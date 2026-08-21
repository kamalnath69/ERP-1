import React from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, CalendarCheck, CheckCircle, EnvelopeSimple, LockKey,
  Phone, Sparkle, UsersThree, WhatsappLogo,
} from "@phosphor-icons/react";

import DemoRequestForm from "@/components/public/DemoRequestForm";
import PageMeta from "@/components/public/PageMeta";
import { usePublicSite } from "@/components/public/PublicSiteLayout";
import {
  CustomProjectsSection, IndustryShowcase, IntelligenceSection,
  PlatformStory, RolloutSection,
} from "@/components/public/landing/LandingSections";
import {
  LandingMotionProvider, Reveal, Stagger, StaggerItem,
} from "@/components/public/landing/LandingMotion";
import PricingSection from "@/components/public/landing/PricingSection";
import ProductShowcase from "@/components/public/landing/ProductShowcase";
import { publicContactLinks } from "@/lib/publicContact";

const principles = [
  "Works with existing systems",
  "Permission-scoped by design",
  "Evidence-linked AI answers",
  "Built for Indian organizations",
];

export default function Landing() {
  const { site, catalog, error, retry } = usePublicSite();
  const phone = site?.contact_phone;
  return <LandingMotionProvider>
    <div className="landing-page overflow-hidden">
      <PageMeta
        title="Edvatiq | Operating intelligence and custom software"
        description="Evidence-backed AI, focused operating workspaces, and custom software for colleges, gyms, salons, clinics, organizations, and founders."
        path="/"
      />
      <Hero site={site} catalog={catalog} />
      <Principles />
      <PlatformStory />
      <IndustryShowcase />
      <IntelligenceSection />
      <RolloutSection />
      <CustomProjectsSection phone={phone} />
      <PricingSection catalog={catalog} error={error} retry={retry} />
      <ContactSection site={site} />
    </div>
  </LandingMotionProvider>;
}

function Hero({ site, catalog }) {
  const trialEnabled = Boolean(catalog?.trial_enabled);
  const signupReady = Boolean(site?.legal_ready);
  const primary = !signupReady
    ? { label: "Explore the platform", to: "#platform", anchor: true }
    : trialEnabled
      ? { label: "Create your workspace", to: "/register?plan=trial" }
      : { label: "Choose your plan", to: "#pricing", anchor: true };
  const secondary = !signupReady || trialEnabled
    ? { label: "Compare plans", to: "#pricing" }
    : { label: "See how it works", to: "#platform" };
  const Primary = primary.anchor ? "a" : Link;
  return <section className="landing-hero relative border-b border-primary/10">
    <div className="landing-grid pointer-events-none absolute inset-0 opacity-60 [mask-image:linear-gradient(to_bottom,black,transparent_88%)]" />
    <div className="landing-ambient landing-ambient-one" />
    <div className="landing-ambient landing-ambient-two" />
    <div className="relative mx-auto grid min-h-[calc(100dvh-4rem)] max-w-[1440px] items-center gap-14 px-4 py-14 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-20">
      <Stagger className="lg:col-span-6 xl:col-span-5" amount={0.05}>
        <StaggerItem><div className="inline-flex items-center gap-2 rounded-full border border-primary/10 bg-card/80 px-3 py-1.5 text-xs font-semibold shadow-sm backdrop-blur"><Sparkle className="text-accent" weight="fill" />Operating intelligence, grounded AI, and focused software</div></StaggerItem>
        <StaggerItem><h1 className="mt-7 max-w-3xl text-[clamp(3.2rem,5.5vw,5.8rem)] font-semibold leading-[0.92] tracking-[-0.055em]">See what matters.<br /><span className="relative text-primary"><span className="relative z-10">Move work forward.</span><i className="absolute inset-x-0 bottom-[.08em] h-[.13em] -rotate-1 rounded-full bg-accent/75" /></span></h1></StaggerItem>
        <StaggerItem><p className="mt-7 max-w-xl text-base leading-8 text-muted-foreground sm:text-lg">Edvatiq brings daily operations, people intelligence, placement readiness, and evidence-backed AI into one calm workspace for Indian organizations.</p></StaggerItem>
        <StaggerItem><div className="mt-8 flex flex-col gap-3 sm:flex-row"><Primary to={primary.anchor ? undefined : primary.to} href={primary.anchor ? primary.to : undefined} className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-[0_14px_30px_hsl(var(--primary)/.16)] transition-transform hover:-translate-y-0.5">{primary.label}<ArrowRight /></Primary><a href={secondary.to} className="inline-flex h-12 items-center justify-center rounded-xl border border-primary/10 bg-card/85 px-6 text-sm font-semibold shadow-sm backdrop-blur transition-colors hover:bg-secondary">{secondary.label}</a></div></StaggerItem>
        <StaggerItem><div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3 text-xs font-medium text-muted-foreground">{[...(trialEnabled ? ["30-day trial"] : []), "GST-ready pricing", "Permission-aware records"].map((item) => <span key={item} className="inline-flex items-center gap-2"><CheckCircle className="text-positive" weight="fill" />{item}</span>)}</div></StaggerItem>
        <StaggerItem><Link to="/?inquiry=client_project#contact" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-primary underline decoration-accent/50 underline-offset-4 hover:decoration-accent">Building something different? Discuss a custom project <ArrowRight /></Link></StaggerItem>
      </Stagger>
      <ProductShowcase />
    </div>
  </section>;
}

