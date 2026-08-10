import React from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, Barbell, CalendarCheck, ChartLineUp, CheckCircle, CirclesFour,
  Command, Cube, GraduationCap, LockKey, Scissors, Sparkle, Stethoscope, UsersThree,
} from "@phosphor-icons/react";

const industries = [
  {
    icon: Barbell,
    title: "Gym and fitness",
    copy: "Memberships, check-ins, coaching, classes, progress, diets, and equipment in one client workspace.",
    accent: "bg-[hsl(var(--chart-2)/.12)] text-[hsl(var(--chart-2))]",
  },
  {
    icon: Scissors,
    title: "Salon and spa",
    copy: "Bookings, walk-ins, preferences, service history, checkout, follow-ups, and staff performance.",
    accent: "bg-[hsl(var(--chart-4)/.12)] text-[hsl(var(--chart-4))]",
  },
  {
    icon: Stethoscope,
    title: "Outpatient clinic",
    copy: "Patient queue, encounters, prescriptions, labs, pharmacy, documents, and permission-separated care records.",
    accent: "bg-[hsl(var(--chart-1)/.12)] text-[hsl(var(--chart-1))]",
  },
  {
    icon: GraduationCap,
    title: "College and higher education",
    copy: "Admissions, programs, cohorts, course allocation, attendance, assessments, student fees, and academic operations.",
    accent: "bg-[hsl(var(--chart-3)/.12)] text-[hsl(var(--chart-3))]",
  },
];

const capabilities = [
  [UsersThree, "Client intelligence", "Know the relationship, history, progress, balance, and next action before every interaction."],
  [CalendarCheck, "Connected operations", "Appointments, work queues, sales, stock, and team responsibilities stay in context."],
  [Sparkle, "Grounded business AI", "Ask in English, Tamil, or Tanglish and receive answers from records you are allowed to access."],
  [LockKey, "Access by responsibility", "Roles control actions while location and client scopes control which records each person can see."],
];

