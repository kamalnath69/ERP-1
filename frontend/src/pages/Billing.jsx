import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import {
  ArrowRight, CalendarBlank, Check, CheckCircle, ClockCountdown, CreditCard,
  Crown, Info, Lightning, Receipt, ShieldCheck, Sparkle, Wallet,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { clientLabel } from "@/app/routeManifest";
import { ValidatedActionDialog } from "@/components/forms/ValidatedActionDialog";
import {
  CursorListFooter, DataTable, EmptyState, ErrorState, PageHeader, PageShell,
  ResponsiveCardGrid, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/contexts/AuthContext";
import useCursorPagination from "@/hooks/useCursorPagination";
import { usePendingAction } from "@/hooks/usePendingAction";
import { loadCashfreeCheckout, openCashfreeModal } from "@/lib/cashfree";
import { loadRazorpayCheckout } from "@/lib/razorpay";
import { requiredText } from "@/lib/validation";
import {
  useCancelPlanMutation, useCreatePackCheckoutMutation, useCreatePlanCheckoutMutation,
  useGetBillingInvoicesQuery, useGetBillingOverviewQuery, useMockPayInvoiceMutation,
  usePreviewPlanCheckoutMutation, useRemoveScheduledPlanChangeMutation,
  useSchedulePlanChangeMutation, useVerifyBillingPaymentMutation,
} from "@/store/api/billingApi";

const BILLING_SECTIONS = [
  { id: "subscription", label: "Subscription", icon: CreditCard },
  { id: "plans", label: "Plans", icon: Crown },
  { id: "credits", label: "AI credits", icon: Wallet },
  { id: "invoices", label: "Invoices", icon: Receipt },
];

const SECTION_IDS = new Set(BILLING_SECTIONS.map((section) => section.id));
const LEGACY_SECTIONS = {
  "#overview": "subscription",
  "#plans": "plans",
  "#ai-wallet": "credits",
  "#billing-history": "invoices",
};

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

const cancellationSchema = z.object({
  reason: requiredText("Cancellation reason", { min: 5, max: 500 }),
});

export default function Billing() {
  const location = useLocation();
  const navigate = useNavigate();
  const { organization, user, refreshMe, can } = useAuth();
  const rawSection = new URLSearchParams(location.search).get("section");
  const section = SECTION_IDS.has(rawSection)
    ? rawSection
    : LEGACY_SECTIONS[location.hash] || "subscription";
  const canManage = Boolean(can?.("billing.manage"));
  const isCollege = organization?.industry === "college";
  const entityLabel = clientLabel(organization?.industry);

  const { data, isLoading, isFetching, error, refetch } = useGetBillingOverviewQuery();
  const [previewPlan] = usePreviewPlanCheckoutMutation();
  const [createCheckout] = useCreatePlanCheckoutMutation();
  const [createPackCheckout] = useCreatePackCheckoutMutation();
  const [verifyPayment] = useVerifyBillingPaymentMutation();
  const [mockPay] = useMockPayInvoiceMutation();
  const [scheduleChange] = useSchedulePlanChangeMutation();
  const [cancelPlan] = useCancelPlanMutation();
  const [removeScheduledPlanChange] = useRemoveScheduledPlanChangeMutation();

  const [interval, setInterval] = useState("monthly");
  const [renewalMode, setRenewalMode] = useState("auto_renew");
  const [review, setReview] = useState(null);
  const [working, setWorking] = useState(false);
  const [hostedCheckoutActive, setHostedCheckoutActive] = useState(false);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [cancellationOpen, setCancellationOpen] = useState(false);
  const [invoiceStatus, setInvoiceStatus] = useState("all");
  const [purchaseType, setPurchaseType] = useState("all");
  const reviewActions = usePendingAction();
  const subscriptionActions = usePendingAction();

  const invoiceFilterKey = `${invoiceStatus}:${purchaseType}`;
  const invoicePaging = useCursorPagination(invoiceFilterKey);
  const invoiceQuery = useGetBillingInvoicesQuery(
    {
      status: invoiceStatus,
      purchaseType,
      cursor: invoicePaging.cursor,
      limit: 25,
    },
    { skip: section !== "invoices" },
  );
  const invoicePage = Object.prototype.hasOwnProperty.call(invoiceQuery, "currentData")
    ? invoiceQuery.currentData
    : invoiceQuery.data;
  const { accept: acceptInvoicePage } = invoicePaging;

  useEffect(() => {
    if (!invoicePage) return;
    acceptInvoicePage(invoicePage);
  }, [acceptInvoicePage, invoicePage]);

  useEffect(() => {
    if (rawSection === section && !location.hash) return;
    const params = new URLSearchParams(location.search);
    params.set("section", section);
    navigate({ pathname: location.pathname, search: params.toString(), hash: "" }, { replace: true });
  }, [location.hash, location.pathname, location.search, navigate, rawSection, section]);

  const changeSection = (nextSection) => {
    const params = new URLSearchParams(location.search);
    params.set("section", nextSection);
    navigate({ pathname: location.pathname, search: params.toString(), hash: "" });
  };

  const plans = useMemo(() => data?.plans || [], [data?.plans]);
  const subscription = data?.subscription;
  const scheduled = data?.scheduled_change;
  const payment = data?.payment;
  const recurringSupported = payment?.recurring_supported !== false;
  const wallet = data?.wallet?.wallet;
  const packs = data?.wallet?.packs || [];
  const recentInvoices = data?.invoices || [];
  const invoiceItems = invoicePaging.items.length
    ? invoicePaging.items
    : !invoicePaging.cursor ? invoicePage?.items || [] : [];
  const invoiceSummary = invoicePage?.summary || data?.invoice_summary || {
    total: recentInvoices.length,
    paid: recentInvoices.filter((invoice) => invoice.status === "paid").length,
    amount_paise: recentInvoices.reduce((sum, invoice) => sum + Number(invoice.amount_paise || 0), 0),
  };
  const activePlanId = subscription?.plan || organization?.plan;
  const currentPlan = plans.find((plan) => plan.id === activePlanId);
  const recurringActive = Boolean(
    subscription?.razorpay_subscription_id
    && ["active", "authenticated", "paused", "past_due"].includes(subscription?.status),
  );
  const settledCredits = wallet?.balance_credits ?? wallet?.available_credits ?? 0;
  const usedCredits = wallet?.cycle_grant_credits
    ? Math.max(wallet.cycle_grant_credits - settledCredits, 0)
    : 0;
  const usagePercent = wallet?.cycle_grant_credits
    ? Math.min(100, Math.round((usedCredits / wallet.cycle_grant_credits) * 100))
    : 0;
  const isTrial = subscription?.plan === "trial" || ["trialing", "expired"].includes(subscription?.status);
  const trialExpired = subscription?.status === "expired";
  const planDate = subscription?.trial_end || subscription?.current_period_end;
  const planDateLabel = isTrial
    ? planDate ? `${trialExpired ? "Trial ended" : "Trial ends"} ${date(planDate)}` : "Trial period"
    : subscription?.current_period_end ? `Through ${date(subscription.current_period_end)}` : "Active term";
  const creditDateLabel = wallet?.cycle_end
    ? isTrial ? `${trialExpired ? "Expired" : "Expires"} ${date(wallet.cycle_end)}` : `Refreshes ${date(wallet.cycle_end)}`
    : "Not scheduled";

  useEffect(() => {
    if (!recurringSupported && renewalMode !== "one_time") setRenewalMode("one_time");
  }, [recurringSupported, renewalMode]);

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
    return [...definitions.values()].filter((feature) => (
      !feature.code.startsWith("module.")
      && !feature.code.startsWith("limits.")
      && !AI_COMPARISON_CODES.has(feature.code)
    ));
  }, [plans]);

  const openPlanReview = async (plan) => {
    if (!canManage) return;
    await reviewActions.run(`plan:${plan.id}`, async () => {
      try {
        const quote = await previewPlan({ plan: plan.id, billing_interval: interval }).unwrap();
        setReview({ kind: "plan", plan, quote, idempotencyKey: crypto.randomUUID() });
      } catch (requestError) {
        toast.error(message(requestError, "Could not prepare this plan"));
      }
    });
  };

  const openPackReview = (pack) => {
    if (!canManage) return;
    setReview({ kind: "pack", pack, quote: pack.quote, idempotencyKey: crypto.randomUUID() });
  };

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
      await refreshMe();
      refetch();
      setReview(null);
      setWorking(false);
      return;
    }
    if (checkout.provider === "cashfree") {
      await loadCashfreeCheckout();
      if (!checkout.payment_session_id) throw new Error("Cashfree did not return a payment session");
      const cashfree = window.Cashfree({
        mode: checkout.checkout_mode || (checkout.mode === "test" ? "sandbox" : "production"),
      });
      const checkoutResult = await openCashfreeModal(cashfree, checkout.payment_session_id, {
        beforeOpen: () => setHostedCheckoutActive(true),
        afterClose: () => setHostedCheckoutActive(false),
      });
      if (checkoutResult?.error) {
        setWorking(false);
        toast.error(checkoutResult.error.message || "Cashfree checkout could not be completed");
        return;
      }
      const verification = await verifyPayment({ invoice_id: checkout.invoice_id }).unwrap();
      if (verification.status && verification.status !== "paid") {
        setWorking(false);
        toast.info(checkoutResult?.error?.message || "Payment is still being confirmed. Your plan has not changed yet.");
        return;
      }
      toast.success(successText);
      await refreshMe();
      refetch();
      setReview(null);
      setWorking(false);
      return;
    }
    await loadRazorpayCheckout();
    const options = checkoutOptions(label);
    if (checkout.checkout_type === "subscription") {
      const modal = new window.Razorpay({
        ...options,
        key: checkout.checkout.key_id,
        subscription_id: checkout.checkout.subscription_id,
        handler: async () => {
          toast.success("Automatic renewal authorized. We are confirming your plan.");
          refetch();
          setReview(null);
          setWorking(false);
        },
      });
      modal.on("payment.failed", (result) => {
        setWorking(false);
        toast.error(result.error?.description || "Authorization was not completed");
      });
      modal.open();
      return;
    }
    const modal = new window.Razorpay({
      ...options,
      key: checkout.key_id,
      amount: checkout.amount_paise,
      currency: checkout.currency,
      order_id: checkout.order_id,
      notes: { invoice_id: checkout.invoice_id },
      handler: (result) => finishOrder(result, checkout, successText).catch((requestError) => {
        setWorking(false);
        toast.error(message(requestError, "Payment is being confirmed"));
      }),
    });
    modal.on("payment.failed", (result) => {
      setWorking(false);
      toast.error(result.error?.description || "Payment was not completed");
    });
    modal.open();
  };

  const confirmReview = async () => {
    if (!review || working) return;
    setWorking(true);
    try {
      if (review.kind === "pack") {
        const checkout = await createPackCheckout({
          packId: review.pack.id,
          idempotency_key: review.idempotencyKey,
        }).unwrap();
        await openProviderCheckout(checkout, `${review.pack.name} AI credits`, "AI credits added to your wallet");
        return;
      }
      if (recurringActive && review.plan.id !== activePlanId) {
        await scheduleChange({
          plan: review.plan.id,
          billing_interval: interval,
          timing: "cycle_end",
          replace_pending: Boolean(scheduled),
          reason: "Plan change requested by account owner",
          version: subscription.version,
        }).unwrap();
        toast.success(`${review.plan.name} is scheduled for the next renewal`);
        setReview(null);
        setWorking(false);
        refetch();
        return;
      }
      const checkout = await createCheckout({
        plan: review.plan.id,
        billing_interval: interval,
        renewal_mode: renewalMode,
        idempotency_key: review.idempotencyKey,
      }).unwrap();
      await openProviderCheckout(
        checkout,
        `${review.plan.name} - ${title(interval)}`,
        `${review.plan.name} is now active`,
      );
    } catch (requestError) {
      setWorking(false);
      toast.error(message(requestError, "Could not start checkout"));
    }
  };

  const undoScheduledChange = () => subscriptionActions.run("scheduled-change:remove", async () => {
    try {
      await removeScheduledPlanChange().unwrap();
      toast.success("The scheduled subscription change was removed");
      refetch();
    } catch (requestError) {
      toast.error(message(requestError, "Could not remove the scheduled change"));
    }
  });

  const requestCancellation = async ({ reason }) => {
    await cancelPlan({
      at_cycle_end: true,
      reason,
      version: subscription.version,
    }).unwrap();
    toast.success("Automatic renewal will stop at the end of this billing period");
    refetch();
  };

  const clearInvoiceFilters = () => {
    setInvoiceStatus("all");
    setPurchaseType("all");
  };

  const showCancellation = canManage
    && recurringActive
    && !subscription?.cancel_at_cycle_end
    && scheduled?.action !== "cancel";

  return <PageShell className="reveal pb-10" size="wide">
    <PageHeader
      eyebrow="Account billing"
      title="Plan & billing"
      description="Manage your subscription, AI credits, and payment records without mixing separate tasks."
    />

    <Tabs value={section} onValueChange={changeSection}>
      <div className="no-scrollbar max-w-full overflow-x-auto border-b">
        <TabsList className="h-auto min-w-max justify-start rounded-none border-0 bg-transparent p-0 shadow-none">
          {BILLING_SECTIONS.map(({ id, label, icon: Icon }) => <TabsTrigger
            key={id}
            value={id}
            className="h-11 gap-2 rounded-none border-b-2 border-transparent bg-transparent px-3.5 text-sm shadow-none data-[state=active]:border-accent data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"
          >
            <Icon size={17} weight={section === id ? "fill" : "regular"} />
            {label}
          </TabsTrigger>)}
        </TabsList>
      </div>

      {isLoading && !data ? <BillingPanelSkeleton section={section} />
        : error && !data ? <ErrorState
          className="mt-5"
          title="Billing could not be loaded"
          description="Your subscription has not changed. Try loading this section again."
          retry={refetch}
        />
          : <>
            <TabsContent value="subscription" className="mt-5">
              <SubscriptionPanel
                subscription={subscription}
                currentPlan={currentPlan}
                scheduled={scheduled}
                payment={payment}
                latestInvoice={recentInvoices[0]}
                settledCredits={settledCredits}
                usedCredits={usedCredits}
                usagePercent={usagePercent}
                creditDateLabel={creditDateLabel}
                planDateLabel={planDateLabel}
                trialExpired={trialExpired}
                canManage={canManage}
                showCancellation={showCancellation}
                removingSchedule={subscriptionActions.isPending("scheduled-change:remove")}
                onSection={changeSection}
                onCancel={() => setCancellationOpen(true)}
                onUndo={undoScheduledChange}
              />
            </TabsContent>

            <TabsContent value="plans" className="mt-5">
              <PlansPanel
                plans={plans}
                activePlanId={activePlanId}
                currentPlan={currentPlan}
                scheduled={scheduled}
                payment={payment}
                interval={interval}
                renewalMode={renewalMode}
                recurringSupported={recurringSupported}
                recurringActive={recurringActive}
                annualSaving={annualSaving}
                entityLabel={entityLabel}
                isCollege={isCollege}
                canManage={canManage}
                backgroundRefreshing={isFetching}
                reviewActions={reviewActions}
                onInterval={setInterval}
                onRenewalMode={setRenewalMode}
                onSelect={openPlanReview}
                onCompare={() => setComparisonOpen(true)}
              />
            </TabsContent>

            <TabsContent value="credits" className="mt-5">
              <CreditsPanel
                wallet={wallet}
                packs={packs}
                settledCredits={settledCredits}
                usedCredits={usedCredits}
                usagePercent={usagePercent}
                creditDateLabel={creditDateLabel}
                paymentConfigured={payment?.configured}
                canManage={canManage}
                onSelect={openPackReview}
              />
            </TabsContent>

            <TabsContent value="invoices" className="mt-5">
              <InvoicesPanel
                rows={invoiceItems}
                summary={invoiceSummary}
                status={invoiceStatus}
                purchaseType={purchaseType}
                loading={invoiceQuery.isLoading && !invoiceItems.length}
                fetching={invoiceQuery.isFetching}
                error={invoiceQuery.isError}
                hasMore={Boolean(invoicePage?.has_more)}
                nextCursor={invoicePage?.next_cursor}
                onStatus={setInvoiceStatus}
                onPurchaseType={setPurchaseType}
                onClear={clearInvoiceFilters}
                onLoadMore={() => invoicePaging.loadMore(invoicePage?.next_cursor)}
                onRetry={invoiceQuery.refetch}
              />
            </TabsContent>
          </>}
    </Tabs>

    <ComparisonSheet
      open={comparisonOpen}
      onOpenChange={setComparisonOpen}
      plans={plans.filter((plan) => plan.id !== "trial" && plan.purchasable)}
      featureRows={featureRows}
      entityLabel={entityLabel}
      isCollege={isCollege}
    />

    <ReviewSheet
      review={review}
      open={Boolean(review) && !hostedCheckoutActive}
      close={() => !working && setReview(null)}
      working={working}
      confirm={confirmReview}
      renewalMode={renewalMode}
      interval={interval}
      recurringActive={recurringActive}
      scheduled={scheduled}
    />

    <ValidatedActionDialog
      open={cancellationOpen}
      onOpenChange={setCancellationOpen}
      title="Stop automatic renewal?"
      description={`Your ${currentPlan?.name || "current"} plan remains active through ${date(subscription?.current_period_end)}.`}
      impact="The workspace keeps its current access until the term ends. You can undo this scheduled cancellation before it takes effect."
      schema={cancellationSchema}
      defaultValues={{ reason: "Subscription no longer required" }}
      fields={[{
        name: "reason",
        label: "Reason",
        type: "textarea",
        rows: 3,
        maxLength: 500,
      }]}
      submitLabel="Stop renewal"
      loadingText="Updating subscription..."
      variant="destructive"
      onSubmit={requestCancellation}
    />
  </PageShell>;
}

