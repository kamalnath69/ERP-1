import React, { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence } from "motion/react";
import { ArrowRight, Check, CheckCircle, WarningCircle } from "@phosphor-icons/react";

import { m, Reveal, Stagger, StaggerItem } from "./LandingMotion";

const money = (paise) => new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
}).format(Number(paise || 0) / 100);

export default function PricingSection({ catalog, error, retry }) {
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
  return <section id="pricing" className="landing-pricing relative scroll-mt-20 overflow-hidden border-y border-primary/10 bg-card">
    <div className="landing-grid pointer-events-none absolute inset-0 opacity-40 [mask-image:linear-gradient(to_bottom,black,transparent_72%)]" />
    <div className="relative mx-auto max-w-[1440px] px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <Reveal className="grid gap-7 lg:grid-cols-12 lg:items-end">
        <div className="max-w-3xl lg:col-span-7"><div className="overline">Plans and pricing</div><h2 className="landing-section-title mt-3">Choose a clear starting point.</h2><p className="mt-4 max-w-2xl text-base leading-8 text-muted-foreground">Compare tax-inclusive pricing, AI credits, and practical workspace limits before creating an account.</p></div>
        <div className="lg:col-span-4 lg:col-start-9 lg:justify-self-end"><div className="inline-flex rounded-xl border bg-card p-1 shadow-sm" role="group" aria-label="Billing period">{[["monthly", "Monthly"], ["annual", "Annual"]].map(([value, label]) => <button key={value} type="button" aria-pressed={interval === value} onClick={() => setInterval(value)} className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${interval === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{label}{value === "annual" && annualSaving > 0 && <span className={`ml-2 text-[10px] ${interval === value ? "text-primary-foreground/65" : "text-positive"}`}>save {annualSaving}%</span>}</button>)}</div></div>
      </Reveal>
      {error && <div className="mt-10 flex min-h-32 flex-col items-center justify-center rounded-2xl border bg-card p-6 text-center"><WarningCircle size={28} className="text-accent" /><p className="mt-3 font-semibold">{error}</p><p className="mt-1 text-sm text-muted-foreground">We will not show stale or guessed prices.</p><button type="button" onClick={retry} className="mt-4 rounded-lg border px-4 py-2 text-sm font-semibold">Try again</button></div>}
      {!catalog && !error && <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="Loading plans">{[1, 2, 3, 4].map((item) => <div key={item} className="h-[440px] animate-pulse rounded-[1.5rem] border bg-card" />)}</div>}
      {catalog && <Stagger className={`mx-auto mt-10 grid items-stretch gap-4 ${gridClass}`}>{plans.map((plan, index) => <StaggerItem key={plan.id} className={`h-full ${plan.signup_mode === "contact" && plans.length % 2 === 1 && index === plans.length - 1 ? "sm:col-span-2 lg:col-span-1" : ""}`}><PlanCard plan={plan} index={index} interval={interval} paymentAvailable={catalog.payment_available} /></StaggerItem>)}</Stagger>}
      <div className="mt-7 flex flex-col gap-2 border-t pt-5 text-xs leading-5 text-muted-foreground sm:flex-row sm:items-center sm:justify-between"><span>Paid signup covers the selected first term. Renewals are managed from Plan &amp; billing.</span><span className="inline-flex items-center gap-2 font-medium text-foreground"><CheckCircle className="text-positive" weight="fill" />Published, tax-inclusive pricing</span></div>
    </div>
  </section>;
}

function PlanCard({ plan, index, interval, paymentAvailable }) {
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
  const price = isTrial ? "Free" : isContact ? "Custom" : quote ? money(quote.total_paise) : "Unavailable";
  return <article className={`group relative flex h-full min-h-[420px] flex-col overflow-hidden rounded-[1.5rem] border bg-card p-5 shadow-[0_12px_35px_hsl(var(--shadow-color)/.055)] transition-[transform,box-shadow] hover:-translate-y-1 hover:shadow-[0_20px_45px_hsl(var(--shadow-color)/.09)] sm:p-6 ${plan.recommended ? "border-primary ring-1 ring-primary/15" : ""}`}>
    {plan.recommended && <div className="absolute inset-x-0 top-0 h-1 bg-accent" />}
    <div className="flex items-center justify-between gap-3"><span className="overline">Plan {String(index + 1).padStart(2, "0")}</span>{plan.recommended && <span className="rounded-full bg-primary px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-primary-foreground">Recommended</span>}</div>
    <div className="mt-5"><h3 className="text-2xl font-semibold">{plan.name}</h3><p className="mt-2 min-h-10 text-xs leading-5 text-muted-foreground">{plan.description}</p></div>
    <div className="mt-7 min-h-24">
      <AnimatePresence mode="wait" initial={false}><m.div key={`${interval}-${price}`} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.2 }}><div className="text-4xl font-semibold tracking-[-.04em]">{price}</div><div className="mt-2 text-xs text-muted-foreground">{isTrial ? `${plan.trial_days || 30}-day access` : isContact ? "Built around your requirements" : quote ? `${interval === "annual" ? "Billed annually" : "Billed monthly"} / tax included` : `No ${interval} price is published`}</div>{!isTrial && !isContact && quote?.tax_paise > 0 && <div className="mt-1 text-[11px] text-muted-foreground">Includes {money(quote.tax_paise)} GST</div>}{quote && interval === "annual" && plan.annual_saving_percent > 0 && <span className="mt-3 inline-flex rounded-full bg-positive/10 px-2 py-1 text-[10px] font-semibold text-positive">Save {plan.annual_saving_percent}%</span>}</m.div></AnimatePresence>
    </div>
    <div className="mt-7 border-t pt-5"><div className="overline">Included</div><ul className="mt-4 space-y-3 text-xs">{points.map((point) => <li key={point} className="flex gap-2.5 leading-5"><span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-positive/10"><Check size={10} className="text-positive" weight="bold" /></span>{point}</li>)}</ul></div>
    <div className="mt-auto pt-7">{isContact
      ? <Link to="/#contact" className="flex h-11 items-center justify-center rounded-xl border text-sm font-semibold hover:bg-secondary">Talk to sales</Link>
      : !isTrial && (!paymentAvailable || !quote)
        ? <button type="button" disabled className="h-11 w-full rounded-xl border bg-secondary text-sm font-semibold text-muted-foreground">Checkout unavailable</button>
        : <Link to={path} aria-label={isTrial ? `Start ${plan.name}` : `Pay and register with ${plan.name}`} className={`flex h-11 items-center justify-center gap-2 rounded-xl text-sm font-semibold ${plan.recommended ? "bg-primary text-primary-foreground" : "border hover:bg-secondary"}`}>{isTrial ? "Start free" : "Pay and register"} <ArrowRight /></Link>}</div>
  </article>;
}
