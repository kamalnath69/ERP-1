import React, { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, useReducedMotion } from "motion/react";
import {
  ArrowRight, Barbell, BracketsCurly, Briefcase, CalendarCheck, ChartLineUp,
  CheckCircle, CirclesFour, Code, Database, FlowArrow, GraduationCap, Lightning,
  LinkSimple, LockKey, Scissors, Sparkle, Stethoscope, UsersThree, WhatsappLogo,
} from "@phosphor-icons/react";

import { publicContactLinks } from "@/lib/publicContact";
import { m, ParallaxLayer, Reveal, Stagger, StaggerItem } from "./LandingMotion";

const platformSteps = [
  {
    key: "connect",
    number: "01",
    title: "Bring the right records",
    copy: "Connect existing systems, import structured data, or begin with one focused workflow. Keep useful tools where they belong.",
    icon: Database,
  },
  {
    key: "prioritize",
    number: "02",
    title: "See priorities clearly",
    copy: "Role-aware workspaces bring people, evidence, deadlines, and operational risk into one calm decision surface.",
    icon: ChartLineUp,
  },
  {
    key: "act",
    number: "03",
    title: "Move work forward",
    copy: "Take the next step beside the record, with permissions, confirmations, and audit history protecting sensitive actions.",
    icon: Lightning,
  },
];

const industries = [
  {
    key: "college", icon: GraduationCap, eyebrow: "College placement", title: "Turn student evidence into placement action.",
    copy: "Bring readiness, academics, coding progress, drives, interviews, and offers into one permission-aware command center.",
    modules: ["Student readiness", "Drive operations", "Academic evidence", "Placement analytics"],
    signal: "Find the students who need support before a deadline is missed.",
  },
  {
    key: "gym", icon: Barbell, eyebrow: "Gym and fitness", title: "Run membership around the person, not the spreadsheet.",
    copy: "Connect memberships, check-ins, coaching, progress, classes, renewals, and clear client billing.",
    modules: ["Memberships", "Attendance", "Coaching", "Billing"],
    signal: "Keep renewals and follow-ups beside the member history.",
  },
  {
    key: "salon", icon: Scissors, eyebrow: "Salon and spa", title: "Keep every visit personal and every operation visible.",
    copy: "Coordinate bookings, preferences, service history, checkout, stock, follow-ups, and staff performance.",
    modules: ["Appointments", "Client history", "Checkout", "Inventory"],
    signal: "Turn service context into a better next visit.",
  },
  {
    key: "clinic", icon: Stethoscope, eyebrow: "Outpatient clinic", title: "Create a clearer path from queue to follow-up.",
    copy: "Connect patient queues, encounters, prescriptions, labs, pharmacy, and permission-separated clinical records.",
    modules: ["Patient queue", "Encounters", "Prescriptions", "Clinical access"],
    signal: "Keep operational flow clear without weakening clinical boundaries.",
  },
];

const projectServices = [
  [BracketsCurly, "Custom web applications", "Focused portals and products shaped around the way your organization actually works."],
  [CirclesFour, "Internal operations systems", "Replace disconnected sheets and manual handoffs with one dependable workflow."],
  [LinkSimple, "ERP and API integrations", "Connect systems, migrate structured data, and remove repetitive data movement."],
  [Sparkle, "AI-enabled automation", "Add grounded assistants and controlled automation where they create measurable operational value."],
];