function SubscriptionPanel({
  subscription, currentPlan, scheduled, payment, latestInvoice, settledCredits,
  usedCredits, usagePercent, creditDateLabel, planDateLabel, trialExpired,
  canManage, showCancellation, removingSchedule, onSection, onCancel, onUndo,
}) {
  const renewalLabel = subscription?.cancel_at_cycle_end || scheduled?.action === "cancel"
    ? "Ends after this term"
    : subscription?.razorpay_subscription_id ? "Renews automatically" : "One-time term";
  const attentionStatus = ["past_due", "paused"].includes(subscription?.status);

  return <div className="space-y-4">
    {trialExpired && <Notice
      tone="warning"
      icon={ClockCountdown}
      title="Your trial has ended"
      description="Choose a paid plan to restore the plan-backed workspace capabilities."
      action={canManage && <Button size="sm" onClick={() => onSection("plans")}>Choose a plan<ArrowRight /></Button>}
    />}
    {attentionStatus && <Notice
      tone="danger"
      icon={Info}
      title="This subscription needs attention"
      description="Your existing records remain safe. Review the subscription before the current access period changes."
      action={canManage && <Button size="sm" onClick={() => onSection("plans")}>Review plans</Button>}
    />}
    {scheduled && <Notice
      tone="info"
      icon={CalendarBlank}
      title={scheduled.action === "cancel" ? "Renewal cancellation scheduled" : "Plan change scheduled"}
      description={`The change takes effect on ${date(scheduled.effective_at)}. Current access continues until then.`}
      action={canManage && <Button variant="outline" size="sm" loading={removingSchedule} loadingText="Removing..." onClick={onUndo}>Undo change</Button>}
    />}
    {payment && !payment.configured && <Notice
      tone="danger"
      icon={Info}
      title="Online checkout is unavailable"
      description="Your current subscription remains unchanged. Plan purchases and AI top-ups are temporarily paused."
    />}

    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Surface className="overflow-hidden">
        <div className="flex flex-col gap-5 p-5 sm:p-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 gap-4">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent/10 text-accent">
              <CreditCard size={22} weight="duotone" />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="overline text-accent">Current subscription</span>
                <StatusBadge status={subscription?.status || "trialing"} />
              </div>
              <h2 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
                {currentPlan?.name || title(subscription?.plan || "Trial")}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                {currentPlan?.description || "Your active plan controls workspace access and recurring AI allowance."}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {canManage && <Button onClick={() => onSection("plans")}>Change plan<ArrowRight /></Button>}
            {showCancellation && <Button variant="ghost" onClick={onCancel}>Stop renewal</Button>}
          </div>
        </div>

        <div className="grid gap-px border-y bg-border sm:grid-cols-2 xl:grid-cols-4">
          <SubscriptionFact label="Billing period" value={title(subscription?.billing_interval || "monthly")} />
          <SubscriptionFact label="Renewal" value={renewalLabel} />
          <SubscriptionFact label="Current access" value={planDateLabel} />
          <SubscriptionFact label="Included AI credits" value={format(currentPlan?.ai_credits || 0)} />
        </div>

        <div className="flex flex-col gap-3 bg-surface-subtle/55 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="text-xs leading-5 text-muted-foreground">Changes are applied only after provider confirmation or at the stated renewal date.</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => onSection("credits")}>AI credits</Button>
            <Button variant="ghost" size="sm" onClick={() => onSection("invoices")}>Billing history</Button>
          </div>
        </div>
      </Surface>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
        <Surface className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div><div className="overline">AI credits</div><div className="mt-2 font-display text-3xl font-semibold">{format(settledCredits)}</div><p className="mt-1 text-xs text-muted-foreground">available now</p></div>
            <span className="state-icon h-10 w-10 rounded-xl bg-accent/10 text-accent"><Wallet size={20} /></span>
          </div>
          <Progress value={100 - usagePercent} className="mt-4 [&>div]:bg-accent" aria-label={`${format(settledCredits)} AI credits available`} />
          <div className="mt-2 flex justify-between gap-3 text-[11px] text-muted-foreground"><span>{format(usedCredits)} used</span><span>{creditDateLabel}</span></div>
          <Button variant="outline" size="sm" className="mt-4 w-full" onClick={() => onSection("credits")}>{canManage ? "Add credits" : "View credits"}<ArrowRight /></Button>
        </Surface>

        <Surface className="p-5">
          <div className="flex items-start justify-between gap-3"><div className="overline">Latest payment</div><span className="state-icon h-10 w-10 rounded-xl"><Receipt size={20} /></span></div>
          {latestInvoice ? <>
            <div className="mt-3 flex items-center justify-between gap-3"><div className="font-display text-2xl font-semibold">{money(latestInvoice.amount_paise)}</div><StatusBadge status={latestInvoice.status} /></div>
            <div className="mt-2 truncate font-mono text-[11px] text-muted-foreground">{latestInvoice.invoice_number || `Invoice ${shortId(latestInvoice.id)}`}</div>
            <div className="mt-1 text-xs text-muted-foreground">{date(latestInvoice.created_at)}</div>
          </> : <div className="mt-3 text-sm text-muted-foreground">No payments have been recorded yet.</div>}
          <Button variant="outline" size="sm" className="mt-4 w-full" onClick={() => onSection("invoices")}>View invoices<ArrowRight /></Button>
        </Surface>
      </div>
    </div>
  </div>;
}

