import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowRight, CalendarBlank, CaretDown, Check, CheckCircle, ClockCountdown,
  Crown, Info, Lightning, Receipt, ShieldCheck, Sparkle, Wallet,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { clientLabel } from "@/app/routeManifest";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { CursorListFooter, EmptyState, ResponsiveCardGrid, StatusBadge } from "@/components/system";
import { useAuth } from "@/contexts/AuthContext";
import {
  useCreatePackCheckoutMutation, useCreatePlanCheckoutMutation,
  useGetBillingInvoicesQuery, useGetBillingOverviewQuery, useMockPayInvoiceMutation,
  usePreviewPlanCheckoutMutation, useSchedulePlanChangeMutation,
  useVerifyBillingPaymentMutation,
} from "@/store/api/billingApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import { loadRazorpayCheckout } from "@/lib/razorpay";

const AI_COMPARISON_CODES = new Set([
  "documents.knowledge",
  "ai.actions",
  "ai.views.share",
]);

const AI_TIER_LABELS = {
  basic: "Essential AI",
  advanced: "Advanced AI",
  actions: "AI with actions",
  enterprise: "Enterprise AI",
};

export default function Billing() {
  const { organization, user, refreshMe } = useAuth();
  const isCollege = organization?.industry === "college";
  const entityLabel = clientLabel(organization?.industry);
  const { data, isLoading, isFetching, error, refetch } = useGetBillingOverviewQuery();
  const [previewPlan] = usePreviewPlanCheckoutMutation();
  const [createCheckout] = useCreatePlanCheckoutMutation();
  const [createPackCheckout] = useCreatePackCheckoutMutation();
  const [verifyPayment] = useVerifyBillingPaymentMutation();
  const [mockPay] = useMockPayInvoiceMutation();
  const [scheduleChange] = useSchedulePlanChangeMutation();
  const [interval, setInterval] = useState("monthly");
  const [renewalMode, setRenewalMode] = useState("auto_renew");
  const [review, setReview] = useState(null);
  const [working, setWorking] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const invoicePaging = useCursorPagination("billing-invoices");
  const invoiceQuery = useGetBillingInvoicesQuery({ cursor: invoicePaging.cursor, limit: 25 });
  const { accept: acceptInvoicePage } = invoicePaging;
  useEffect(() => { acceptInvoicePage(invoiceQuery.data); }, [acceptInvoicePage, invoiceQuery.data]);

  const plans = useMemo(() => data?.plans || [], [data?.plans]);
  const subscription = data?.subscription;
  const scheduled = data?.scheduled_change;
  const payment = data?.payment;
  const wallet = data?.wallet?.wallet;
  const packs = data?.wallet?.packs || [];
  const recentInvoices = data?.invoices || [];
  const invoices = invoicePaging.items.length ? invoicePaging.items : recentInvoices;
  const invoiceSummary = invoiceQuery.data?.summary || data?.invoice_summary || {
    total: recentInvoices.length,
    paid: recentInvoices.filter((invoice) => invoice.status === "paid").length,
  };
  const activePlanId = subscription?.plan || organization?.plan;
  const currentPlan = plans.find((plan) => plan.id === activePlanId);
  const recurringActive = Boolean(subscription?.razorpay_subscription_id && ["active", "authenticated", "paused", "past_due"].includes(subscription?.status));
  const annualSaving = useMemo(() => {
    const savings = plans.flatMap((plan) => {
      const monthly = Number(plan.monthly_price_paise || 0);
      const annual = Number(plan.annual_price_paise || 0);
      return monthly && annual && annual < monthly * 12
        ? [Math.round((1 - annual / (monthly * 12)) * 100)]
        : [];
    });
    return savings.length ? Math.max(...savings) : 0;
  }, [plans]);

  const featureRows = useMemo(() => {
    const definitions = new Map();
    plans.forEach((plan) => plan.features?.forEach((feature) => definitions.set(feature.code, feature)));
    return [...definitions.values()].filter((feature) =>
      !feature.code.startsWith("module.") &&
      !feature.code.startsWith("limits.") &&
      !AI_COMPARISON_CODES.has(feature.code));
  }, [plans]);

  const openPlanReview = async (plan) => {
    try {
      const quote = await previewPlan({ plan: plan.id, billing_interval: interval }).unwrap();
      setReview({ kind: "plan", plan, quote });
    } catch (requestError) {
      toast.error(message(requestError, "Could not prepare this plan"));
    }
  };

  const openPackReview = (pack) => setReview({ kind: "pack", pack, quote: pack.quote });

  const checkoutOptions = (label) => ({
    name: "Edvatiq",
    description: label,
    prefill: {
      name: `${user?.first_name || ""} ${user?.last_name || ""}`.trim(),
      email: user?.email || "",
      contact: user?.phone || "",
    },
    theme: { color: `hsl(${getComputedStyle(document.documentElement).getPropertyValue("--accent").trim()})` },
    modal: { ondismiss: () => setWorking(false) },
  });

  const finishOrder = async (result, order, successText) => {
    await verifyPayment({
      invoice_id: order.invoice_id,
      razorpay_order_id: result.razorpay_order_id,
      razorpay_payment_id: result.razorpay_payment_id,
      razorpay_signature: result.razorpay_signature,
    }).unwrap();
    toast.success(successText);
    await refreshMe();
    refetch();
    setReview(null);
    setWorking(false);
  };

  const openProviderCheckout = async (checkout, label, successText) => {
    if (checkout.mock_mode || checkout.checkout?.mode === "mock") {
      if (checkout.invoice_id) await mockPay(checkout.invoice_id).unwrap();
      toast.success(successText);
      await refreshMe(); refetch(); setReview(null); setWorking(false);
      return;
    }
    await loadRazorpayCheckout();
    const options = checkoutOptions(label);
    if (checkout.checkout_type === "subscription") {
      const modal = new window.Razorpay({
        ...options, key: checkout.checkout.key_id, subscription_id: checkout.checkout.subscription_id,
        handler: async () => {
          toast.success("Automatic renewal authorized. We are confirming your plan.");
          refetch(); setReview(null); setWorking(false);
        },
      });
      modal.on("payment.failed", (result) => { setWorking(false); toast.error(result.error?.description || "Authorization was not completed"); });
      modal.open();
      return;
    }
    const modal = new window.Razorpay({
      ...options, key: checkout.key_id, amount: checkout.amount_paise,
      currency: checkout.currency, order_id: checkout.order_id,
      notes: { invoice_id: checkout.invoice_id },
      handler: (result) => finishOrder(result, checkout, successText).catch((requestError) => {
        setWorking(false); toast.error(message(requestError, "Payment is being confirmed"));
      }),
    });
    modal.on("payment.failed", (result) => { setWorking(false); toast.error(result.error?.description || "Payment was not completed"); });
    modal.open();
  };

  const confirmReview = async () => {
    setWorking(true);
    try {
      if (review.kind === "pack") {
        const checkout = await createPackCheckout({ packId: review.pack.id, idempotency_key: crypto.randomUUID() }).unwrap();
        await openProviderCheckout(checkout, `${review.pack.name} AI credits`, "AI credits added to your wallet");
        return;
      }
      if (recurringActive && review.plan.id !== activePlanId) {
        await scheduleChange({
          plan: review.plan.id, billing_interval: interval, timing: "cycle_end",
          replace_pending: Boolean(scheduled), reason: "Plan change requested by account owner",
          version: subscription.version,
        }).unwrap();
        toast.success(`${review.plan.name} is scheduled for the next renewal`);
        setReview(null); setWorking(false); refetch();
        return;
      }
      const checkout = await createCheckout({
        plan: review.plan.id, billing_interval: interval, renewal_mode: renewalMode,
        idempotency_key: crypto.randomUUID(),
      }).unwrap();
      await openProviderCheckout(checkout, `${review.plan.name} - ${title(interval)}`, `${review.plan.name} is now active`);
    } catch (requestError) {
      setWorking(false);
      toast.error(message(requestError, "Could not start checkout"));
    }
  };

  if (isLoading) return <BillingSkeleton />;
  if (error) return <LoadFailure retry={refetch} />;

  const settledCredits = wallet?.balance_credits ?? wallet?.available_credits ?? 0;
  const used = wallet?.cycle_grant_credits ? Math.max(wallet.cycle_grant_credits - settledCredits, 0) : 0;
  const usagePercent = wallet?.cycle_grant_credits ? Math.min(100, Math.round((used / wallet.cycle_grant_credits) * 100)) : 0;
  const isTrial = subscription?.plan === "trial" || ["trialing", "expired"].includes(subscription?.status);
  const trialExpired = subscription?.status === "expired";
  const planDate = subscription?.trial_end || subscription?.current_period_end;
  const planDateLabel = isTrial
    ? planDate ? `${trialExpired ? "Trial ended" : "Trial ends"} ${date(planDate)}` : "30-day free trial"
    : subscription?.current_period_end ? `Renews ${date(subscription.current_period_end)}` : "Active plan";
  const creditDateLabel = wallet?.cycle_end
    ? isTrial ? `${trialExpired ? "Expired" : "Expires"} ${date(wallet.cycle_end)}` : `Refreshes ${date(wallet.cycle_end)}`
    : "";
  const latestInvoice = invoices[0];

  return <div className="mx-auto max-w-[1440px] space-y-6 pb-12 reveal md:space-y-8">
    <header className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
      <div className="max-w-3xl">
        <div className="overline text-accent">Plans &amp; billing</div>
        <h1 className="mt-1 font-display text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">One place for your plan, AI credits, and payments.</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">See what is active, recharge without hunting through settings, and keep every invoice easy to find.</p>
      </div>
      <nav aria-label="Billing sections" className="no-scrollbar flex max-w-full gap-1 overflow-x-auto rounded-2xl border bg-card p-1.5 shadow-sm">
        <SectionLink href="#overview">Overview</SectionLink>
        <SectionLink href="#ai-wallet">AI wallet</SectionLink>
        <SectionLink href="#billing-history">Invoices</SectionLink>
        <SectionLink href="#plans">Plans</SectionLink>
      </nav>
    </header>

    <section id="overview" className="grid scroll-mt-6 gap-4 lg:grid-cols-2 xl:grid-cols-12">
      <article className="relative overflow-hidden rounded-[1.75rem] border bg-primary p-6 text-primary-foreground shadow-xl sm:p-8 lg:col-span-2 xl:col-span-7">
        <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-accent/20 blur-2xl" />
        <div className="absolute -bottom-20 left-1/2 h-40 w-72 rounded-full bg-chart-2/20 blur-3xl" />
        <div className="relative flex h-full min-h-[270px] flex-col justify-between gap-8">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-[.2em] text-accent">Current subscription</span>
              <span className="rounded-full border border-primary-foreground/15 bg-primary-foreground/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider">{title(subscription?.status || "trialing")}</span>
            </div>
            <h2 className="mt-4 font-display text-4xl font-semibold sm:text-5xl">{currentPlan?.name || title(organization?.plan)}</h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-primary-foreground/70">{trialExpired ? "Your trial has ended. Select a paid plan to restore full workspace access." : "Your team access, billing cycle, and AI allowance stay together on one predictable subscription."}</p>
          </div>
          <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div className="grid gap-x-8 gap-y-4 text-sm sm:grid-cols-2">
              <SummaryDetail label="Billing date" value={planDateLabel} />
              <SummaryDetail label="Payment" value={payment?.mode === "test" ? "Secure test checkout" : "Secure online checkout"} />
            </div>
            <Button asChild className="shrink-0 bg-accent text-accent-foreground hover:bg-accent/90">
              <a href="#plans">Review plans<ArrowRight /></a>
            </Button>
          </div>
        </div>
      </article>

      <a href="#ai-wallet" className="surface-card surface-interactive group flex min-h-[270px] flex-col justify-between overflow-hidden p-6 xl:col-span-3">
        <div>
          <div className="flex items-start justify-between gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-accent/10 text-accent"><Wallet size={23} weight="duotone" /></span>
            <span className="overline">AI wallet</span>
          </div>
          <div className="mt-8 font-display text-4xl font-semibold tracking-[-0.05em]">{format(settledCredits)}</div>
          <p className="mt-1 text-sm text-muted-foreground">credits available</p>
          <Progress value={100 - usagePercent} className="mt-5 [&>div]:bg-accent" aria-label={`${format(settledCredits)} AI credits available`} />
          <div className="mt-2 flex justify-between gap-3 text-[11px] text-muted-foreground"><span>{format(used)} used this cycle</span><span>{creditDateLabel}</span></div>
        </div>
        <span className="mt-6 inline-flex items-center gap-2 text-sm font-semibold">Recharge wallet<ArrowRight className="transition-transform group-hover:translate-x-1" /></span>
      </a>

      <a href="#billing-history" className="surface-card surface-interactive group flex min-h-[270px] flex-col justify-between overflow-hidden p-6 xl:col-span-2">
        <div>
          <div className="flex items-start justify-between gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-secondary text-muted-foreground"><Receipt size={23} weight="duotone" /></span>
            <span className="overline">Invoices</span>
          </div>
          {latestInvoice ? <>
            <div className="mt-8 font-display text-3xl font-semibold tracking-[-0.05em]">{money(latestInvoice.amount_paise)}</div>
            <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{latestInvoice.invoice_number || `Invoice ${shortId(latestInvoice.id)}`}</p>
            <StatusBadge className="mt-4" status={latestInvoice.status} />
          </> : <>
            <div className="mt-8 font-display text-2xl font-semibold">No invoices yet</div>
            <p className="mt-2 text-sm leading-5 text-muted-foreground">Completed purchases will appear here.</p>
          </>}
        </div>
        <span className="mt-6 inline-flex items-center gap-2 text-sm font-semibold">{invoiceSummary.total ? `${invoiceSummary.total} total, ${invoiceSummary.paid} paid` : "View billing history"}<ArrowRight className="transition-transform group-hover:translate-x-1" /></span>
      </a>
    </section>

    {trialExpired && <section className="flex flex-col justify-between gap-4 rounded-2xl border border-warning/30 bg-warning-soft p-5 sm:flex-row sm:items-center">
      <div className="flex gap-3"><ClockCountdown size={24} className="shrink-0 text-warning" /><div><div className="font-semibold">Your free trial has ended</div><p className="mt-1 text-sm text-muted-foreground">Select a paid plan below. Free AI credits do not renew after the trial.</p></div></div>
      <span className="rounded-full border bg-card px-3 py-1 text-sm">Upgrade to continue</span>
    </section>}

    {scheduled && <section className="flex flex-col justify-between gap-4 rounded-2xl border border-warning/30 bg-warning-soft p-5 sm:flex-row sm:items-center">
      <div className="flex gap-3"><ClockCountdown size={24} className="shrink-0 text-warning" /><div><div className="font-semibold">A plan change is scheduled</div><p className="mt-1 text-sm text-muted-foreground">The change takes effect on {date(scheduled.effective_at)}. Your current access continues until then.</p></div></div>
      <span className="rounded-full border bg-card px-3 py-1 text-sm capitalize">{scheduled.action}</span>
    </section>}

    {payment && !payment.configured && <section className="rounded-2xl border border-destructive/25 bg-destructive/5 p-5 flex gap-3"><Info size={22} className="text-destructive shrink-0" /><div><div className="font-semibold">Online checkout is temporarily unavailable</div><p className="text-sm text-muted-foreground mt-1">Your current plan remains active. Contact Edvatiq support if you need an immediate change.</p></div></section>}

    <section className="space-y-5">
      <WalletPanel wallet={wallet} packs={packs} settledCredits={settledCredits} creditDateLabel={creditDateLabel} paymentConfigured={payment?.configured} onSelect={openPackReview} />
      <InvoiceHistory invoices={invoices} total={invoiceSummary.total || 0} hasMore={Boolean(invoiceQuery.data?.has_more)} loading={invoiceQuery.isFetching} error={invoiceQuery.isError} onLoadMore={() => invoicePaging.loadMore(invoiceQuery.data?.next_cursor)} onRetry={invoiceQuery.refetch} />
    </section>

    <section id="plans" className="scroll-mt-6 space-y-5">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl"><div className="overline text-accent">Plans</div><h2 className="mt-1 font-display text-3xl font-semibold tracking-[-0.04em] md:text-4xl">Choose the capacity your team needs.</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Every price shows the tax-inclusive checkout total. Change cadence and renewal behavior before choosing.</p></div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <SegmentedControl label="Billing cadence">
            <Toggle active={interval === "monthly"} onClick={() => setInterval("monthly")}>Monthly</Toggle>
            <Toggle active={interval === "annual"} onClick={() => setInterval("annual")}>Annual {annualSaving > 0 && <span className="ml-1 text-positive">save {annualSaving}%</span>}</Toggle>
          </SegmentedControl>
          <SegmentedControl label="Renewal">
            <Toggle active={renewalMode === "auto_renew"} onClick={() => setRenewalMode("auto_renew")}>Auto-renew</Toggle>
            <Toggle active={renewalMode === "one_time"} onClick={() => setRenewalMode("one_time")}>Pay once</Toggle>
          </SegmentedControl>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4 reveal-stagger">
        {plans.filter((plan) => plan.id !== "trial").map((plan) => <PlanCard key={plan.id} plan={plan} interval={interval} current={activePlanId === plan.id} disabled={!payment?.configured || isFetching || !plan.purchasable} action={() => openPlanReview(plan)} scheduled={recurringActive && activePlanId !== plan.id} entityLabel={entityLabel} isCollege={isCollege} />)}
      </div>
    </section>

    <Comparison plans={plans.filter((plan) => plan.id !== "trial")} featureRows={featureRows} expanded={showComparison} onToggle={() => setShowComparison((value) => !value)} entityLabel={entityLabel} isCollege={isCollege} />

    <ReviewSheet review={review} open={Boolean(review)} close={() => !working && setReview(null)} working={working} confirm={confirmReview} renewalMode={renewalMode} interval={interval} recurringActive={recurringActive} scheduled={scheduled} />
  </div>;
}

