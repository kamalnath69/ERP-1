import React from "react";
import { Link } from "react-router-dom";
import {
  Buildings, Check, CheckCircle, CreditCard, LockKey, PencilSimple, Sparkle, UserCircle,
} from "@phosphor-icons/react";

import BrandLogo from "@/components/brand/BrandLogo";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export const registrationSteps = ["Plan", "Workspace", "Owner", "Review"];

const stepMeta = [
  { label: "Plan", description: "Choose access", icon: CreditCard },
  { label: "Workspace", description: "Organization details", icon: Buildings },
  { label: "Owner", description: "Secure the owner", icon: UserCircle },
  { label: "Review", description: "Confirm and pay", icon: CheckCircle },
];

export function RegistrationShell({
  children, currentStep = 1, completedSteps = [], summaries = {}, editingStep = null,
  onStepSelect,
}) {
  return <div className="marketing-site relative isolate min-h-dvh overflow-x-hidden bg-[linear-gradient(145deg,hsl(var(--background))_0%,hsl(var(--surface-subtle))_52%,hsl(var(--accent)/0.045)_100%)] md:h-dvh md:overflow-hidden">
    <div className="paper-grid pointer-events-none absolute inset-0 -z-10 opacity-[0.16] [mask-image:linear-gradient(to_bottom,black,transparent_78%)]" />
    <div className="pointer-events-none absolute -left-32 -top-40 -z-10 h-[34rem] w-[34rem] rounded-full bg-[hsl(var(--chart-2)/0.1)] blur-3xl" />
    <div className="pointer-events-none absolute -bottom-44 -right-32 -z-10 h-[30rem] w-[30rem] rounded-full bg-accent/10 blur-3xl" />
    <a href="#registration-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2">Skip to registration</a>
    <header className="sticky top-0 z-20 h-16 border-b bg-card/88 shadow-[0_8px_30px_hsl(var(--shadow-color)/0.035)] backdrop-blur-xl before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:bg-[linear-gradient(90deg,hsl(var(--primary)),hsl(var(--accent))_48%,transparent_86%)]">
      <div className="mx-auto flex min-h-16 max-w-[1360px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link to="/" aria-label="Edvatiq home"><BrandLogo nameClassName="font-marketing text-2xl font-semibold" /></Link>
        <div className="flex items-center gap-4">
          <span className="hidden items-center gap-2 text-xs font-medium text-muted-foreground sm:inline-flex"><LockKey size={15} className="text-positive" />Secure workspace setup</span>
          <span className="hidden h-5 w-px bg-border sm:block" />
          <p className="text-xs text-muted-foreground sm:text-sm"><span className="hidden sm:inline">Already have a workspace? </span><Link to="/login" className="font-semibold text-foreground transition-colors hover:text-primary">Sign in</Link></p>
        </div>
      </div>
    </header>
    <main id="registration-content" className="relative z-10 mx-auto w-full max-w-[1360px] px-4 py-3 sm:px-6 md:h-[calc(100dvh-4rem)] md:overflow-hidden md:py-4 lg:px-8">
      <RegistrationMobileProgress currentStep={currentStep} editingStep={editingStep} />
      <div className="min-w-0 md:grid md:h-full md:min-h-0 md:grid-cols-[190px_minmax(0,1fr)] md:gap-4 xl:grid-cols-[200px_minmax(0,1fr)] xl:gap-6">
        <RegistrationJourney
          currentStep={currentStep}
          completedSteps={completedSteps}
          summaries={summaries}
          editingStep={editingStep}
          onStepSelect={onStepSelect}
        />
        <div className="min-h-0 min-w-0 md:h-full">{children}</div>
      </div>
    </main>
  </div>;
}

function RegistrationMobileProgress({ currentStep, editingStep }) {
  const currentLabel = registrationSteps[Math.max(0, Math.min(registrationSteps.length - 1, currentStep - 1))];
  const CurrentIcon = stepMeta[Math.max(0, Math.min(stepMeta.length - 1, currentStep - 1))].icon;
  return <nav aria-label="Registration progress" className="mb-3 md:hidden">
    <div className="overflow-hidden rounded-xl border border-primary/10 bg-card/95 px-3.5 py-3 shadow-sm backdrop-blur">
      <div className="flex items-center justify-between gap-3 text-xs"><span className="inline-flex items-center gap-2 font-semibold"><span className="grid h-7 w-7 place-items-center rounded-lg bg-primary text-primary-foreground"><CurrentIcon size={15} weight="duotone" /></span>{editingStep ? `Editing ${currentLabel}` : currentLabel}</span><span className="text-muted-foreground">Step {currentStep} of {registrationSteps.length}</span></div>
      <div className="mt-2.5 grid grid-cols-4 gap-1.5">{registrationSteps.map((label, index) => <span key={label} className={cn("h-1 rounded-full", index < currentStep || editingStep ? "bg-primary" : "bg-border")}><span className="sr-only">{label}</span></span>)}</div>
    </div>
  </nav>;
}