function PlansPanel({
  plans, activePlanId, currentPlan, scheduled, payment, interval, renewalMode,
  recurringSupported, recurringActive, annualSaving, entityLabel, isCollege,
  canManage, backgroundRefreshing, reviewActions, onInterval, onRenewalMode,
  onSelect, onCompare,
}) {
  const standardPlans = plans.filter((plan) => plan.id !== "trial" && plan.purchasable);
  const customPlans = plans.filter((plan) => plan.id !== "trial" && !plan.purchasable);

  return <div className="space-y-5">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h2 className="font-display text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">Choose the right capacity</h2>
        <p className="mt-1.5 text-sm text-muted-foreground">Compare tax-inclusive pricing and the limits that change daily work.</p>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <SegmentedControl label="Billing period">
          <Toggle active={interval === "monthly"} onClick={() => onInterval("monthly")}>Monthly</Toggle>
          <Toggle active={interval === "annual"} onClick={() => onInterval("annual")}>Annual {annualSaving > 0 && <span className="ml-1 text-positive">save {annualSaving}%</span>}</Toggle>
        </SegmentedControl>
        {canManage && <SegmentedControl label="Renewal">
          <Toggle disabled={!recurringSupported} active={renewalMode === "auto_renew"} onClick={() => onRenewalMode("auto_renew")}>Auto-renew</Toggle>
          <Toggle active={renewalMode === "one_time"} onClick={() => onRenewalMode("one_time")}>Pay once</Toggle>
        </SegmentedControl>}
      </div>
    </div>

    <Surface className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-secondary"><CheckCircle className="text-positive" weight="fill" /></span>
        <div className="min-w-0"><div className="text-sm font-semibold">Current plan: {currentPlan?.name || title(activePlanId)}</div><div className="mt-0.5 text-xs text-muted-foreground">{scheduled ? `A ${scheduled.action} is scheduled for ${date(scheduled.effective_at)}` : "No pending plan change"}</div></div>
      </div>
      {backgroundRefreshing && <span className="text-xs text-muted-foreground">Refreshing pricing...</span>}
    </Surface>

    {!recurringSupported && canManage && <Notice
      tone="info"
      icon={Info}
      title="One-time checkout is active"
      description="The current payment gateway does not support automatic renewal."
    />}
    {payment && !payment.configured && <Notice
      tone="danger"
      icon={Info}
      title="Plan checkout is unavailable"
      description="Pricing remains visible, but no plan will change until online checkout is restored."
    />}

    {standardPlans.length ? <ResponsiveCardGrid minWidth="17rem" className="items-stretch">
      {standardPlans.map((plan) => <PlanCard
        key={plan.id}
        plan={plan}
        interval={interval}
        current={activePlanId === plan.id}
        disabled={!canManage || !payment?.configured}
        loading={reviewActions.isPending(`plan:${plan.id}`)}
        action={() => onSelect(plan)}
        scheduled={recurringActive && activePlanId !== plan.id}
        entityLabel={entityLabel}
        isCollege={isCollege}
        canManage={canManage}
      />)}
    </ResponsiveCardGrid> : <EmptyState variant="section" icon={Crown} title="No paid plans are available" description="Your current subscription remains unchanged." />}

    {customPlans.map((plan) => <Surface key={plan.id} className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
      <div><div className="overline">Enterprise</div><h3 className="mt-1 font-display text-xl font-semibold">{plan.name}</h3><p className="mt-1 text-sm text-muted-foreground">{plan.description || "Custom limits, rollout support, and commercial terms."}</p></div>
      <Button asChild variant="outline"><a href="/#contact">Talk to sales<ArrowRight /></a></Button>
    </Surface>)}

    {standardPlans.length > 1 && <Surface className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
      <div><h3 className="font-display text-lg font-semibold">Need the complete comparison?</h3><p className="mt-1 text-sm text-muted-foreground">Review every limit and included capability without expanding this page.</p></div>
      <Button variant="outline" onClick={onCompare}>Compare all features<ArrowRight /></Button>
    </Surface>}
  </div>;
}

