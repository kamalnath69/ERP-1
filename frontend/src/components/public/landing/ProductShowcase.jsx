import React, { useState } from "react";
import { AnimatePresence, useReducedMotion } from "motion/react";
import {
  ArrowRight, Briefcase, CalendarCheck, ChartLineUp, CheckCircle,
  CirclesFour, Code, LockKey, Sparkle, Student, UsersThree,
} from "@phosphor-icons/react";

import BrandLogo from "@/components/brand/BrandLogo";
import { m } from "./LandingMotion";

const NAVIGATION = {
  college: [[CirclesFour, "Overview"], [Student, "Students"], [Briefcase, "Placements"], [Code, "Coding"], [ChartLineUp, "Readiness"]],
  business: [[CirclesFour, "Home"], [UsersThree, "Clients"], [CalendarCheck, "Calendar"], [ChartLineUp, "Sales"], [Briefcase, "Team"]],
};

export default function ProductShowcase() {
  const [mode, setMode] = useState("college");
  const reducedMotion = useReducedMotion();
  const college = mode === "college";
  return <div className="relative lg:col-span-6 lg:col-start-7 xl:col-span-7">
    <div className="landing-hero-halo absolute -inset-10 rounded-full blur-3xl" />
    <ProductShell reducedMotion={reducedMotion}>
      <div className="overflow-hidden rounded-[1.8rem] border border-primary/10 bg-card p-2 shadow-[0_35px_100px_hsl(var(--shadow-color)/.18)]">
        <div className="flex min-h-14 flex-wrap items-center gap-2 rounded-t-[1.35rem] border-b bg-surface-subtle/90 px-3 py-2 sm:px-4">
          <BrandLogo showName={false} markClassName="h-8 w-8 rounded-lg" />
          <div className="flex rounded-lg border bg-card p-1" role="tablist" aria-label="Preview workspace">
            {[["college", "College"], ["business", "Business"]].map(([value, label]) => <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              aria-controls="landing-product-preview"
              onClick={() => setMode(value)}
              className={`rounded-md px-3 py-1.5 text-[10px] font-semibold transition-colors ${mode === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >{label}</button>)}
          </div>
          <span className="ml-auto hidden items-center gap-1.5 text-[10px] font-semibold text-muted-foreground sm:inline-flex"><i className="h-1.5 w-1.5 rounded-full bg-positive" />Illustrative workspace</span>
        </div>
        <div className="grid min-h-[430px] sm:grid-cols-[8.5rem_1fr]">
          <aside className="hidden border-r bg-surface-subtle/75 p-3 sm:block" aria-label="Preview navigation">
            <div className="space-y-1">{NAVIGATION[mode].map(([Icon, label], index) => <div key={label} className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-[10px] font-semibold ${index === 0 ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"}`}><Icon size={14} />{label}</div>)}</div>
            <div className="mt-28 rounded-xl bg-primary p-3 text-primary-foreground"><Sparkle className="text-accent" weight="fill" /><div className="mt-2 text-[9px] font-semibold">Ask Edvatiq</div><div className="mt-1 text-[8px] leading-4 text-primary-foreground/55">Grounded in permitted records</div></div>
          </aside>
          <div id="landing-product-preview" role="tabpanel" className="min-w-0 p-4 sm:p-5">
            <AnimatePresence mode="wait" initial={false}>
              {reducedMotion
                ? <div key={mode}>{college ? <CollegeScene /> : <BusinessScene />}</div>
                : <m.div key={mode} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} transition={{ duration: 0.28 }}>
                  {college ? <CollegeScene /> : <BusinessScene />}
                </m.div>}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </ProductShell>
    <FloatingNote className="-left-8 top-24 hidden xl:flex" icon={LockKey} label="Access checked" copy="Only permitted records" delay={0.65} />
    <FloatingNote className="-right-5 bottom-16 hidden xl:flex" icon={Sparkle} label="Evidence linked" copy="Answers show their basis" delay={0.8} />
  </div>;
}