function Principles() {
  return <section className="border-b border-primary/10 bg-card" aria-label="Platform principles">
    <Stagger className="mx-auto grid max-w-[1440px] grid-cols-2 px-4 sm:px-6 lg:grid-cols-4 lg:px-8" amount={0.25}>
      {principles.map((item, index) => <StaggerItem key={item} className={`flex min-h-24 items-center gap-2.5 py-4 text-xs font-semibold sm:text-sm ${index % 2 ? "pl-4" : "pr-4"} lg:border-l lg:px-5 lg:first:border-l-0`}><CheckCircle className="shrink-0 text-positive" weight="fill" />{item}</StaggerItem>)}
    </Stagger>
  </section>;
}

function ContactSection({ site }) {
  const supportEmail = site?.support_email || "sales@edvatiq.com";
  const contact = publicContactLinks(site?.contact_phone);
  return <section id="contact" className="scroll-mt-20 bg-[hsl(var(--landing-paper-deep))] px-4 pb-20 pt-16 sm:px-6 lg:px-8 lg:pb-28 lg:pt-24">
    <div className="relative mx-auto grid max-w-[1400px] items-start overflow-hidden rounded-[2rem] bg-primary text-primary-foreground shadow-[0_35px_90px_hsl(var(--shadow-color)/.2)] lg:grid-cols-12">
      <div className="landing-grid-dark pointer-events-none absolute inset-0 opacity-70" />
      <Reveal className="relative p-7 sm:p-10 lg:col-span-5 lg:p-12 xl:p-14">
        <div className="overline !text-primary-foreground/45">Start a conversation</div>
        <h2 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">Tell us what you want to improve or build.</h2>
        <p className="mt-5 max-w-xl text-sm leading-7 text-primary-foreground/62 sm:text-base">Choose an Edvatiq product walkthrough or a custom software discussion. We will prepare around your real workflow, team, and constraints.</p>
        <div className="mt-9 space-y-3 border-t border-primary-foreground/12 pt-8">
          <ContactLink icon={Phone} label="Call us" value={contact.display} href={contact.tel} />
          <ContactLink icon={WhatsappLogo} label="WhatsApp" value="Start a project conversation" href={contact.whatsapp} external />
          <ContactLink icon={EnvelopeSimple} label="Email" value={supportEmail} href={`mailto:${supportEmail}`} />
        </div>
        <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
          {[[CalendarCheck, "A relevant discussion", "We prepare around your selected enquiry."], [UsersThree, "The right context", "Workflow, roles, data, and rollout stay connected."], [LockKey, "A clear next step", "No hidden setup or invented promises."]].map(([Icon, title, copy]) => <div key={title} className="flex gap-3.5"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary-foreground/10 text-accent"><Icon size={18} /></span><div><div className="text-sm font-semibold">{title}</div><p className="mt-1 text-xs leading-5 text-primary-foreground/52">{copy}</p></div></div>)}
        </div>
      </Reveal>
      <Reveal className="relative border-t border-primary-foreground/12 p-3 sm:p-5 lg:col-span-7 lg:border-l lg:border-t-0 lg:p-6 xl:p-8" delay={0.08}><DemoRequestForm /></Reveal>
    </div>
  </section>;
}

function ContactLink({ icon: Icon, label, value, href, external = false }) {
  return <a href={href} target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined} className="group flex items-center gap-3 rounded-xl border border-primary-foreground/10 bg-primary-foreground/[0.045] p-3.5 transition-colors hover:bg-primary-foreground/[0.08]"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary-foreground/10 text-accent"><Icon size={18} /></span><span className="min-w-0"><span className="block text-[10px] font-semibold uppercase tracking-[.14em] text-primary-foreground/42">{label}</span><strong className="mt-0.5 block truncate text-sm">{value}</strong></span><ArrowRight className="ml-auto shrink-0 text-accent transition-transform group-hover:translate-x-1" /></a>;
}