function CreditsPanel({
  wallet, packs, settledCredits, usedCredits, usagePercent, creditDateLabel,
  paymentConfigured, canManage, onSelect,
}) {
  return <div className="space-y-5">
    <Surface className="overflow-hidden">
      <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(280px,.7fr)] lg:items-center">
        <div>
          <div className="flex items-center gap-3"><span className="state-icon bg-accent/10 text-accent"><Wallet size={22} /></span><div><div className="overline text-accent">Available balance</div><h2 className="mt-1 font-display text-4xl font-semibold tracking-[-0.05em]">{format(settledCredits)} credits</h2></div></div>
          <Progress value={100 - usagePercent} className="mt-5 max-w-2xl [&>div]:bg-accent" aria-label={`${format(settledCredits)} AI credits available`} />
          <div className="mt-2 flex max-w-2xl flex-wrap justify-between gap-2 text-xs text-muted-foreground"><span>{format(usedCredits)} used from this cycle's grant</span><span>{creditDateLabel}</span></div>
        </div>
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border">
          <CreditFact label="Included each cycle" value={format(wallet?.cycle_grant_credits || 0)} />
          <CreditFact label="Reserved" value={format(wallet?.reserved_credits || 0)} />
        </div>
      </div>
    </Surface>

    <div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div><h2 className="font-display text-2xl font-semibold">One-time top-ups</h2><p className="mt-1 text-sm text-muted-foreground">Add credits without changing your subscription.</p></div>
        {!canManage && <span className="text-xs text-muted-foreground">Purchase access is limited to billing managers.</span>}
      </div>
      <div className="mt-4">
        {packs.length ? <ResponsiveCardGrid minWidth="14rem">
          {packs.map((pack) => <PackCard
            key={pack.id}
            pack={pack}
            canManage={canManage}
            paymentConfigured={paymentConfigured}
            onSelect={() => onSelect(pack)}
          />)}
        </ResponsiveCardGrid> : <EmptyState variant="section" icon={Wallet} title="Recharge packs are not available" description="Your current credits remain available." />}
      </div>
    </div>

    {!paymentConfigured && <Notice
      tone="danger"
      icon={Info}
      title="Top-ups are temporarily unavailable"
      description="Existing credits remain available and no charge has been created."
    />}
  </div>;
}