function ProductShell({ reducedMotion, children }) {
  if (reducedMotion) {
    return <div className="landing-product-shell relative">{children}</div>;
  }
  return <m.div
    className="landing-product-shell relative"
    initial={{ opacity: 0, y: 28, rotateX: 3 }}
    animate={{ opacity: 1, y: 0, rotateX: 0 }}
    transition={{ delay: 0.22, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
  >
    {children}
  </m.div>;
}

function CollegeScene() {
  return <><PreviewHeading eyebrow="College placement" title="Placement readiness" tag="Current scope" />
    <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">{[["Students", "Authorized"], ["Readiness", "Evidence"], ["Drives", "Current"], ["Offers", "Tracked"]].map(([label, value]) => <Metric key={label} label={label} value={value} />)}</div>
    <div className="mt-3 grid gap-3 lg:grid-cols-2">
      <div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Readiness signals</div><div className="mt-5 flex items-center gap-4"><div className="grid h-24 w-24 shrink-0 place-items-center rounded-full bg-[conic-gradient(hsl(var(--chart-2))_0_42%,hsl(var(--accent)/.8)_42%_72%,hsl(var(--muted))_72%)]"><div className="grid h-14 w-14 place-items-center rounded-full bg-card text-[9px] font-semibold">Verified</div></div><div className="space-y-2 text-[9px]">{["Ready evidence", "Developing", "Needs support"].map((label, index) => <div key={label} className="flex items-center gap-2"><i className={`h-2 w-2 rounded-full ${index === 0 ? "bg-[hsl(var(--chart-2))]" : index === 1 ? "bg-accent" : "bg-muted"}`} />{label}</div>)}</div></div></div>
      <div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Placement journey</div><div className="mt-5 space-y-3">{[["Eligible", "w-[92%]"], ["Applied", "w-[72%]"], ["Interview", "w-[48%]"], ["Offered", "w-[34%]"]].map(([label, width]) => <div key={label}><div className="text-[8px] font-medium">{label}</div><div className="mt-1.5 h-2 rounded-full bg-secondary"><div className={`h-full rounded-full bg-primary ${width}`} /></div></div>)}</div></div>
    </div>
    <PreviewNotice title="Review readiness gaps before the next drive" copy="Attendance, coding, and profile evidence stay connected." />
  </>;
}

function BusinessScene() {
  return <><PreviewHeading eyebrow="Focused operations" title="Business position" tag="Today" />
    <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">{[["Collections", "Live"], ["Clients", "In context"], ["Schedule", "Connected"], ["Work", "Assigned"]].map(([label, value]) => <Metric key={label} label={label} value={value} />)}</div>
    <div className="mt-3 grid gap-3 lg:grid-cols-[1.35fr_.65fr]">
      <div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Collections trend</div><div className="mt-7 flex h-32 items-end gap-2">{[34, 54, 44, 72, 58, 84, 76, 92].map((height, index) => <div key={`${height}-${index}`} className="flex-1 origin-bottom rounded-t-md bg-[hsl(var(--chart-2)/.26)]" style={{ height: `${height}%`, opacity: 0.5 + index * 0.055 }} />)}</div></div>
      <div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Needs attention</div>{["Renewals", "Payments", "Follow-ups"].map((item) => <div key={item} className="mt-3 flex items-center gap-2 text-[9px]"><span className="h-6 w-6 rounded-lg bg-secondary" /><span>{item}</span></div>)}</div>
    </div>
    <PreviewNotice title="Keep the next action beside the record" copy="No separate spreadsheet or disconnected follow-up list." positive />
  </>;
}

function PreviewHeading({ eyebrow, title, tag }) {
  return <div className="flex items-end justify-between gap-3"><div><div className="text-[9px] font-semibold uppercase tracking-[.16em] text-muted-foreground">{eyebrow}</div><div className="mt-1 text-sm font-semibold">{title}</div></div><span className="rounded-lg border px-2 py-1 text-[9px]">{tag}</span></div>;
}

function Metric({ label, value }) {
  return <div className="rounded-xl border bg-card p-3"><div className="text-[8px] text-muted-foreground">{label}</div><div className="mt-2 text-[11px] font-semibold sm:text-xs">{value}</div></div>;
}

function PreviewNotice({ title, copy, positive = false }) {
  return <div className="mt-3 flex items-center justify-between gap-4 rounded-xl border bg-accent/5 p-3"><div><div className="text-[9px] font-semibold">{title}</div><div className="mt-1 text-[8px] leading-4 text-muted-foreground">{copy}</div></div>{positive ? <CheckCircle className="shrink-0 text-positive" weight="fill" /> : <ArrowRight className="shrink-0 text-accent" />}</div>;
}

function FloatingNote({ icon: Icon, label, copy, className, delay }) {
  const reducedMotion = useReducedMotion();
  const content = <><span className="grid h-9 w-9 place-items-center rounded-xl bg-secondary text-primary"><Icon size={18} /></span><span><strong className="block text-[11px]">{label}</strong><span className="mt-0.5 block text-[9px] text-muted-foreground">{copy}</span></span></>;
  const classes = `absolute z-10 items-center gap-3 rounded-2xl border bg-card/95 p-3.5 shadow-xl backdrop-blur ${className}`;
  if (reducedMotion) {
    return <div className={classes}>{content}</div>;
  }
  return <m.div
    className={classes}
    initial={{ opacity: 0, scale: 0.94, y: 8 }}
    animate={{ opacity: 1, scale: 1, y: 0 }}
    transition={{ delay, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
  >
    {content}
  </m.div>;
}