function RegistrationJourney({ currentStep, completedSteps, summaries, editingStep, onStepSelect }) {
  return <aside className="relative hidden min-h-0 flex-col overflow-hidden rounded-2xl border border-primary/10 bg-card/90 text-foreground shadow-[0_18px_50px_hsl(var(--shadow-color)/0.06)] backdrop-blur md:flex">
    <div className="paper-grid pointer-events-none absolute inset-0 opacity-[0.11] [mask-image:linear-gradient(to_bottom,black,transparent_70%)]" />
    <div className="pointer-events-none absolute -bottom-20 -right-20 h-52 w-52 rounded-full bg-accent/10 blur-3xl" />
    <div className="relative border-b border-primary/10 px-4 py-4">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-accent shadow-sm"><Sparkle size={18} weight="fill" /></span>
      <div className="overline mt-4 text-primary">Get started</div>
      <h2 className="mt-1 text-lg font-semibold leading-tight">Create your workspace</h2>
    </div>
    <nav className="relative min-h-0 flex-1 px-3 py-3" aria-label="Registration steps">
      <ol className="space-y-1">
      {stepMeta.map(({ label, description, icon: StepIcon }, index) => {
        const number = index + 1;
        const complete = completedSteps.includes(number);
        const active = number === currentStep;
        const editing = editingStep === number;
        const clickable = complete && !active && typeof onStepSelect === "function";
        const content = <>
          <span className={cn(
            "mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border text-[11px] font-bold",
            complete && !active && "border-primary/15 bg-primary/8 text-primary",
            active && "border-primary bg-primary text-primary-foreground shadow-[0_0_0_4px_hsl(var(--primary)/0.09)]",
            !complete && !active && "border-border bg-card text-muted-foreground",
          )}>{editing ? <PencilSimple size={13} weight="bold" /> : complete && !active ? <Check size={13} weight="bold" /> : <StepIcon size={13} weight="duotone" />}</span>
          <span className="min-w-0 flex-1">
            <span className={cn("flex items-center gap-2 text-xs font-semibold", active ? "text-foreground" : "text-muted-foreground")}><span className="text-[9px] tracking-[0.12em] text-muted-foreground/70">{String(number).padStart(2, "0")}</span>{label}{editing && <span className="rounded-full bg-accent/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-accent">Editing</span>}</span>
            <span className="mt-0.5 block truncate text-[10px] leading-4 text-muted-foreground">{summaries[number] || description}</span>
          </span>
        </>;
        return <li key={label} aria-current={active ? "step" : undefined}>
          {clickable
            ? <button type="button" onClick={() => onStepSelect(number)} className="flex w-full items-start gap-2.5 rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-secondary/70">{content}</button>
            : <div className={cn("flex items-start gap-2.5 rounded-xl px-2 py-2.5", active && "border border-primary/10 bg-[linear-gradient(90deg,hsl(var(--primary)/0.07),hsl(var(--accent)/0.035))]")}>{content}</div>}
        </li>;
      })}
      </ol>
    </nav>
    <div className="relative flex gap-2.5 border-t border-primary/10 px-4 py-3 text-[10px] leading-4 text-muted-foreground"><LockKey size={15} className="mt-0.5 shrink-0 text-primary" />Progress is saved in this browser. Sensitive credentials are never stored.</div>
  </aside>;
}

