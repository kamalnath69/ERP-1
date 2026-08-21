import React, { useRef } from "react";
import { LazyMotion, MotionConfig, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import * as m from "motion/react-m";

const loadFeatures = () => import("./motionFeatures").then((module) => module.default);

export function LandingMotionProvider({ children }) {
  return <LazyMotion features={loadFeatures} strict>
    <MotionConfig
      reducedMotion="user"
      transition={{ duration: 0.52, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </MotionConfig>
  </LazyMotion>;
}

export function Reveal({ children, className = "", delay = 0, amount = 0.16 }) {
  const reducedMotion = useReducedMotion();
  if (reducedMotion) {
    return <div className={className}>{children}</div>;
  }
  return <m.div
    className={className}
    initial={{ opacity: 0, y: 24 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, amount }}
    transition={{ delay, duration: 0.62, ease: [0.22, 1, 0.36, 1] }}
  >
    {children}
  </m.div>;
}

export function Stagger({ children, className = "", amount = 0.14 }) {
  const reducedMotion = useReducedMotion();
  if (reducedMotion) {
    return <div className={className}>{children}</div>;
  }
  return <m.div
    className={className}
    initial="hidden"
    whileInView="shown"
    viewport={{ once: true, amount }}
    variants={{
      hidden: {},
      shown: { transition: { staggerChildren: 0.085, delayChildren: 0.04 } },
    }}
  >
    {children}
  </m.div>;
}

export function StaggerItem({ children, className = "" }) {
  const reducedMotion = useReducedMotion();
  if (reducedMotion) {
    return <div className={className}>{children}</div>;
  }
  return <m.div
    className={className}
    variants={{
      hidden: { opacity: 0, y: 18 },
      shown: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
    }}
  >
    {children}
  </m.div>;
}

export function ParallaxLayer({ children, className = "", distance = 24 }) {
  const ref = useRef(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const rawY = useTransform(scrollYProgress, [0, 1], [-distance, distance]);
  const y = useSpring(rawY, { stiffness: 90, damping: 24, mass: 0.45 });
  if (reducedMotion) {
    return <div className={className}>{children}</div>;
  }
  return <m.div ref={ref} className={className} style={{ y }}>
    {children}
  </m.div>;
}

export { m };
