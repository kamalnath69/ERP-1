import React, { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, Barbell, Briefcase, CalendarCheck, ChartLineUp, Check,
  CheckCircle, CirclesFour, Code, GraduationCap, LockKey, Scissors,
  Sparkle, Stethoscope, Student, UsersThree, WarningCircle,
} from "@phosphor-icons/react";

import { usePublicSite } from "@/components/public/PublicSiteLayout";
import BrandLogo from "@/components/brand/BrandLogo";
import DemoRequestForm from "@/components/public/DemoRequestForm";
import PageMeta from "@/components/public/PageMeta";

const industries = [
  {
    icon: Barbell,
    title: "Gym and fitness",
    copy: "Memberships, check-ins, coaching, progress, classes, and clear client billing in one workspace.",
    accent: "bg-[hsl(var(--chart-2)/.14)] text-[hsl(var(--chart-2))]",
  },
  {
    icon: Scissors,
    title: "Salon and spa",
    copy: "Bookings, preferences, service history, checkout, follow-ups, stock, and staff performance.",
    accent: "bg-[hsl(var(--chart-4)/.14)] text-[hsl(var(--chart-4))]",
  },
  {
    icon: Stethoscope,
    title: "Outpatient clinic",
    copy: "Patient queues, encounters, prescriptions, labs, pharmacy, and permission-separated clinical records.",
    accent: "bg-[hsl(var(--chart-1)/.14)] text-[hsl(var(--chart-1))]",
  },
  {
    icon: GraduationCap,
    title: "College placement",
    copy: "Student readiness, academic evidence, coding progress, drives, applications, interviews, and offers.",
    accent: "bg-[hsl(var(--chart-3)/.14)] text-[hsl(var(--chart-3))]",
  },
];

const capabilities = [
  [Sparkle, "Evidence-backed AI", "Ask in English, Tamil, or Tanglish. Answers stay grounded in authorized records and link back to evidence."],
  [UsersThree, "People in context", "Understand each client, patient, member, or student with the history and next action that matter."],
  [CalendarCheck, "Connected execution", "Schedules, work queues, payments, inventory, interventions, and ownership stay connected."],
  [LockKey, "Responsible access", "Roles, location scope, confirmations, and audit history protect important data and actions."],
];

const journeySteps = [
  ["01", "Bring the right records", "Connect existing systems, import structured data, or begin with focused local records. Edvatiq does not force a disruptive rip-and-replace rollout."],
  ["02", "See priorities clearly", "Role-aware dashboards surface the people, evidence, deadlines, and operational risks that deserve attention now."],
  ["03", "Act with confidence", "Use grounded AI and connected workflows to take the next step, with permissions and confirmations protecting sensitive actions."],
];

function DemoLink({ children, className = "" }) {
  return <Link to="/#contact" className={className}>{children}</Link>;
}

const money = (paise) => new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
}).format(Number(paise || 0) / 100);