function WalletPanel({ wallet, packs, settledCredits, creditDateLabel, paymentConfigured, onSelect }) {
  return <section id="ai-wallet" className="surface-card scroll-mt-6 overflow-hidden">
    <div className="flex flex-col gap-5 border-b bg-surface-subtle/55 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
      <div className="flex gap-4">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground"><Wallet size={24} weight="duotone" /></span>
        <div><div className="overline text-accent">AI wallet recharge</div><h2 className="mt-1 font-display text-2xl font-semibold sm:text-3xl">Add credits without changing your plan.</h2><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">Choose a one-time pack for busy periods. Credits remain available for 12 months and the total is confirmed before checkout.</p></div>
      </div>
      <div className="shrink-0 rounded-2xl border bg-card px-4 py-3 sm:text-right">
        <div className="text-xs text-muted-foreground">Available now</div>
        <div className="mt-1 font-display text-2xl font-semibold">{format(settledCredits)} credits</div>
        <div className="mt-1 text-[11px] text-muted-foreground">{creditDateLabel || `${format(wallet?.cycle_grant_credits)} included per cycle`}</div>
      </div>
    </div>
    <div className="p-5 sm:p-6">
      {packs.length ? <ResponsiveCardGrid minWidth="15rem" className="sm:grid-cols-2 xl:[grid-template-columns:repeat(auto-fit,minmax(13rem,1fr))]">
        {packs.map((pack) => <button
          type="button"
          key={pack.id}
          onClick={() => onSelect(pack)}
          disabled={!paymentConfigured}
          aria-label={`Recharge ${format(pack.credits)} AI credits for ${money(pack.quote?.total_paise)}`}
          className="group flex min-h-[190px] flex-col rounded-2xl border bg-card p-4 text-left transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-lg disabled:pointer-events-none disabled:opacity-50"
        >
          <div className="flex items-start justify-between gap-3"><span className="text-xs font-semibold text-muted-foreground">{pack.name}</span><Lightning size={18} className="text-accent" weight="fill" /></div>
          <div className="mt-5 font-display text-3xl font-semibold tracking-[-0.05em]">{format(pack.credits)}</div>
          <div className="text-xs text-muted-foreground">AI credits</div>
          <div className="mt-auto flex items-end justify-between gap-3 pt-5"><div><div className="text-sm font-semibold">{money(pack.quote?.total_paise)}</div><div className="mt-0.5 text-[10px] text-muted-foreground">Tax-inclusive total</div></div><span className="grid h-8 w-8 place-items-center rounded-full bg-secondary transition group-hover:bg-primary group-hover:text-primary-foreground"><ArrowRight /></span></div>
        </button>)}
      </ResponsiveCardGrid> : <EmptyState variant="section" icon={Wallet} title="Recharge packs are not available" description="Your current credits remain available." />}
      <div className="mt-4 flex flex-col gap-2 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between"><span>Secure checkout. No recurring charge for a top-up.</span>{!paymentConfigured && <span className="font-semibold text-destructive">Checkout is temporarily unavailable</span>}</div>
    </div>
  </section>;
}