function InvoicesPanel({
  rows, summary, status, purchaseType, loading, fetching, error, hasMore,
  nextCursor, onStatus, onPurchaseType, onClear, onLoadMore, onRetry,
}) {
  const filtered = status !== "all" || purchaseType !== "all";
  const columns = [
    {
      key: "invoice_number",
      label: "Invoice",
      render: (invoice) => <div><div className="font-mono text-xs font-semibold">{invoice.invoice_number || `Invoice ${shortId(invoice.id)}`}</div><div className="mt-1 text-xs text-muted-foreground">{invoice.description || purchaseLabel(invoice.purchase_type)}</div></div>,
    },
    { key: "status", label: "Status", render: (invoice) => <StatusBadge status={invoice.status} /> },
    { key: "purchase_type", label: "Purchase", render: (invoice) => purchaseLabel(invoice.purchase_type) },
    { key: "created_at", label: "Date", render: (invoice) => date(invoice.created_at) },
    { key: "tax_paise", label: "Tax", className: "text-right", cellClassName: "text-right text-muted-foreground", render: (invoice) => money(invoice.tax_paise) },
    { key: "amount_paise", label: "Total", className: "text-right", cellClassName: "text-right font-semibold", render: (invoice) => money(invoice.amount_paise) },
  ];

  return <div className="space-y-4">
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <InvoiceMetric label="Invoices" value={format(summary?.total || 0)} />
      <InvoiceMetric label="Paid" value={format(summary?.paid || 0)} />
      <InvoiceMetric className="col-span-2 sm:col-span-1" label="Total invoiced" value={money(summary?.amount_paise || 0)} />
    </div>

    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div><h2 className="font-display text-2xl font-semibold">Invoices and payments</h2><p className="mt-1 text-sm text-muted-foreground">Plan purchases and AI-credit top-ups for this workspace.</p></div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Select value={purchaseType} onValueChange={onPurchaseType}>
          <SelectTrigger className="w-full sm:w-44" aria-label="Purchase type"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All purchases</SelectItem>
            <SelectItem value="plan">Plans</SelectItem>
            <SelectItem value="wallet_pack">AI credit top-ups</SelectItem>
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={onStatus}>
          <SelectTrigger className="w-full sm:w-40" aria-label="Invoice status"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="paid">Paid</SelectItem>
            <SelectItem value="created">Pending</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    {error && !rows.length ? <ErrorState
      title="Invoices could not be loaded"
      description="No billing records were changed. Try this view again."
      retry={onRetry}
    /> : <div className="overflow-hidden rounded-2xl border bg-card">
      <DataTable
        className="rounded-none border-0 shadow-none"
        rows={rows}
        columns={columns}
        density="compact"
        mobileColumns={6}
        loading={loading}
        caption="Workspace billing invoices"
        empty={<EmptyState
          variant={filtered ? "filtered" : "section"}
          alignment="left"
          icon={Receipt}
          title={filtered ? "No invoices match these filters" : "No billing history yet"}
          description={filtered ? "Clear the billing filters to see other records." : "The first completed plan or AI-credit purchase will appear here."}
          primaryAction={filtered ? <Button variant="outline" size="sm" onClick={onClear}>Clear filters</Button> : null}
        />}
      />
      <CursorListFooter
        count={rows.length}
        noun="invoices"
        hasMore={hasMore && Boolean(nextCursor)}
        loading={fetching}
        error={error && rows.length > 0}
        onLoadMore={onLoadMore}
        onRetry={onRetry}
        className="border-x-0 border-b-0 bg-surface-subtle/55"
      />
    </div>}
  </div>;
}