export default function Landing() {
  return <div className="marketing-site min-h-screen overflow-hidden bg-background text-foreground">
    <header className="sticky top-0 z-50 border-b bg-background/82 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2.5" aria-label="Edvatiq home">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-sm font-bold text-accent-foreground shadow-sm">E</span>
          <span className="font-marketing text-xl font-semibold">Edvatiq</span>
        </Link>
        <nav className="hidden items-center gap-7 text-sm font-medium text-muted-foreground md:flex" aria-label="Primary navigation">
          <a className="transition-colors hover:text-foreground" href="#platform">Platform</a>
          <a className="transition-colors hover:text-foreground" href="#industries">Industries</a>
          <a className="transition-colors hover:text-foreground" href="#ai">Business AI</a>
        </nav>
        <div className="flex items-center gap-1 sm:gap-2">
          <Link to="/login" className="rounded-xl px-3 py-2 text-sm font-semibold transition-colors hover:bg-secondary sm:px-4">Sign in</Link>
          <Link to="/register" className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition-transform hover:-translate-y-0.5 sm:px-5">Start free</Link>
        </div>
      </div>
    </header>

    <main>
      <section className="soft-glow relative border-b">
        <div className="paper-grid absolute inset-0 opacity-[0.32] [mask-image:linear-gradient(to_bottom,black,transparent_88%)]" />
        <div className="relative mx-auto grid min-h-[calc(100dvh-4rem)] max-w-[1440px] items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-20">
          <div className="lg:col-span-6 xl:col-span-5">
            <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs font-semibold shadow-sm">
              <Sparkle className="text-accent" weight="fill" />
              Operations OS for growing teams
            </div>
            <h1 className="mt-7 max-w-3xl text-[clamp(3.15rem,6.2vw,6.25rem)] font-semibold leading-[0.94] tracking-[-0.055em]">
              Run the work.<br /><span className="text-accent">Know every relationship.</span>
            </h1>
            <p className="mt-7 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
              Edvatiq connects people, schedules, finance, operations, teams, and grounded AI in one calm workspace built for Indian organizations.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className="inline-flex h-12 items-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/10 transition-transform hover:-translate-y-0.5">
                Create your workspace <ArrowRight />
              </Link>
              <Link to="/login" className="inline-flex h-12 items-center rounded-xl border bg-card px-6 text-sm font-semibold shadow-sm transition-colors hover:bg-secondary">
                Sign in to Edvatiq
              </Link>
            </div>
            <div className="mt-9 flex flex-wrap gap-x-6 gap-y-3 text-xs font-medium text-muted-foreground">
              {['30-day trial', 'No card required', 'Gym, Salon, Clinic, and College'].map((item) => <span key={item} className="inline-flex items-center gap-2"><CheckCircle className="text-positive" weight="fill" />{item}</span>)}
            </div>
          </div>

          <ProductPreview />
        </div>
      </section>

      <section id="platform" className="mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
        <div className="grid gap-10 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-5">
            <div className="overline">One connected workspace</div>
            <h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">Less switching. More context.</h2>
          </div>
          <p className="max-w-2xl text-base leading-7 text-muted-foreground lg:col-span-6 lg:col-start-7">Every screen is shaped by the user’s role, permitted locations, and business type. Your front desk sees today’s work; owners see performance; specialists see the people assigned to them.</p>
        </div>
        <div className="mt-12 grid overflow-hidden rounded-2xl border bg-border md:grid-cols-2 xl:grid-cols-4">
          {capabilities.map(([Icon, title, copy]) => <article key={title} className="bg-card p-6 md:p-7">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary text-primary"><Icon size={20} /></span>
            <h3 className="mt-6 text-xl font-semibold">{title}</h3>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{copy}</p>
          </article>)}
        </div>
      </section>

      <section id="industries" className="border-y bg-primary text-primary-foreground">
        <div className="mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
          <div className="grid gap-8 lg:grid-cols-12 lg:items-end">
            <div className="lg:col-span-7"><div className="overline !text-primary-foreground/50">Industry-aware by design</div><h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">The same quality of platform, shaped around different work.</h2></div>
            <p className="text-sm leading-6 text-primary-foreground/60 lg:col-span-4 lg:col-start-9">Shared foundations with purpose-built operational spaces and no generic module clutter.</p>
          </div>
          <div className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {industries.map(({ icon: Icon, title, copy, accent }) => <article key={title} className="group rounded-2xl border border-primary-foreground/12 bg-primary-foreground/[0.045] p-6 transition-transform hover:-translate-y-1 sm:p-8">
              <span className={`grid h-11 w-11 place-items-center rounded-xl ${accent}`}><Icon size={23} weight="duotone" /></span>
              <h3 className="mt-8 text-2xl font-semibold">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-primary-foreground/58">{copy}</p>
              <div className="mt-8 flex items-center gap-2 text-xs font-semibold text-accent">Explore the workflow <ArrowRight className="transition-transform group-hover:translate-x-1" /></div>
            </article>)}
          </div>
        </div>
      </section>

      <section id="ai" className="mx-auto grid max-w-[1440px] gap-12 px-4 py-20 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-28">
        <div className="lg:col-span-5">
          <div className="overline">Edvatiq AI</div>
          <h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">Answers grounded in the business you actually run.</h2>
          <p className="mt-5 text-base leading-7 text-muted-foreground">Ask naturally, inspect the records behind an answer, and review important actions before anything changes.</p>
        </div>
        <div className="lg:col-span-6 lg:col-start-7">
          <div className="surface-card overflow-hidden p-2 shadow-xl shadow-primary/5">
            <div className="rounded-xl bg-primary p-5 text-primary-foreground sm:p-7">
              <div className="flex items-center justify-between"><span className="inline-flex items-center gap-2 text-sm font-semibold"><Sparkle className="text-accent" weight="fill" />Ask Edvatiq</span><span className="rounded-full border border-primary-foreground/15 px-2.5 py-1 text-[10px] text-primary-foreground/55">Permission scoped</span></div>
              <div className="mt-8 rounded-xl border border-primary-foreground/12 bg-primary-foreground/[0.06] p-4 text-sm text-primary-foreground/72">Which clients need my attention today?</div>
              <div className="mt-3 rounded-xl bg-card p-5 text-foreground shadow-sm">
                <div className="flex items-center gap-2 text-sm font-semibold"><CirclesFour className="text-accent" />Live business records</div>
                <div className="mt-4 space-y-3">{["Evidence-linked insights", "Authorized profile actions", "English, Tamil, and Tanglish"].map((item) => <div key={item} className="flex items-center gap-3 rounded-lg bg-secondary px-3 py-2.5 text-xs"><CheckCircle className="text-positive" weight="fill" />{item}</div>)}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-4 pb-20 sm:px-6 lg:px-8 lg:pb-28">
        <div className="relative mx-auto flex max-w-[1400px] flex-col items-start justify-between gap-8 overflow-hidden rounded-3xl bg-accent p-8 text-accent-foreground sm:p-12 lg:flex-row lg:items-end lg:p-16">
          <div className="paper-grid absolute inset-0 opacity-15" />
          <div className="relative max-w-3xl"><div className="overline !text-accent-foreground/55">Start with your real workflow</div><h2 className="mt-3 text-4xl font-semibold leading-tight sm:text-5xl">Give your team one place to run the day.</h2></div>
          <Link to="/register" className="relative inline-flex h-12 shrink-0 items-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-lg transition-transform hover:-translate-y-0.5">Start free <ArrowRight /></Link>
        </div>
      </section>
    </main>

    <footer className="border-t">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-4 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <span>© 2026 Edvatiq Business OS</span>
        <span>Built for local businesses in India.</span>
      </div>
    </footer>
  </div>;
}