function InvoiceHistory({ invoices, total, hasMore, loading, error, onLoadMore, onRetry }) {
  return <section id="billing-history" className="surface-card scroll-mt-6 overflow-hidden">
    <div className="flex items-start justify-between gap-4 border-b p-5 sm:p-6">
      <div><div className="overline text-accent">Billing history</div><h2 className="mt-1 font-display text-2xl font-semibold sm:text-3xl">Invoices and payments</h2><p className="mt-2 text-sm text-muted-foreground">A clear record of plan and wallet purchases.</p></div>
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-secondary text-muted-foreground"><Receipt size={23} weight="duotone" /></span>
    </div>
    {invoices.length ? <div className="divide-y">
      {invoices.map((invoice) => <article key={invoice.id} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-6">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2"><h3 className="truncate text-sm font-semibold">{invoice.description || title(invoice.purchase_type)}</h3><StatusBadge status={invoice.status} /></div>
          <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-muted-foreground"><span className="font-mono">{invoice.invoice_number || `Invoice ${shortId(invoice.id)}`}</span><span aria-hidden="true">&middot;</span><span>{date(invoice.created_at)}</span>{invoice.billing_interval && <><span aria-hidden="true">&middot;</span><span>{title(invoice.billing_interval)}</span></>}</div>
        </div>
        <div className="sm:text-right"><div className="font-display text-lg font-semibold">{money(invoice.amount_paise)}</div>{invoice.tax_paise > 0 && <div className="mt-0.5 text-[10px] text-muted-foreground">includes {money(invoice.tax_paise)} tax</div>}</div>
      </article>)}
    </div> : <div className="p-4 sm:p-5"><EmptyState variant="inline" icon={Receipt} title="No billing history yet" description="Your first completed checkout will create an invoice here." /></div>}
    <CursorListFooter count={invoices.length} noun="invoices" hasMore={hasMore} loading={loading} error={error} onLoadMore={onLoadMore} onRetry={onRetry} className="bg-surface-subtle/55" />
  </section>;
}