function PlanCard({
  plan, interval, current, disabled, loading, action, scheduled,
  entityLabel = "Clients", isCollege = false, canManage,
}) {
  const quote = interval === "annual" ? plan.annual_quote : plan.monthly_quote;
  const highlights = (plan.features || [])
    .filter((item) => !item.code.startsWith("module.") && !AI_COMPARISON_CODES.has(item.code))
    .slice(0, 3);
  const actionLabel = current ? "Current plan" : scheduled ? "Schedule change" : "Choose plan";

  return <article className={`relative flex h-full flex-col overflow-hidden rounded-2xl border bg-card p-5 transition-[border-color,box-shadow,transform] ${plan.recommended ? "border-accent/55 shadow-lg" : "shadow-sm"} ${current ? "ring-1 ring-positive/35" : "hover:-translate-y-0.5 hover:shadow-md"}`}>
    <div className={`absolute inset-x-0 top-0 h-1 ${plan.recommended ? "bg-accent" : current ? "bg-positive" : "bg-border"}`} />
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap gap-2">{plan.recommended && <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-accent"><Sparkle weight="fill" />Recommended</span>}{current && <StatusBadge status="active" label="Current" />}</div>
      {plan.id === "business" && <Crown size={20} className="text-warning" weight="duotone" />}
    </div>
    <h3 className="mt-4 font-display text-2xl font-semibold">{plan.name}</h3>
    <p className="mt-1.5 line-clamp-2 text-sm leading-5 text-muted-foreground">{plan.description}</p>
    <div className="mt-5"><span className="font-display text-3xl font-semibold tracking-[-0.05em]">{money(quote?.total_paise)}</span><span className="text-xs text-muted-foreground">/{interval === "annual" ? "year" : "month"}</span></div>
    <div className="mt-1 text-[10px] text-muted-foreground">{interval === "annual" ? `${money(quote?.total_paise / 12)} effective monthly` : plan.tax_enabled ? `${plan.gst_rate_bps / 100}% GST included` : "No GST on this plan"}</div>
    <div className="mt-5 grid grid-cols-2 gap-2 text-xs">
      <Stat value={limit(plan.employee_limit)} label={isCollege ? "faculty & staff" : "team"} />
      <Stat value={limit(plan.client_limit)} label={entityLabel.toLowerCase()} />
      <Stat value={limit(plan.location_limit)} label={isCollege ? "campuses" : "locations"} />
      <Stat value={format(plan.ai_credits)} label="AI credits" />
    </div>
    {!!highlights.length && <div className="mt-5 space-y-2">{highlights.map((item) => <div key={item.code} className="flex gap-2 text-xs leading-5"><Check size={16} className="mt-0.5 shrink-0 text-positive" />{item.name}</div>)}</div>}
    {canManage ? <Button type="button" className="mt-5 w-full" variant={current ? "outline" : "default"} disabled={disabled || current} loading={loading} loadingText="Preparing..." onClick={action}>{actionLabel}{!current && <ArrowRight />}</Button>
      : <div className="mt-5 rounded-xl bg-secondary px-3 py-2.5 text-center text-xs font-medium text-muted-foreground">View only</div>}
  </article>;
}