export function RegistrationPanel({ children, footer, aside, wide = false }) {
  return <div className={cn(
    "mx-auto grid min-w-0 gap-3 md:h-full md:min-h-0 xl:gap-5",
    aside ? "md:grid-rows-[auto_minmax(0,1fr)]" : "md:grid-rows-[minmax(0,1fr)]",
    wide ? "max-w-[1100px]" : "max-w-[1060px]",
    aside && "xl:grid-cols-[minmax(0,1fr)_260px] xl:grid-rows-[minmax(0,1fr)]",
  )}>
    {aside && <aside className="order-first min-w-0 xl:order-last xl:sticky xl:top-0 xl:self-start">{aside}</aside>}
    <section className="reveal relative order-last flex min-w-0 flex-col overflow-visible rounded-2xl border border-primary/10 bg-card/95 shadow-[0_22px_65px_hsl(var(--shadow-color)/0.075)] md:min-h-0 md:overflow-hidden xl:order-first">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-[3px] bg-[linear-gradient(90deg,hsl(var(--primary)),hsl(var(--accent))_42%,transparent_82%)]" />
      <div data-registration-scroll-region className="premium-scrollbar relative min-h-0 min-w-0 p-5 sm:p-6 md:flex-1 md:overflow-y-auto lg:p-7">{children}</div>
      {footer && <div className="sticky bottom-0 z-10 border-t bg-card/95 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur-xl sm:p-5 md:static md:shrink-0">{footer}</div>}
    </section>
  </div>;
}

export function CheckoutSummary({ plan, quote, interval, money, organizationName, showWorkspace = true, className }) {
  if (!plan) return null;
  const trial = plan.signup_mode === "trial";
  return <div className={cn("relative isolate overflow-hidden rounded-2xl border bg-card p-4 shadow-sm lg:p-5 xl:border-primary/15 xl:bg-[linear-gradient(145deg,hsl(var(--card)),hsl(var(--primary)/0.045))] xl:shadow-[0_16px_40px_hsl(var(--shadow-color)/0.07)]", className)}>
    <div className="paper-grid pointer-events-none absolute inset-0 -z-10 hidden opacity-[0.08] xl:block" />
    <div className="pointer-events-none absolute inset-x-0 top-0 h-[3px] bg-[linear-gradient(90deg,hsl(var(--primary)),hsl(var(--accent)),transparent)] xl:block" />
    <div className="flex items-center justify-between gap-4 xl:hidden">
      <div className="min-w-0"><div className="truncate text-sm font-semibold">{plan.name}{showWorkspace && organizationName ? ` / ${organizationName}` : ""}</div><div className="mt-0.5 text-[11px] text-muted-foreground">{trial ? `${plan.trial_days || 30}-day trial` : interval === "annual" ? "Annual billing" : "Monthly billing"}</div></div>
      <div className="shrink-0 font-semibold">{trial ? "Free" : quote ? money(quote.total_paise) : "Unavailable"}</div>
    </div>
    <div className="hidden xl:block">
    <div className="overline inline-flex items-center gap-2 text-primary"><Sparkle className="text-accent" weight="fill" />Order summary</div>
    <div className="mt-3 flex items-start justify-between gap-4">
      <div className="min-w-0"><div className="truncate font-semibold">{plan.name}</div><div className="mt-1 text-xs text-muted-foreground">{trial ? `${plan.trial_days || 30}-day trial` : `${interval === "annual" ? "Annual" : "Monthly"} term`}</div></div>
      <div className="shrink-0 text-right font-semibold">{trial ? "Free" : quote ? money(quote.total_paise) : "Unavailable"}</div>
    </div>
    {showWorkspace && organizationName && <div className="mt-4 border-t pt-4"><div className="text-[11px] uppercase tracking-wider text-muted-foreground">Workspace</div><div className="mt-1 truncate text-sm font-medium">{organizationName}</div></div>}
    {!trial && quote && <div className="mt-4 space-y-2 border-t pt-4 text-xs">
      <div className="flex justify-between gap-4 text-muted-foreground"><span>Plan fee</span><span>{money(quote.subtotal_paise)}</span></div>
      <div className="flex justify-between gap-4 text-muted-foreground"><span>GST</span><span>{money(quote.tax_paise)}</span></div>
      <div className="flex justify-between gap-4 border-t pt-3 text-sm font-semibold"><span>Total</span><span>{money(quote.total_paise)}</span></div>
    </div>}
    </div>
  </div>;
}

export function CancelCheckoutDialog({ open, onOpenChange, loading, onConfirm }) {
  return <Dialog open={open} onOpenChange={(value) => { if (!loading) onOpenChange(value); }}>
    <DialogContent>
      <DialogHeader><DialogTitle>Cancel this checkout?</DialogTitle><DialogDescription>The payment session will stop being usable. Your workspace details remain, but the owner email must be verified again and the password re-entered.</DialogDescription></DialogHeader>
      <DialogFooter className="gap-2 sm:space-x-0"><Button type="button" variant="outline" disabled={loading} onClick={() => onOpenChange(false)}>Keep checkout</Button><Button type="button" variant="destructive" loading={loading} loadingText="Cancelling..." onClick={onConfirm}>Cancel and edit</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