function PlanCard({ plan, interval, current, disabled, action, scheduled, entityLabel = "Clients", isCollege = false }) {
  const quote = interval === "annual" ? plan.annual_quote : plan.monthly_quote;
  const aiIncluded = Boolean(plan.entitlements?.["module.ai"]);
  const highlights = (plan.features || [])
    .filter((item) => !item.code.startsWith("module.") && !AI_COMPARISON_CODES.has(item.code))
    .slice(0, 3);
  const actionLabel = current ? "Current plan" : !plan.purchasable ? "Custom plan" : scheduled ? "Schedule change" : "Choose plan";
  return <article className={`relative flex min-h-[470px] flex-col overflow-hidden rounded-[1.75rem] border bg-card p-5 transition-[border-color,box-shadow,transform] sm:p-6 ${plan.recommended ? "border-accent/70 shadow-xl" : "shadow-sm"} ${current ? "ring-1 ring-positive/35" : "hover:-translate-y-0.5 hover:shadow-lg"}`}>
    <div className={`absolute inset-x-0 top-0 h-1 ${plan.recommended ? "bg-accent" : current ? "bg-positive" : "bg-border"}`} />
    <div className="flex min-h-7 flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap gap-2">{plan.recommended && <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-accent"><Sparkle weight="fill" />Recommended</span>}{current && <StatusBadge status="active" label="Current" />}</div>
      {plan.id === "business" && <Crown size={22} className="text-warning" weight="duotone" />}
    </div>
    <div className="mt-4"><div className="overline">Edvatiq plan</div><h3 className="mt-1 font-display text-2xl font-semibold">{plan.name}</h3><p className="mt-2 min-h-12 text-sm leading-6 text-muted-foreground">{plan.description}</p></div>
    <div className="mt-5"><span className="font-display text-3xl font-semibold tracking-[-0.05em]">{quote ? money(quote.total_paise) : "Custom"}</span>{quote && <span className="text-xs text-muted-foreground">/{interval === "annual" ? "year" : "month"}</span>}</div>
    <div className="mt-1 min-h-4 text-[10px] text-muted-foreground">{quote && interval === "annual" ? `${money(quote.total_paise / 12)} effective monthly` : plan.tax_enabled ? `${plan.gst_rate_bps / 100}% GST included` : "No GST on this plan"}</div>
    <div className="mt-5 grid grid-cols-2 gap-2 text-xs"><Stat value={limit(plan.employee_limit)} label={isCollege ? "faculty & staff" : "team"} /><Stat value={limit(plan.client_limit)} label={entityLabel.toLowerCase()} /><Stat value={limit(plan.location_limit)} label={isCollege ? "campuses" : "locations"} /><Stat value={format(plan.ai_credits)} label="AI credits" /></div>
    <div className={`mt-4 rounded-2xl border p-3.5 ${plan.id === "growth" ? "border-accent/30 bg-accent/5" : "bg-secondary/50"}`}>
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-xl bg-primary text-primary-foreground"><Sparkle size={16} weight="fill" /></span>
        <div>
          <div className="text-sm font-semibold">{aiIncluded ? AI_TIER_LABELS[plan.ai_tier] || "Edvatiq AI" : "AI not included"}</div>
          <div className="text-xs text-muted-foreground mt-0.5">{aiIncluded ? `${format(plan.ai_credits)} credits refresh every month` : "Upgrade to use Edvatiq AI"}</div>
        </div>
      </div>
      {aiIncluded && <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
        <Capability active label="AI chat" />
        <Capability active={Boolean(plan.entitlements?.["documents.knowledge"])} label="Document answers" />
        <Capability active={Boolean(plan.entitlements?.["ai.actions"])} label={isCollege ? "College workflow actions" : "Business actions"} />
      </div>}
    </div>
    <div className="mt-5 flex-1 space-y-2.5">{highlights.map((item) => <div key={item.code} className="flex gap-2 text-sm leading-5"><Check size={17} className="mt-0.5 shrink-0 text-positive" />{item.name}</div>)}</div>
    <Button type="button" className="mt-5 rounded-xl" variant={current ? "outline" : "default"} disabled={disabled || current} onClick={action}>{actionLabel}{!current && plan.purchasable && <ArrowRight />}</Button>
  </article>;
}

function Comparison({ plans, featureRows, expanded, onToggle, entityLabel = "Clients", isCollege = false }) {
  const rows = [
    { code: "limits.employees", name: "Team members", value: (plan) => limit(plan.employee_limit) },
    { code: "limits.clients", name: entityLabel, value: (plan) => limit(plan.client_limit) },
    { code: "limits.locations", name: isCollege ? "Campuses" : "Locations", value: (plan) => limit(plan.location_limit) },
    { code: "limits.storage_mb", name: "Document storage", value: (plan) => storage(plan.storage_limit_mb) },
    { code: "module.ai", name: "Edvatiq AI chat", value: (plan) => Boolean(plan.entitlements?.["module.ai"]) },
    { code: "ai.tier", name: "AI experience", value: (plan) => AI_TIER_LABELS[plan.ai_tier] || title(plan.ai_tier) },
    { code: "ai.credits", name: "AI credits each month", value: (plan) => format(plan.ai_credits) },
    { code: "documents.knowledge", name: "Answers from your documents", value: (plan) => Boolean(plan.entitlements?.["documents.knowledge"]) },
    { code: "ai.actions", name: isCollege ? "AI-assisted College actions" : "AI-assisted business actions", value: (plan) => Boolean(plan.entitlements?.["ai.actions"]) },
    { code: "ai.views.share", name: "Share AI insights with the team", value: (plan) => Boolean(plan.entitlements?.["ai.views.share"]) },
    ...featureRows.map((feature) => ({ code: feature.code, name: feature.name, value: (plan) => Boolean(plan.entitlements?.[feature.code]) })),
  ];
  return <section className="overflow-hidden rounded-[1.75rem] border bg-card">
    <button type="button" aria-expanded={expanded} aria-controls="plan-comparison-table" onClick={onToggle} className="group flex w-full flex-col gap-5 p-5 text-left transition hover:bg-surface-subtle/60 sm:flex-row sm:items-center sm:justify-between sm:p-7">
      <div><div className="overline text-accent">Detailed comparison</div><h2 className="mt-1 font-display text-2xl font-semibold sm:text-3xl">Know exactly what changes between plans.</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Compare {rows.length} limits and capabilities across {plans.length} paid plans when you need the fine print.</p></div>
      <span className="inline-flex shrink-0 items-center gap-2 rounded-xl border bg-card px-4 py-2 text-sm font-semibold shadow-sm">{expanded ? "Hide comparison" : "Compare every feature"}<CaretDown className={`transition-transform ${expanded ? "rotate-180" : ""}`} /></span>
    </button>
    {expanded && <div id="plan-comparison-table" className="premium-scrollbar overflow-x-auto border-t"><table className="w-full min-w-[820px] text-sm"><thead><tr className="bg-secondary/60"><th className="p-4 text-left font-medium">Capability</th>{plans.map((plan) => <th key={plan.id} className="p-4 text-center font-semibold">{plan.name}</th>)}</tr></thead><tbody className="divide-y">{rows.map((row) => <tr key={row.code}><td className="p-4 text-muted-foreground">{row.name}</td>{plans.map((plan) => { const value = row.value(plan); return <td key={plan.id} className="p-4 text-center">{typeof value === "boolean" ? value ? <CheckCircle weight="fill" className="inline text-positive" size={19} aria-label="Included" /> : <span className="text-muted-foreground/45">-</span> : value}</td>; })}</tr>)}</tbody></table></div>}
  </section>;
}

function ReviewSheet({ review, open, close, working, confirm, renewalMode, interval, recurringActive, scheduled }) {
  const quote = review?.quote;
  const label = review?.kind === "pack" ? review.pack.name : review?.plan?.name;
  const isSchedule = review?.kind === "plan" && recurringActive;
  return <Sheet open={open} onOpenChange={(value) => !value && close()}><SheetContent className="sm:max-w-lg overflow-y-auto">
    <SheetHeader><SheetTitle className="font-display text-3xl">Review your {review?.kind === "pack" ? "top-up" : "plan"}</SheetTitle><SheetDescription>Nothing changes until you confirm below.</SheetDescription></SheetHeader>
    {review && <div className="mt-7 space-y-6">
      <div className="rounded-2xl bg-primary p-6 text-primary-foreground"><div className="text-xs uppercase tracking-[.2em] text-accent">{review.kind === "pack" ? "AI credits" : title(interval)}</div><div className="mt-2 font-display text-3xl font-bold">{label}</div>{review.kind === "pack" && <div className="mt-2 text-primary-foreground/70">{format(review.pack.credits)} credits</div>}</div>
      <div className="rounded-2xl border divide-y">
        <PriceRow label="Price" value={money(quote?.total_paise - quote?.tax_paise)} />
        {quote?.tax_enabled && <PriceRow label={`GST (${quote.gst_rate_bps / 100}%)`} value={money(quote.tax_paise)} muted />}
        <PriceRow label="Total" value={money(quote?.total_paise)} strong />
      </div>
      <div className="rounded-2xl bg-secondary/60 p-4 text-sm space-y-3">
        <ReviewLine icon={CalendarBlank}>{review.kind === "pack" ? `Credits expire ${date(review.pack.expires_at)}` : isSchedule ? "Starts after your current billing cycle" : interval === "annual" ? "12 months of plan access" : "One month of plan access"}</ReviewLine>
        {review.kind === "plan" && <ReviewLine icon={Lightning}>{isSchedule ? scheduled ? "Replaces the currently scheduled change" : "No charge today for a cycle-end change" : renewalMode === "auto_renew" ? "Renews automatically until cancelled" : "Does not renew automatically"}</ReviewLine>}
        <ReviewLine icon={ShieldCheck}>Your access changes only after payment confirmation</ReviewLine>
      </div>
      <Button className="w-full rounded-xl h-12" disabled={working} onClick={confirm}>{working ? "Preparing secure checkout..." : isSchedule ? "Schedule for next renewal" : `Continue to pay ${money(quote?.total_paise)}`}</Button>
    </div>}
  </SheetContent></Sheet>;
}

function SectionLink({ href, children }) { return <a href={href} className="whitespace-nowrap rounded-xl px-3.5 py-2 text-xs font-semibold text-muted-foreground transition hover:bg-secondary hover:text-foreground sm:text-sm">{children}</a>; }
function SummaryDetail({ label, value }) { return <div><div className="text-[10px] font-bold uppercase tracking-[.16em] text-primary-foreground/45">{label}</div><div className="mt-1 text-xs font-semibold text-primary-foreground/90 sm:text-sm">{value}</div></div>; }
function SegmentedControl({ label, children }) { return <div><div className="mb-1 ml-1 text-[9px] font-bold uppercase tracking-[.16em] text-muted-foreground">{label}</div><div role="group" aria-label={label} className="flex rounded-2xl border bg-card p-1 shadow-sm">{children}</div></div>; }
function Toggle({ active, children, onClick }) { return <button type="button" aria-pressed={active} onClick={onClick} className={`rounded-xl px-3.5 py-2 text-xs font-semibold transition sm:text-sm ${active ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}>{children}</button>; }
function Stat({ value, label }) { return <div className="rounded-xl bg-secondary/60 p-2.5"><strong className="block text-foreground">{value}</strong><span className="text-muted-foreground">{label}</span></div>; }
function Capability({ active, label }) { return <span className={`rounded-full px-2 py-1 ${active ? "bg-positive/10 text-positive" : "bg-secondary text-muted-foreground line-through"}`}>{label}</span>; }
function PriceRow({ label, value, strong, muted }) { return <div className={`flex justify-between p-4 ${strong ? "text-lg font-bold" : ""} ${muted ? "text-muted-foreground" : ""}`}><span>{label}</span><span>{value}</span></div>; }
function ReviewLine({ icon: Icon, children }) { return <div className="flex gap-2.5"><Icon size={19} className="shrink-0 text-positive" /><span>{children}</span></div>; }
function BillingSkeleton() { return <div className="mx-auto max-w-[1440px] space-y-6"><div><Skeleton className="h-4 w-28" /><Skeleton className="mt-3 h-10 max-w-2xl" /><Skeleton className="mt-3 h-4 max-w-xl" /></div><div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-12"><Skeleton className="h-[270px] rounded-[1.75rem] lg:col-span-2 xl:col-span-7" /><Skeleton className="h-[270px] rounded-[1.75rem] xl:col-span-3" /><Skeleton className="h-[270px] rounded-[1.75rem] xl:col-span-2" /></div><Skeleton className="h-[360px] rounded-[1.75rem]" /><Skeleton className="h-64 rounded-[1.75rem]" /></div>; }
function LoadFailure({ retry }) { return <div className="max-w-xl mx-auto mt-20 rounded-3xl border bg-card p-10 text-center"><Info size={36} className="mx-auto text-destructive" /><h1 className="font-display text-3xl font-bold mt-4">Billing could not be loaded</h1><p className="text-muted-foreground mt-2">Your plan has not changed. Try loading this page again.</p><Button className="mt-6" onClick={retry}>Try again</Button></div>; }
function money(paise = 0) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise || 0) / 100); }
function format(value = 0) { return new Intl.NumberFormat("en-IN").format(Number(value || 0)); }
function date(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "Not set"; }
function title(value = "") { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function shortId(value = "") { return String(value || "").slice(0, 8).toUpperCase() || "Pending"; }
function limit(value) { return value == null ? "Unlimited" : format(value); }
function storage(mb) { return mb == null ? "Custom" : mb >= 1024 ? `${format(mb / 1024)} GB` : `${format(mb)} MB`; }
function message(error, fallback) { return error?.data?.detail || error?.response?.data?.detail || error?.message || fallback; }