export function PlatformStory() {
  const [active, setActive] = useState("connect");
  return <section id="platform" className="scroll-mt-20 border-b border-primary/10 bg-[hsl(var(--landing-paper))]">
    <div className="mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <Reveal className="grid gap-7 lg:grid-cols-12 lg:items-end">
        <div className="lg:col-span-6"><div className="overline">One connected workspace</div><h2 className="landing-section-title mt-3">From scattered records to a clear next move.</h2></div>
        <p className="max-w-2xl text-base leading-8 text-muted-foreground lg:col-span-5 lg:col-start-8">Edvatiq adapts to the organization, role, and permitted scope. Your team sees the evidence and action that matter, not another dashboard full of disconnected totals.</p>
      </Reveal>

      <Stagger className="mt-12 grid gap-4 lg:hidden">
        {platformSteps.map(({ key, number, title, copy, icon: Icon }) => <StaggerItem key={key}><article className="landing-editorial-card p-6"><div className="flex items-center justify-between"><span className="font-mono text-xs font-semibold text-accent">{number}</span><span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary text-primary"><Icon size={20} /></span></div><h3 className="mt-8 text-2xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-7 text-muted-foreground">{copy}</p></article></StaggerItem>)}
      </Stagger>

      <div className="mt-16 hidden grid-cols-12 gap-10 lg:grid">
        <div className="col-span-5 space-y-3" role="tablist" aria-label="How Edvatiq works">
          {platformSteps.map(({ key, number, title, copy, icon: Icon }) => <button
            key={key}
            type="button"
            role="tab"
            aria-selected={active === key}
            aria-controls="platform-story-panel"
            onClick={() => setActive(key)}
            className={`group w-full rounded-2xl border p-5 text-left transition-[background-color,border-color,box-shadow,transform] ${active === key ? "border-primary/25 bg-card shadow-[0_18px_45px_hsl(var(--shadow-color)/.08)]" : "border-transparent hover:border-border hover:bg-card/55"}`}
          >
            <div className="flex gap-4"><span className={`mt-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-xl transition-colors ${active === key ? "bg-primary text-primary-foreground" : "bg-secondary text-primary"}`}><Icon size={20} /></span><span><span className="font-mono text-[10px] font-semibold text-accent">{number}</span><strong className="mt-1 block text-xl">{title}</strong><span className="mt-2 block text-sm leading-6 text-muted-foreground">{copy}</span></span></div>
          </button>)}
        </div>
        <ParallaxLayer className="col-span-7" distance={16}>
          <div className="sticky top-28"><WorkflowCanvas active={active} /></div>
        </ParallaxLayer>
      </div>
    </div>
  </section>;
}

function WorkflowCanvas({ active }) {
  const reducedMotion = useReducedMotion();
  const content = {
    connect: {
      label: "Connected inputs", title: "Keep a governed source of truth.", icon: Database,
      rows: [["Student information system", "Connected"], ["Structured imports", "Validated"], ["Local records", "In scope"]],
      footer: "Start with one useful workflow. Expand when the team is ready.",
    },
    prioritize: {
      label: "Role-aware priorities", title: "Show the work that needs attention.", icon: ChartLineUp,
      rows: [["Evidence gaps", "Review"], ["Upcoming deadlines", "Plan"], ["People needing support", "Act"]],
      footer: "Every result is limited to the viewer's current permissions.",
    },
    act: {
      label: "Controlled execution", title: "Complete work without losing context.", icon: Lightning,
      rows: [["Assign the next step", "Tracked"], ["Confirm sensitive actions", "Protected"], ["Review audit history", "Available"]],
      footer: "The record, decision, and responsible person stay connected.",
    },
  }[active];
  const Icon = content.icon;
  return <div id="platform-story-panel" role="tabpanel" className="landing-workflow-canvas overflow-hidden rounded-[2rem] border border-primary/12 bg-primary p-3 text-primary-foreground shadow-[0_30px_80px_hsl(var(--shadow-color)/.16)]">
    <div className="landing-grid-dark relative min-h-[31rem] overflow-hidden rounded-[1.45rem] border border-primary-foreground/10 p-7 xl:p-9">
      <AnimatePresence mode="wait" initial={false}>
        <m.div key={active} initial={{ opacity: 0, x: reducedMotion ? 0 : 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reducedMotion ? 0 : -12 }} transition={{ duration: 0.3 }}>
          <div className="flex items-center justify-between"><span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[.16em] text-primary-foreground/50"><Icon className="text-accent" size={17} />{content.label}</span><span className="rounded-full border border-primary-foreground/12 px-3 py-1 text-[10px] text-primary-foreground/55">Authorized scope</span></div>
          <h3 className="mt-12 max-w-lg text-4xl font-semibold leading-tight xl:text-5xl">{content.title}</h3>
          <div className="mt-10 space-y-3">{content.rows.map(([label, status], index) => <m.div key={label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.06 }} className="flex items-center gap-3 rounded-xl border border-primary-foreground/10 bg-primary-foreground/[0.055] p-4"><span className="grid h-9 w-9 place-items-center rounded-lg bg-primary-foreground/10"><CheckCircle className="text-accent" weight="fill" /></span><strong className="text-sm">{label}</strong><span className="ml-auto rounded-full bg-primary-foreground/8 px-2.5 py-1 text-[10px] text-primary-foreground/60">{status}</span></m.div>)}</div>
          <div className="mt-7 flex items-center gap-3 border-t border-primary-foreground/10 pt-6 text-xs leading-5 text-primary-foreground/55"><LockKey className="shrink-0 text-accent" size={18} />{content.footer}</div>
        </m.div>
      </AnimatePresence>
    </div>
  </div>;
}

export function IndustryShowcase() {
  const [active, setActive] = useState("college");
  const selected = industries.find((item) => item.key === active) || industries[0];
  const reducedMotion = useReducedMotion();
  return <section id="industries" className="scroll-mt-20 overflow-hidden bg-primary text-primary-foreground">
    <div className="landing-grid-dark mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <Reveal className="grid gap-8 lg:grid-cols-12 lg:items-end">
        <div className="lg:col-span-7"><div className="overline !text-primary-foreground/45">Purpose-built by industry</div><h2 className="landing-section-title mt-3">Shared foundations. Workflows that belong.</h2></div>
        <p className="text-sm leading-7 text-primary-foreground/60 lg:col-span-4 lg:col-start-9">The underlying access, records, billing, and intelligence remain consistent. The operating language does not.</p>
      </Reveal>
      <div className="mt-14 grid gap-8 lg:grid-cols-12">
        <div className="flex gap-2 overflow-x-auto pb-2 lg:col-span-4 lg:flex-col lg:overflow-visible lg:pb-0" role="tablist" aria-label="Industry solutions">
          {industries.map(({ key, icon: Icon, eyebrow }) => <button key={key} type="button" role="tab" aria-selected={active === key} aria-controls="industry-panel" onClick={() => setActive(key)} className={`flex min-w-max items-center gap-3 rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors lg:w-full ${active === key ? "border-primary-foreground/20 bg-primary-foreground text-primary" : "border-primary-foreground/10 bg-primary-foreground/[0.035] text-primary-foreground/65 hover:bg-primary-foreground/[0.075] hover:text-primary-foreground"}`}><Icon size={20} weight="duotone" />{eyebrow}<ArrowRight className={`ml-auto hidden transition-transform lg:block ${active === key ? "translate-x-0" : "-translate-x-1 opacity-40"}`} /></button>)}
        </div>
        <div id="industry-panel" role="tabpanel" className="relative min-h-[31rem] overflow-hidden rounded-[2rem] border border-primary-foreground/12 bg-primary-foreground/[0.045] p-6 sm:p-8 lg:col-span-8 xl:p-10">
          <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-accent/12 blur-3xl" />
          <AnimatePresence mode="wait" initial={false}>
            <m.div key={active} className="relative" initial={{ opacity: 0, y: reducedMotion ? 0 : 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reducedMotion ? 0 : -10 }} transition={{ duration: 0.32 }}>
              <selected.icon className="text-accent" size={34} weight="duotone" />
              <div className="mt-8 text-xs font-semibold uppercase tracking-[.18em] text-primary-foreground/45">{selected.eyebrow}</div>
              <h3 className="mt-3 max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl xl:text-5xl">{selected.title}</h3>
              <p className="mt-5 max-w-2xl text-sm leading-7 text-primary-foreground/62 sm:text-base">{selected.copy}</p>
              <div className="mt-9 flex flex-wrap gap-2">{selected.modules.map((module) => <span key={module} className="rounded-full border border-primary-foreground/12 bg-primary-foreground/[0.06] px-3 py-1.5 text-xs text-primary-foreground/72">{module}</span>)}</div>
              <div className="mt-10 flex max-w-2xl items-start gap-3 rounded-2xl border border-primary-foreground/12 bg-primary-foreground/[0.07] p-4"><Sparkle className="mt-0.5 shrink-0 text-accent" weight="fill" /><div><strong className="text-sm">A clearer operational signal</strong><p className="mt-1 text-xs leading-5 text-primary-foreground/55">{selected.signal}</p></div></div>
            </m.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  </section>;
}

export function IntelligenceSection() {
  return <section id="ai" className="scroll-mt-20 overflow-hidden border-b border-primary/10 bg-[hsl(var(--landing-paper-deep))]">
    <div className="mx-auto grid max-w-[1440px] gap-12 px-4 py-20 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-28">
      <Reveal className="lg:col-span-5 lg:pt-8"><div className="overline">Edvatiq AI</div><h2 className="landing-section-title mt-3">An assistant that can show its work.</h2><p className="mt-6 max-w-xl text-base leading-8 text-muted-foreground">Ask naturally in English, Tamil, or Tanglish. Edvatiq answers from authorized records, explains the evidence, and keeps sensitive actions behind confirmation.</p><div className="mt-8 space-y-4">{[[LockKey, "Permissions are resolved before data is queried."], [Database, "Answers stay connected to current ERP evidence."], [FlowArrow, "Follow-up questions retain only authorized context."]].map(([Icon, copy]) => <div key={copy} className="flex items-start gap-3 text-sm leading-6"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary text-accent"><Icon size={16} /></span>{copy}</div>)}</div></Reveal>
      <ParallaxLayer className="lg:col-span-6 lg:col-start-7" distance={18}>
        <Stagger className="landing-ai-scene rounded-[2rem] border border-primary/10 bg-card p-3 shadow-[0_28px_80px_hsl(var(--shadow-color)/.12)] sm:p-5">
          <div className="rounded-[1.45rem] bg-primary p-5 text-primary-foreground sm:p-7">
            <StaggerItem><div className="flex items-center justify-between gap-3"><span className="inline-flex items-center gap-2 text-sm font-semibold"><Sparkle className="text-accent" weight="fill" />Ask Edvatiq</span><span className="rounded-full border border-primary-foreground/15 px-2.5 py-1 text-[10px] text-primary-foreground/55">Permission scoped</span></div></StaggerItem>
            <StaggerItem><div className="ml-auto mt-8 max-w-[88%] rounded-2xl rounded-br-md border border-primary-foreground/12 bg-primary-foreground/[0.07] p-4 text-sm leading-6 text-primary-foreground/78">Which students need support before the next placement drive?</div></StaggerItem>
            <StaggerItem><div className="mt-4 rounded-2xl rounded-bl-md bg-card p-5 text-foreground shadow-sm"><div className="flex items-center gap-2 text-sm font-semibold"><CirclesFour className="text-accent" />Evidence-linked answer</div><p className="mt-3 text-sm leading-6 text-muted-foreground">Prioritize students with missing eligibility evidence, attendance risk, or incomplete readiness records within your authorized scope.</p><div className="mt-4 grid gap-2 sm:grid-cols-3">{["Readiness", "Attendance", "Drive eligibility"].map((item) => <div key={item} className="flex items-center gap-2 rounded-lg bg-secondary px-3 py-2.5 text-[10px] font-semibold"><CheckCircle className="text-positive" weight="fill" />{item}</div>)}</div></div></StaggerItem>
            <StaggerItem><div className="mt-3 flex items-center justify-between rounded-xl border border-primary-foreground/10 px-4 py-3 text-[10px] text-primary-foreground/50"><span>Evidence and scope available</span><ArrowRight /></div></StaggerItem>
          </div>
        </Stagger>
      </ParallaxLayer>
    </div>
  </section>;
}

export function RolloutSection() {
  return <section id="about" className="scroll-mt-20 bg-card">
    <div className="mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <Reveal className="grid gap-8 lg:grid-cols-12"><div className="lg:col-span-4"><div className="overline">A practical rollout</div><h2 className="landing-section-title mt-3">Useful before everything is perfect.</h2></div><p className="max-w-2xl text-base leading-8 text-muted-foreground lg:col-span-6 lg:col-start-7">Start where clarity is most valuable. Edvatiq can work beside existing systems, establish a reliable operating rhythm, and expand without forcing a disruptive rip-and-replace programme.</p></Reveal>
      <Stagger className="mt-14 grid overflow-hidden rounded-[2rem] border bg-border lg:grid-cols-3">
        {platformSteps.map(({ number, title, copy, icon: Icon }) => <StaggerItem key={number} className="bg-card p-6 sm:p-8"><div className="flex items-center justify-between"><span className="font-mono text-xs font-semibold text-accent">{number}</span><Icon className="text-primary" size={22} /></div><h3 className="mt-12 text-2xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-7 text-muted-foreground">{copy}</p></StaggerItem>)}
      </Stagger>
    </div>
  </section>;
}

export function CustomProjectsSection({ phone }) {
  const contact = publicContactLinks(phone);
  return <section id="services" className="scroll-mt-20 overflow-hidden border-y border-primary/10 bg-[hsl(var(--landing-paper))]">
    <div className="relative mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <div className="absolute right-0 top-10 h-80 w-80 rounded-full bg-accent/8 blur-3xl" />
      <Reveal className="relative grid gap-8 lg:grid-cols-12 lg:items-end"><div className="lg:col-span-7"><div className="overline">Beyond the platform</div><h2 className="landing-section-title mt-3">Need software built around your workflow?</h2></div><div className="lg:col-span-4 lg:col-start-9"><p className="text-sm leading-7 text-muted-foreground">Alongside Edvatiq, we design and build focused custom software for organizations and founders.</p><div className="mt-5 flex flex-col gap-2 sm:flex-row"><Link to="/?inquiry=client_project#contact" className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/10">Discuss a project <ArrowRight /></Link><a href={contact.whatsapp} target="_blank" rel="noreferrer" className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border bg-card px-5 text-sm font-semibold hover:bg-secondary"><WhatsappLogo size={19} />WhatsApp us</a></div></div></Reveal>
      <Stagger className="relative mt-12 grid gap-4 md:grid-cols-2">
        {projectServices.map(([Icon, title, copy], index) => <StaggerItem key={title}><article className={`landing-service-card min-h-56 rounded-2xl border p-6 sm:p-7 ${index === 0 || index === 3 ? "bg-primary text-primary-foreground" : "bg-card"}`}><span className={`grid h-11 w-11 place-items-center rounded-xl ${index === 0 || index === 3 ? "bg-primary-foreground/10 text-accent" : "bg-secondary text-primary"}`}><Icon size={22} /></span><h3 className="mt-8 text-2xl font-semibold">{title}</h3><p className={`mt-3 max-w-xl text-sm leading-7 ${index === 0 || index === 3 ? "text-primary-foreground/58" : "text-muted-foreground"}`}>{copy}</p></article></StaggerItem>)}
      </Stagger>
    </div>
  </section>;
}