function ProductPreview() {
  return <div className="relative lg:col-span-6 lg:col-start-7 xl:col-span-7">
    <div className="absolute -inset-8 rounded-full bg-accent/8 blur-3xl" />
    <div className="relative overflow-hidden rounded-[1.6rem] border bg-card p-2 shadow-[0_32px_90px_hsl(var(--shadow-color)/.14)]">
      <div className="flex h-12 items-center gap-3 rounded-t-[1.15rem] border-b bg-surface-subtle px-4">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-primary text-[10px] font-bold text-primary-foreground">E</span>
        <span className="text-xs font-semibold">Business workspace</span>
        <div className="ml-auto hidden h-8 w-44 items-center gap-2 rounded-lg border bg-card px-3 text-[10px] text-muted-foreground sm:flex"><Command size={12} />Search or open</div>
        <span className="h-7 w-7 rounded-full bg-accent/18" />
      </div>
      <div className="grid min-h-[440px] sm:grid-cols-[9rem_1fr]">
        <aside className="hidden border-r bg-surface-subtle p-3 sm:block">
          <div className="space-y-1">{[[CirclesFour, "Home"], [UsersThree, "Clients"], [CalendarCheck, "Calendar"], [ChartLineUp, "Sales"], [Cube, "Inventory"]].map(([Icon, label], index) => <div key={label} className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-[10px] font-semibold ${index === 0 ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"}`}><Icon size={14} />{label}</div>)}</div>
          <div className="mt-36 rounded-xl border bg-card p-3"><div className="h-1.5 w-10 rounded-full bg-accent" /><div className="mt-2 h-1.5 w-full rounded-full bg-secondary" /><div className="mt-1.5 h-1.5 w-2/3 rounded-full bg-secondary" /></div>
        </aside>
        <div className="min-w-0 p-4 sm:p-5">
          <div className="flex items-end justify-between"><div><div className="h-2 w-20 rounded-full bg-accent/55" /><div className="mt-3 h-5 w-36 rounded-md bg-foreground/85" /></div><div className="h-8 w-20 rounded-lg border bg-card" /></div>
          <div className="mt-5 grid grid-cols-2 gap-2.5 lg:grid-cols-4">{[1, 2, 3, 4].map((item) => <div key={item} className="rounded-xl border bg-card p-3"><div className="h-1.5 w-12 rounded-full bg-muted-foreground/25" /><div className="mt-3 h-5 w-16 rounded-md bg-foreground/80" /><div className="mt-3 h-1.5 w-10 rounded-full bg-positive/35" /></div>)}</div>
          <div className="mt-3 grid gap-3 lg:grid-cols-12">
            <div className="rounded-xl border bg-card p-4 lg:col-span-8">
              <div className="flex justify-between"><div><div className="h-2 w-24 rounded-full bg-foreground/75" /><div className="mt-2 h-1.5 w-36 rounded-full bg-muted-foreground/20" /></div><div className="h-6 w-16 rounded-lg bg-secondary" /></div>
              <div className="mt-8 flex h-32 items-end gap-2">{[42, 63, 48, 78, 57, 88, 70, 92, 76, 84].map((height, index) => <div key={`${height}-${index}`} className="flex-1 rounded-t-md bg-[hsl(var(--chart-2)/.2)]" style={{ height: `${height}%` }}><div className="h-full rounded-t-md bg-[hsl(var(--chart-2))]" style={{ opacity: 0.35 + index * 0.05 }} /></div>)}</div>
            </div>
            <div className="rounded-xl border bg-card p-4 lg:col-span-4"><div className="h-2 w-20 rounded-full bg-foreground/75" />{[1, 2, 3].map((item) => <div key={item} className="mt-4 flex items-center gap-2"><span className="h-7 w-7 rounded-lg bg-secondary" /><span className="flex-1"><span className="block h-1.5 w-full rounded bg-muted-foreground/20" /><span className="mt-1.5 block h-1.5 w-2/3 rounded bg-muted-foreground/12" /></span></div>)}</div>
          </div>
          <div className="mt-3 rounded-xl border bg-card p-4"><div className="flex items-center gap-2"><div className="h-2 w-24 rounded-full bg-foreground/75" /><div className="ml-auto h-6 w-14 rounded-md bg-secondary" /></div><div className="mt-4 grid grid-cols-3 gap-3">{[1, 2, 3].map((item) => <div key={item}><div className="h-1.5 w-full rounded bg-muted-foreground/16" /><div className="mt-2 h-1.5 w-2/3 rounded bg-muted-foreground/10" /></div>)}</div></div>
        </div>
      </div>
    </div>
  </div>;
}