export default function Landing() {
  const { site, catalog, error, retry } = usePublicSite();
  const trialEnabled = Boolean(catalog?.trial_enabled);
  const signupReady = Boolean(site?.legal_ready);
  return <div className="overflow-hidden">
    <PageMeta title="Edvatiq | Placement intelligence and focused operations" description="Evidence-backed AI and focused workspaces for colleges, gyms, salons, and clinics." path="/" />
      <section className="soft-glow relative border-b">
        <div className="paper-grid absolute inset-0 opacity-[0.28] [mask-image:linear-gradient(to_bottom,black,transparent_88%)]" />
        <div className="relative mx-auto grid min-h-[calc(100dvh-4rem)] max-w-[1440px] items-center gap-12 px-4 py-14 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-20">
          <div className="lg:col-span-6 xl:col-span-5">
            <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs font-semibold shadow-sm">
              <Sparkle className="text-accent" weight="fill" />
              Operations, placement intelligence, and grounded AI
            </div>
            <h1 className="mt-7 max-w-3xl text-[clamp(3rem,5.4vw,5.6rem)] font-semibold leading-[0.95] tracking-[-0.052em]">
              See what matters.<br /><span className="text-accent">Move work forward.</span>
            </h1>
            <p className="mt-7 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
              Edvatiq brings daily operations, people intelligence, placement readiness, and grounded AI into one calm workspace for Indian organizations.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              {!signupReady
                ? <a href="#platform" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/10 transition-transform hover:-translate-y-0.5">Explore the platform <ArrowRight /></a>
                : trialEnabled
                ? <Link to="/register?plan=trial" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/10 transition-transform hover:-translate-y-0.5">Create your workspace <ArrowRight /></Link>
                : <a href="#pricing" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/10 transition-transform hover:-translate-y-0.5">Choose your plan <ArrowRight /></a>}
              <a href={!signupReady || trialEnabled ? "#pricing" : "#platform"} className="inline-flex h-12 items-center justify-center rounded-xl border bg-card px-6 text-sm font-semibold shadow-sm transition-colors hover:bg-secondary">{!signupReady || trialEnabled ? "Compare plans" : "Explore product"}</a>
            </div>
            <div className="mt-9 flex flex-wrap gap-x-6 gap-y-3 text-xs font-medium text-muted-foreground">
              {[...(trialEnabled ? ["30-day trial"] : []), "GST-ready pricing", "Gym, Salon, Clinic, and College"].map((item) => <span key={item} className="inline-flex items-center gap-2"><CheckCircle className="text-positive" weight="fill" />{item}</span>)}
            </div>
          </div>
          <ProductPreview />
        </div>
      </section>

      <section className="border-b bg-card" aria-label="Platform principles">
        <div className="mx-auto grid max-w-[1440px] grid-cols-2 px-4 sm:px-6 lg:grid-cols-4 lg:px-8">
          {["Works with existing systems", "Permission-scoped by design", "Evidence-linked AI answers", "Built for Indian organizations"].map((item, index) => <div key={item} className={`flex min-h-20 items-center gap-2.5 py-4 text-xs font-semibold sm:text-sm ${index % 2 ? "pl-4" : "pr-4"} lg:border-l lg:px-5 lg:first:border-l-0`}><CheckCircle className="shrink-0 text-positive" weight="fill" />{item}</div>)}
        </div>
      </section>

      <section id="platform" className="mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
        <div className="grid gap-10 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-5"><div className="overline">One connected workspace</div><h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">Clarity before more software.</h2></div>
          <p className="max-w-2xl text-base leading-7 text-muted-foreground lg:col-span-6 lg:col-start-7">Every workspace adapts to the organization, role, and permitted scope. Teams see the next useful action instead of a dashboard full of disconnected totals.</p>
        </div>
        <div className="mt-12 grid overflow-hidden rounded-2xl border bg-border md:grid-cols-2 xl:grid-cols-4">
          {capabilities.map(([Icon, title, copy]) => <article key={title} className="bg-card p-6 md:p-7"><span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary text-primary"><Icon size={20} /></span><h3 className="mt-6 text-xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-6 text-muted-foreground">{copy}</p></article>)}
        </div>
      </section>

      <section id="industries" className="border-y bg-primary text-primary-foreground">
        <div className="mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
          <div className="grid gap-8 lg:grid-cols-12 lg:items-end"><div className="lg:col-span-7"><div className="overline !text-primary-foreground/50">Purpose-built by industry</div><h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">Shared foundations. Workflows that belong.</h2></div><p className="text-sm leading-6 text-primary-foreground/60 lg:col-span-4 lg:col-start-9">Each category gets focused operations and language, while access, records, billing, and AI remain consistent.</p></div>
          <div className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {industries.map(({ icon: Icon, title, copy, accent }) => <article key={title} className="group rounded-2xl border border-primary-foreground/12 bg-primary-foreground/[0.045] p-6 transition-transform hover:-translate-y-1 sm:p-8"><span className={`grid h-11 w-11 place-items-center rounded-xl ${accent}`}><Icon size={23} weight="duotone" /></span><h3 className="mt-8 text-2xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-6 text-primary-foreground/58">{copy}</p><div className="mt-8 flex items-center gap-2 text-xs font-semibold text-accent">Built into Edvatiq <ArrowRight className="transition-transform group-hover:translate-x-1" /></div></article>)}
          </div>
        </div>
      </section>

      <section id="about" className="scroll-mt-16 border-b bg-surface-subtle">
        <div className="mx-auto grid max-w-[1440px] gap-12 px-4 py-20 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-28">
          <div className="lg:col-span-4">
            <div className="overline">Why Edvatiq</div>
            <h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">Useful before everything is perfect.</h2>
            <p className="mt-5 max-w-md text-base leading-7 text-muted-foreground">Edvatiq is an operating layer for clearer decisions. Start with one valuable workflow, keep existing systems where they belong, and expand when your team is ready.</p>
          </div>
          <div className="divide-y overflow-hidden rounded-2xl border bg-card lg:col-span-7 lg:col-start-6">
            {journeySteps.map(([number, title, copy]) => <article key={number} className="grid gap-4 p-5 sm:grid-cols-[3.5rem_1fr] sm:p-7"><span className="font-mono text-xs font-semibold text-accent">{number}</span><div><h3 className="text-xl font-semibold">{title}</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">{copy}</p></div></article>)}
          </div>
        </div>
      </section>

      <section id="ai" className="mx-auto grid max-w-[1440px] gap-12 px-4 py-20 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-28">
        <div className="lg:col-span-5"><div className="overline">Edvatiq AI</div><h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">An assistant that can show its work.</h2><p className="mt-5 text-base leading-7 text-muted-foreground">Ask naturally, inspect the supporting records, and confirm sensitive actions before anything changes. Personalize tone and detail without weakening permissions or accuracy.</p></div>
        <div className="lg:col-span-6 lg:col-start-7"><div className="surface-card overflow-hidden p-2 shadow-xl shadow-primary/5"><div className="rounded-xl bg-primary p-5 text-primary-foreground sm:p-7"><div className="flex items-center justify-between"><span className="inline-flex items-center gap-2 text-sm font-semibold"><Sparkle className="text-accent" weight="fill" />Ask Edvatiq</span><span className="rounded-full border border-primary-foreground/15 px-2.5 py-1 text-[10px] text-primary-foreground/55">Permission scoped</span></div><div className="mt-8 rounded-xl border border-primary-foreground/12 bg-primary-foreground/[0.06] p-4 text-sm text-primary-foreground/72">Who needs support before the next placement drive?</div><div className="mt-3 rounded-xl bg-card p-5 text-foreground shadow-sm"><div className="flex items-center gap-2 text-sm font-semibold"><CirclesFour className="text-accent" />Evidence-linked answer</div><div className="mt-4 space-y-3">{["Readiness and missing evidence", "Authorized student or client records", "English, Tamil, and Tanglish"].map((item) => <div key={item} className="flex items-center gap-3 rounded-lg bg-secondary px-3 py-2.5 text-xs"><CheckCircle className="text-positive" weight="fill" />{item}</div>)}</div></div></div></div></div>
      </section>

      <Pricing catalog={catalog} error={error} retry={retry} />

      <section id="contact" className="scroll-mt-16 px-4 pb-20 pt-12 sm:px-6 lg:px-8 lg:pb-28 lg:pt-16">
        <div className="relative mx-auto grid max-w-[1400px] items-start overflow-hidden rounded-[2rem] bg-primary text-primary-foreground shadow-[0_30px_80px_hsl(var(--shadow-color)/.16)] lg:grid-cols-12">
          <div className="paper-grid pointer-events-none absolute inset-0 opacity-[0.06]" />
          <div className="relative p-7 sm:p-10 lg:col-span-5 lg:p-12 xl:p-14">
            <div className="overline !text-primary-foreground/50">Book a working session</div>
            <h2 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">Bring the workflow you want to improve.</h2>
            <p className="mt-5 max-w-xl text-sm leading-7 text-primary-foreground/65 sm:text-base">We will prepare the relevant workspace, discuss data ownership and permissions, and map a practical first rollout around your real work.</p>
            <div className="mt-9 space-y-5 border-t border-primary-foreground/12 pt-8">
              {[
                [CalendarCheck, "Your highest-value workflow", "A focused walkthrough for your industry and team roles."],
                [UsersThree, "Data and rollout fit", "Imports, existing systems, permissions, and practical onboarding."],
                [LockKey, "A clear commercial path", "The right plan, payment path, and next steps with no hidden setup."],
              ].map(([Icon, title, copy]) => <div key={title} className="flex gap-3.5"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary-foreground/10 text-accent"><Icon size={18} /></span><div><div className="text-sm font-semibold">{title}</div><p className="mt-1 text-xs leading-5 text-primary-foreground/55">{copy}</p></div></div>)}
            </div>
            <a href={`mailto:${site?.support_email || "sales@edvatiq.com"}`} className="mt-9 inline-flex text-sm font-semibold text-accent underline-offset-4 hover:underline">Prefer email? {site?.support_email || "sales@edvatiq.com"}</a>
          </div>
          <div className="relative border-t border-primary-foreground/12 p-3 sm:p-5 lg:col-span-7 lg:border-l lg:border-t-0 lg:p-6 xl:p-8"><DemoRequestForm /></div>
        </div>
      </section>
  </div>;
}

function Pricing({ catalog, error, retry }) {
  const [interval, setInterval] = useState("monthly");
  const plans = catalog?.plans || [];
  const annualSaving = Math.max(0, ...plans.map((plan) => Number(plan.annual_saving_percent || 0)));
  const gridClass = plans.length <= 1
    ? "max-w-md"
    : plans.length === 2
      ? "max-w-4xl sm:grid-cols-2"
      : plans.length === 3
        ? "max-w-6xl sm:grid-cols-2 lg:grid-cols-3"
        : plans.length === 4
          ? "sm:grid-cols-2 lg:grid-cols-4"
          : "sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5";
  return <section id="pricing" className="soft-glow relative scroll-mt-16 overflow-hidden border-y bg-card">
    <div className="paper-grid pointer-events-none absolute inset-0 opacity-[0.13] [mask-image:linear-gradient(to_bottom,black,transparent_65%)]" />
    <div className="relative mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <div className="grid gap-7 lg:grid-cols-12 lg:items-end"><div className="max-w-3xl lg:col-span-7"><div className="overline">Plans and pricing</div><h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">Choose a clear starting point.</h2><p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">Compare tax-inclusive pricing, AI credits, and practical workspace limits before creating an account.</p></div><div className="lg:col-span-4 lg:col-start-9 lg:justify-self-end"><div className="inline-flex rounded-xl border bg-card p-1 shadow-sm" role="group" aria-label="Billing period">{[["monthly", "Monthly"], ["annual", "Annual"]].map(([value, label]) => <button key={value} type="button" aria-pressed={interval === value} onClick={() => setInterval(value)} className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${interval === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{label}{value === "annual" && annualSaving > 0 && <span className={`ml-2 text-[10px] ${interval === value ? "text-primary-foreground/65" : "text-positive"}`}>save {annualSaving}%</span>}</button>)}</div></div></div>
      {error && <div className="mt-10 flex min-h-32 flex-col items-center justify-center rounded-2xl border bg-card p-6 text-center"><WarningCircle size={28} className="text-accent" /><p className="mt-3 font-semibold">{error}</p><p className="mt-1 text-sm text-muted-foreground">We will not show stale or guessed prices.</p><button type="button" onClick={retry} className="mt-4 rounded-lg border px-4 py-2 text-sm font-semibold">Try again</button></div>}
      {!catalog && !error && <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <div key={item} className="h-[440px] animate-pulse rounded-[1.35rem] border bg-card" />)}</div>}
      {catalog && <div className={`mx-auto mt-10 grid items-stretch gap-4 ${gridClass}`}>{plans.map((plan, index) => <PlanCard key={plan.id} plan={plan} index={index} totalPlans={plans.length} interval={interval} paymentAvailable={catalog.payment_available} />)}</div>}
      <div className="mt-7 flex flex-col gap-2 border-t pt-5 text-xs leading-5 text-muted-foreground sm:flex-row sm:items-center sm:justify-between"><span>Paid signup covers the selected first term. Renewals are managed from Plan &amp; billing.</span><span className="inline-flex items-center gap-2 font-medium text-foreground"><CheckCircle className="text-positive" weight="fill" />Published, tax-inclusive pricing</span></div>
    </div>
  </section>;
}

function PlanCard({ plan, index, totalPlans, interval, paymentAvailable }) {
  const quote = interval === "annual" ? plan.annual_quote : plan.monthly_quote;
  const isTrial = plan.signup_mode === "trial";
  const isContact = plan.signup_mode === "contact";
  const configuredPoints = [
    plan.ai_credits != null && `${Number(plan.ai_credits).toLocaleString("en-IN")} AI credits per cycle`,
    plan.location_limit != null && `Up to ${Number(plan.location_limit).toLocaleString("en-IN")} location${Number(plan.location_limit) === 1 ? "" : "s"}`,
    plan.employee_limit != null && `Up to ${Number(plan.employee_limit).toLocaleString("en-IN")} team members`,
    plan.client_limit != null && `Up to ${Number(plan.client_limit).toLocaleString("en-IN")} people records`,
  ].filter(Boolean).slice(0, 4);
  const points = configuredPoints.length ? configuredPoints : [
    "Tailored workspace limits",
    "Integration and rollout planning",
    "Governance and access design",
  ];
  const path = `/register?plan=${encodeURIComponent(plan.id)}&interval=${interval}`;
  const expandOnTwoColumns = isContact && totalPlans % 2 === 1 && index === totalPlans - 1;
  return <article className={`group relative flex min-h-[420px] flex-col overflow-hidden rounded-[1.35rem] border bg-card p-5 shadow-[0_12px_35px_hsl(var(--shadow-color)/.055)] transition-[transform,box-shadow] hover:-translate-y-1 hover:shadow-[0_20px_45px_hsl(var(--shadow-color)/.09)] sm:p-6 ${expandOnTwoColumns ? "sm:col-span-2 lg:col-span-1" : ""} ${plan.recommended ? "border-primary ring-1 ring-primary/15" : ""}`}>
    {plan.recommended && <div className="absolute inset-x-0 top-0 h-1 bg-accent" />}
    <div className="flex items-center justify-between gap-3"><span className="overline">Plan {String(index + 1).padStart(2, "0")}</span>{plan.recommended && <span className="rounded-full bg-primary px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-primary-foreground">Recommended</span>}</div>
    <div className="mt-5"><h3 className="text-2xl font-semibold">{plan.name}</h3><p className="mt-2 min-h-10 text-xs leading-5 text-muted-foreground">{plan.description}</p></div>
    <div className="mt-7"><div className="text-4xl font-semibold tracking-[-.04em]">{isTrial ? "Free" : isContact ? "Custom" : quote ? money(quote.total_paise) : "Unavailable"}</div><div className="mt-2 text-xs text-muted-foreground">{isTrial ? `${plan.trial_days || 30}-day access` : isContact ? "Built around your requirements" : quote ? `${interval === "annual" ? "Billed annually" : "Billed monthly"} / tax included` : `No ${interval} price is published`}</div>{!isTrial && !isContact && quote?.tax_paise > 0 && <div className="mt-1 text-[11px] text-muted-foreground">Includes {money(quote.tax_paise)} GST</div>}{quote && interval === "annual" && plan.annual_saving_percent > 0 && <span className="mt-3 inline-flex rounded-full bg-positive/10 px-2 py-1 text-[10px] font-semibold text-positive">Save {plan.annual_saving_percent}%</span>}</div>
    <div className="mt-7 border-t pt-5"><div className="overline">Included</div><ul className="mt-4 space-y-3 text-xs">{points.map((point) => <li key={point} className="flex gap-2.5 leading-5"><span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-positive/10"><Check size={10} className="text-positive" weight="bold" /></span>{point}</li>)}</ul></div>
    <div className="mt-auto pt-7">{isContact
      ? <DemoLink className="flex h-11 items-center justify-center rounded-xl border text-sm font-semibold hover:bg-secondary">Talk to sales</DemoLink>
      : !isTrial && (!paymentAvailable || !quote)
        ? <button type="button" disabled className="h-11 w-full rounded-xl border bg-secondary text-sm font-semibold text-muted-foreground">Checkout unavailable</button>
        : <Link to={path} aria-label={isTrial ? `Start ${plan.name}` : `Pay and register with ${plan.name}`} className={`flex h-11 items-center justify-center gap-2 rounded-xl text-sm font-semibold ${plan.recommended ? "bg-primary text-primary-foreground" : "border hover:bg-secondary"}`}>{isTrial ? "Start free" : "Pay and register"} <ArrowRight /></Link>}</div>
  </article>;
}

function ProductPreview() {
  const [mode, setMode] = useState("college");
  const college = mode === "college";
  return <div className="relative lg:col-span-6 lg:col-start-7 xl:col-span-7">
    <div className="absolute -inset-8 rounded-full bg-accent/8 blur-3xl" />
    <div className="relative overflow-hidden rounded-[1.6rem] border bg-card p-2 shadow-[0_32px_90px_hsl(var(--shadow-color)/.14)]">
      <div className="flex min-h-14 flex-wrap items-center gap-2 rounded-t-[1.15rem] border-b bg-surface-subtle px-3 py-2 sm:px-4"><BrandLogo showName={false} markClassName="h-8 w-8 rounded-lg" /><div className="flex rounded-lg border bg-card p-1">{[["college", "College"], ["business", "Business"]].map(([value, label]) => <button key={value} type="button" onClick={() => setMode(value)} className={`rounded-md px-3 py-1.5 text-[10px] font-semibold ${mode === value ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>{label}</button>)}</div><span className="ml-auto hidden text-[10px] font-semibold text-muted-foreground sm:block">{college ? "Placement command center" : "Operations command center"}</span></div>
      <div className="grid min-h-[440px] sm:grid-cols-[8.5rem_1fr]">
        <aside className="hidden border-r bg-surface-subtle p-3 sm:block"><div className="space-y-1">{(college ? [[CirclesFour, "Overview"], [Student, "Students"], [Briefcase, "Placements"], [Code, "Coding"], [ChartLineUp, "Readiness"]] : [[CirclesFour, "Home"], [UsersThree, "Clients"], [CalendarCheck, "Calendar"], [ChartLineUp, "Sales"], [Briefcase, "Team"]]).map(([Icon, label], index) => <div key={label} className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-[10px] font-semibold ${index === 0 ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"}`}><Icon size={14} />{label}</div>)}</div><div className="mt-32 rounded-xl bg-primary p-3 text-primary-foreground"><Sparkle className="text-accent" weight="fill" /><div className="mt-2 text-[9px] font-semibold">Ask Edvatiq</div><div className="mt-1 text-[8px] text-primary-foreground/55">Grounded in your records</div></div></aside>
        <div className="min-w-0 p-4 sm:p-5">{college ? <CollegePreview /> : <BusinessPreview />}</div>
      </div>
    </div>
  </div>;
}

function CollegePreview() {
  return <><div className="flex items-end justify-between"><div><div className="text-[9px] font-semibold uppercase tracking-[.16em] text-muted-foreground">Good evening, Kavya.</div><div className="mt-1 text-sm font-semibold">Placement readiness</div></div><span className="rounded-lg border px-2 py-1 text-[9px]">2027 batch</span></div><div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">{[["Students", "110"], ["Ready", "46"], ["Need support", "24"], ["Placed", "31"]].map(([label, value]) => <div key={label} className="rounded-xl border p-3"><div className="text-[8px] text-muted-foreground">{label}</div><div className="mt-2 text-lg font-semibold">{value}</div></div>)}</div><div className="mt-3 grid gap-3 lg:grid-cols-2"><div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Readiness distribution</div><div className="mt-4 flex items-center gap-4"><div className="grid h-24 w-24 shrink-0 place-items-center rounded-full" style={{ background: "conic-gradient(hsl(var(--chart-2)) 0 42%, hsl(var(--chart-3)) 42% 78%, hsl(var(--muted)) 78%)" }}><div className="grid h-14 w-14 place-items-center rounded-full bg-card text-xs font-semibold">73%</div></div><div className="space-y-2 text-[9px]">{[["Ready", "46"], ["Developing", "40"], ["Support", "24"]].map(([label, value], index) => <div key={label} className="flex min-w-24 items-center justify-between gap-3"><span className="flex items-center gap-1.5"><i className={`h-2 w-2 rounded-full ${index === 0 ? "bg-[hsl(var(--chart-2))]" : index === 1 ? "bg-[hsl(var(--chart-3))]" : "bg-muted"}`} />{label}</span><strong>{value}</strong></div>)}</div></div></div><div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Placement funnel</div><div className="mt-4 space-y-2.5">{[["Eligible", 92], ["Applied", 72], ["Interview", 46], ["Offered", 31]].map(([label, width]) => <div key={label}><div className="flex justify-between text-[8px]"><span>{label}</span><strong>{width}</strong></div><div className="mt-1 h-2 rounded-full bg-secondary"><div className="h-full rounded-full bg-primary" style={{ width: `${width}%` }} /></div></div>)}</div></div></div><div className="mt-3 flex items-center justify-between rounded-xl border bg-accent/5 p-3"><div><div className="text-[9px] font-semibold">3 students need eligibility review</div><div className="mt-1 text-[8px] text-muted-foreground">Missing attendance or coding evidence</div></div><ArrowRight className="text-accent" /></div></>;
}

function BusinessPreview() {
  return <><div className="flex items-end justify-between"><div><div className="text-[9px] font-semibold uppercase tracking-[.16em] text-muted-foreground">Good evening, Demo.</div><div className="mt-1 text-sm font-semibold">Business position</div></div><span className="rounded-lg border px-2 py-1 text-[9px]">30 days</span></div><div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">{[["Outstanding", "INR 1.3K"], ["Collected", "INR 8.4K"], ["Active", "87"], ["Today", "12"]].map(([label, value]) => <div key={label} className="rounded-xl border p-3"><div className="text-[8px] text-muted-foreground">{label}</div><div className="mt-2 text-base font-semibold">{value}</div></div>)}</div><div className="mt-3 grid gap-3 lg:grid-cols-[1.35fr_.65fr]"><div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Collections trend</div><div className="mt-7 flex h-32 items-end gap-2">{[34, 54, 44, 72, 58, 84, 76, 92].map((height, index) => <div key={`${height}-${index}`} className="flex-1 rounded-t-md bg-[hsl(var(--chart-2)/.22)]" style={{ height: `${height}%` }}><div className="h-full rounded-t-md bg-[hsl(var(--chart-2))]" style={{ opacity: 0.38 + index * 0.06 }} /></div>)}</div></div><div className="rounded-xl border p-4"><div className="text-[10px] font-semibold">Needs attention</div>{["2 renewals", "1 payment", "3 follow-ups"].map((item) => <div key={item} className="mt-3 flex items-center gap-2 text-[9px]"><span className="h-6 w-6 rounded-lg bg-secondary" /><span>{item}</span></div>)}</div></div><div className="mt-3 flex items-center justify-between rounded-xl border bg-accent/5 p-3"><div><div className="text-[9px] font-semibold">Your team is caught up on urgent work</div><div className="mt-1 text-[8px] text-muted-foreground">Next review at 4:30 PM</div></div><CheckCircle className="text-positive" weight="fill" /></div></>;
}
