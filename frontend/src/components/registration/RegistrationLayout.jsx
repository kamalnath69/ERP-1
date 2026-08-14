import React from "react";
import { Link } from "react-router-dom";
import { Check, LockKey, ShieldCheck } from "@phosphor-icons/react";

import BrandLogo from "@/components/brand/BrandLogo";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export const registrationSteps = ["Plan", "Workspace", "Owner", "Review", "Payment"];

export function RegistrationShell({ children, currentStep = 1 }) {
  return <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,hsl(var(--accent)/0.08),transparent_34rem),linear-gradient(180deg,hsl(var(--background)),hsl(var(--secondary)/0.28))]">
    <a href="#registration-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2">Skip to registration</a>
    <header className="border-b bg-background/90 backdrop-blur-xl">
      <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link to="/" aria-label="Edvatiq home"><BrandLogo /></Link>
        <p className="text-xs text-muted-foreground sm:text-sm">Already have a workspace? <Link to="/login" className="font-semibold text-foreground hover:text-primary">Sign in</Link></p>
      </div>
    </header>
    <main id="registration-content" className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
      <RegistrationStepper currentStep={currentStep} />
      {children}
    </main>
  </div>;
}

export function RegistrationStepper({ currentStep }) {
  const currentLabel = registrationSteps[Math.max(0, Math.min(registrationSteps.length - 1, currentStep - 1))];
  return <nav aria-label="Registration progress" className="mb-6 sm:mb-8">
    <div className="sm:hidden">
      <div className="flex items-center justify-between text-xs"><span className="font-semibold">{currentLabel}</span><span className="text-muted-foreground">Step {currentStep} of {registrationSteps.length}</span></div>
      <div className="mt-3 grid grid-cols-5 gap-1.5">{registrationSteps.map((label, index) => <span key={label} className={cn("h-1 rounded-full", index < currentStep ? "bg-primary" : "bg-border")}><span className="sr-only">{label}</span></span>)}</div>
    </div>
    <ol className="mx-auto hidden max-w-4xl items-center sm:flex">
      {registrationSteps.map((label, index) => {
        const number = index + 1;
        const complete = number < currentStep;
        const active = number === currentStep;
        return <li key={label} className={cn("flex items-center", index < registrationSteps.length - 1 && "flex-1")} aria-current={active ? "step" : undefined}>
          <div className="flex items-center gap-2.5">
            <span className={cn(
              "grid h-7 w-7 shrink-0 place-items-center rounded-full border text-[11px] font-bold",
              complete && "border-primary bg-primary text-primary-foreground",
              active && "border-primary bg-card text-primary ring-4 ring-primary/10",
              !complete && !active && "bg-card text-muted-foreground",
            )}>{complete ? <Check size={13} weight="bold" /> : number}</span>
            <span className={cn("text-xs font-semibold", active ? "text-foreground" : "text-muted-foreground")}>{label}</span>
          </div>
          {index < registrationSteps.length - 1 && <span className={cn("mx-3 h-px flex-1", complete ? "bg-primary" : "bg-border")} />}
        </li>;
      })}
    </ol>
  </nav>;
}

export function RegistrationPanel({ children, aside, wide = false }) {
  return <div className={cn("mx-auto grid items-start gap-5", wide ? "max-w-6xl" : "max-w-5xl", aside && "lg:grid-cols-[minmax(0,1fr)_19rem]")}>
    <section className="min-w-0 rounded-2xl border bg-card p-5 shadow-[0_18px_55px_hsl(var(--shadow-color)/0.06)] sm:p-7 lg:p-8">{children}</section>
    {aside && <aside className="min-w-0 lg:sticky lg:top-6">{aside}</aside>}
  </div>;
}

export function CheckoutSummary({ plan, quote, interval, money, organizationName, className }) {
  if (!plan) return null;
  const trial = plan.signup_mode === "trial";
  return <div className={cn("rounded-2xl border bg-card p-5 shadow-sm", className)}>
    <div className="overline">Order summary</div>
    <div className="mt-3 flex items-start justify-between gap-4">
      <div className="min-w-0"><div className="truncate font-semibold">{plan.name}</div><div className="mt-1 text-xs text-muted-foreground">{trial ? `${plan.trial_days || 30}-day trial` : `${interval === "annual" ? "Annual" : "Monthly"} term`}</div></div>
      <div className="shrink-0 text-right font-semibold">{trial ? "Free" : quote ? money(quote.total_paise) : "Unavailable"}</div>
    </div>
    {organizationName && <div className="mt-4 border-t pt-4"><div className="text-[11px] uppercase tracking-wider text-muted-foreground">Workspace</div><div className="mt-1 truncate text-sm font-medium">{organizationName}</div></div>}
    {!trial && quote && <div className="mt-4 space-y-2 border-t pt-4 text-xs">
      <div className="flex justify-between gap-4 text-muted-foreground"><span>Plan fee</span><span>{money(quote.subtotal_paise)}</span></div>
      <div className="flex justify-between gap-4 text-muted-foreground"><span>GST</span><span>{money(quote.tax_paise)}</span></div>
      <div className="flex justify-between gap-4 border-t pt-3 text-sm font-semibold"><span>Total</span><span>{money(quote.total_paise)}</span></div>
    </div>}
  </div>;
}

export function PaymentSecurityNote({ provider }) {
  return <div className="flex items-start gap-3 rounded-xl border bg-secondary/45 p-4 text-xs leading-5 text-muted-foreground"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-card text-primary shadow-sm"><LockKey /></span><span>Payment details are collected by {provider === "cashfree" ? "Cashfree" : provider === "razorpay" ? "Razorpay" : "the secure payment provider"}. Edvatiq confirms the provider order before creating your workspace.</span></div>;
}

export function CancelCheckoutDialog({ open, onOpenChange, loading, onConfirm }) {
  return <Dialog open={open} onOpenChange={(value) => { if (!loading) onOpenChange(value); }}>
    <DialogContent>
      <DialogHeader><DialogTitle>Cancel this checkout?</DialogTitle><DialogDescription>The current payment session will stop being usable. Your non-sensitive registration details will remain available, but you must enter the owner password again.</DialogDescription></DialogHeader>
      <DialogFooter className="gap-2 sm:space-x-0"><Button type="button" variant="outline" disabled={loading} onClick={() => onOpenChange(false)}>Keep checkout</Button><Button type="button" variant="destructive" loading={loading} loadingText="Cancelling..." onClick={onConfirm}>Cancel and edit</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