function PackCard({ pack, canManage, paymentConfigured, onSelect }) {
  const content = <>
    <div className="flex items-start justify-between gap-3"><span className="text-xs font-semibold text-muted-foreground">{pack.name}</span><Lightning size={18} className="text-accent" weight="fill" /></div>
    <div className="mt-4 font-display text-3xl font-semibold tracking-[-0.05em]">{format(pack.credits)}</div>
    <div className="text-xs text-muted-foreground">AI credits</div>
    <div className="mt-auto flex items-end justify-between gap-3 pt-5"><div><div className="text-sm font-semibold">{money(pack.quote?.total_paise)}</div><div className="mt-0.5 text-[10px] text-muted-foreground">Tax-inclusive total</div></div>{canManage && <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary transition group-hover:bg-primary group-hover:text-primary-foreground"><ArrowRight /></span>}</div>
  </>;
  const className = "group flex min-h-[168px] flex-col rounded-2xl border bg-card p-4 text-left shadow-sm transition-[border-color,box-shadow,transform]";
  if (!canManage) return <article className={className}>{content}</article>;
  return <button type="button" onClick={onSelect} disabled={!paymentConfigured} className={`${className} hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-md disabled:pointer-events-none disabled:opacity-50`}>{content}</button>;
}

function ComparisonSheet({ open, onOpenChange, plans, featureRows, entityLabel, isCollege }) {
  const rows = comparisonRows(featureRows, entityLabel, isCollege);
  return <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent className="w-full overflow-y-auto sm:max-w-5xl">
      <SheetHeader>
        <SheetTitle className="font-display text-2xl">Compare plan capabilities</SheetTitle>
        <SheetDescription>Limits and included features from the currently published plans.</SheetDescription>
      </SheetHeader>
      <div className="mt-6 hidden overflow-hidden rounded-2xl border lg:block">
        <div className="premium-scrollbar overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead><tr className="border-b bg-secondary/60"><th className="p-4 text-left font-semibold">Capability</th>{plans.map((plan) => <th key={plan.id} className="p-4 text-center font-semibold">{plan.name}</th>)}</tr></thead>
            <tbody className="divide-y">{rows.map((row) => <tr key={row.code}><td className="p-4 text-muted-foreground">{row.name}</td>{plans.map((plan) => <td key={plan.id} className="p-4 text-center">{comparisonValue(row.value(plan))}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </div>
      <div className="mt-6 space-y-3 lg:hidden">{rows.map((row) => <section key={row.code} className="rounded-xl border p-4"><h3 className="text-sm font-semibold">{row.name}</h3><div className="mt-3 divide-y">{plans.map((plan) => <div key={plan.id} className="flex items-center justify-between gap-4 py-2 text-sm"><span className="text-muted-foreground">{plan.name}</span><span className="text-right font-medium">{comparisonValue(row.value(plan))}</span></div>)}</div></section>)}</div>
    </SheetContent>
  </Sheet>;
}

function ReviewSheet({ review, open, close, working, confirm, renewalMode, interval, recurringActive, scheduled }) {
  const quote = review?.quote;
  const label = review?.kind === "pack" ? review.pack.name : review?.plan?.name;
  const isSchedule = review?.kind === "plan" && recurringActive;
  return <Sheet open={open} onOpenChange={(value) => !value && close()}>
    <SheetContent className="overflow-y-auto sm:max-w-lg">
      <SheetHeader><SheetTitle className="font-display text-2xl">Review your {review?.kind === "pack" ? "top-up" : "plan"}</SheetTitle><SheetDescription>Nothing changes until you confirm below.</SheetDescription></SheetHeader>
      {review && <div className="mt-6 space-y-5">
        <div className="rounded-2xl border bg-surface-subtle p-5"><div className="overline text-accent">{review.kind === "pack" ? "AI credits" : title(interval)}</div><div className="mt-2 font-display text-2xl font-semibold">{label}</div>{review.kind === "pack" && <div className="mt-1 text-sm text-muted-foreground">{format(review.pack.credits)} credits</div>}</div>
        <div className="divide-y rounded-2xl border"><PriceRow label="Price" value={money(quote?.total_paise - quote?.tax_paise)} />{quote?.tax_enabled && <PriceRow label={`GST (${quote.gst_rate_bps / 100}%)`} value={money(quote.tax_paise)} muted />}<PriceRow label="Total" value={money(quote?.total_paise)} strong /></div>
        <div className="space-y-3 rounded-2xl bg-secondary/60 p-4 text-sm">
          <ReviewLine icon={CalendarBlank}>{review.kind === "pack" ? `Credits expire ${date(review.pack.expires_at)}` : isSchedule ? "Starts after your current billing cycle" : interval === "annual" ? "12 months of plan access" : "One month of plan access"}</ReviewLine>
          {review.kind === "plan" && <ReviewLine icon={Lightning}>{isSchedule ? scheduled ? "Replaces the currently scheduled change" : "No charge today for a cycle-end change" : renewalMode === "auto_renew" ? "Renews automatically until cancelled" : "Does not renew automatically"}</ReviewLine>}
          <ReviewLine icon={ShieldCheck}>Access changes only after provider confirmation</ReviewLine>
        </div>
        <Button className="h-11 w-full" loading={working} loadingText="Preparing secure checkout..." onClick={confirm}>{isSchedule ? "Schedule for next renewal" : `Continue to pay ${money(quote?.total_paise)}`}</Button>
      </div>}
    </SheetContent>
  </Sheet>;
}

function Notice({ tone = "info", icon: Icon, title: noticeTitle, description, action }) {
  const toneClass = tone === "danger"
    ? "border-destructive/25 bg-destructive/5"
    : tone === "warning" ? "border-warning/30 bg-warning-soft" : "border-info/20 bg-info/5";
  return <section className={`flex flex-col justify-between gap-3 rounded-2xl border px-4 py-3.5 sm:flex-row sm:items-center ${toneClass}`}>
    <div className="flex min-w-0 gap-3"><Icon size={21} className="mt-0.5 shrink-0" /><div><div className="text-sm font-semibold">{noticeTitle}</div><p className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</p></div></div>{action}
  </section>;
}

function SubscriptionFact({ label, value }) { return <div className="bg-card px-5 py-4"><div className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted-foreground">{label}</div><div className="mt-1.5 text-sm font-semibold">{value}</div></div>; }
function CreditFact({ label, value }) { return <div className="bg-card p-4"><div className="text-[10px] font-semibold uppercase tracking-[.1em] text-muted-foreground">{label}</div><div className="mt-1.5 font-display text-xl font-semibold">{value}</div></div>; }
function InvoiceMetric({ label, value, className = "" }) { return <Surface className={`p-4 sm:p-5 ${className}`}><div className="text-xs text-muted-foreground">{label}</div><div className="mt-2 font-display text-2xl font-semibold tracking-[-0.04em]">{value}</div></Surface>; }
function SegmentedControl({ label, children }) { return <div><div className="mb-1 ml-1 text-[9px] font-bold uppercase tracking-[.14em] text-muted-foreground">{label}</div><div role="group" aria-label={label} className="flex rounded-xl border bg-card p-1 shadow-sm">{children}</div></div>; }
function Toggle({ active, children, onClick, disabled = false }) { return <button type="button" aria-pressed={active} disabled={disabled} onClick={onClick} className={`rounded-lg px-3 py-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-45 ${active ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}>{children}</button>; }
function Stat({ value, label }) { return <div className="rounded-xl bg-secondary/60 p-2.5"><strong className="block text-foreground">{value}</strong><span className="text-muted-foreground">{label}</span></div>; }
function PriceRow({ label, value, strong, muted }) { return <div className={`flex justify-between p-4 ${strong ? "text-lg font-bold" : ""} ${muted ? "text-muted-foreground" : ""}`}><span>{label}</span><span>{value}</span></div>; }
function ReviewLine({ icon: Icon, children }) { return <div className="flex gap-2.5"><Icon size={19} className="shrink-0 text-positive" /><span>{children}</span></div>; }

function BillingPanelSkeleton({ section }) {
  return <div className="mt-5 space-y-4" aria-label={`Loading ${section}`}>
    <Skeleton className="h-20 w-full rounded-2xl" />
    <div className="grid gap-4 lg:grid-cols-3"><Skeleton className="h-56 rounded-2xl lg:col-span-2" /><Skeleton className="h-56 rounded-2xl" /></div>
  </div>;
}

function comparisonRows(featureRows, entityLabel, isCollege) {
  return [
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
}

function comparisonValue(value) {
  if (typeof value !== "boolean") return value;
  return value
    ? <CheckCircle weight="fill" className="inline text-positive" size={19} aria-label="Included" />
    : <span className="text-muted-foreground/55">Not included</span>;
}

function purchaseLabel(value) {
  if (value === "wallet_pack") return "AI credit top-up";
  if (value === "plan") return "Plan";
  return title(value || "Purchase");
}

function money(paise = 0) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise || 0) / 100); }
function format(value = 0) { return new Intl.NumberFormat("en-IN").format(Number(value || 0)); }
function date(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "Not set"; }
function title(value = "") { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function shortId(value = "") { return String(value || "").slice(0, 8).toUpperCase() || "Pending"; }
function limit(value) { return value == null ? "Unlimited" : format(value); }
function storage(mb) { return mb == null ? "Custom" : mb >= 1024 ? `${format(mb / 1024)} GB` : `${format(mb)} MB`; }
function message(requestError, fallback) { return requestError?.data?.detail || requestError?.response?.data?.detail || requestError?.message || fallback; }
