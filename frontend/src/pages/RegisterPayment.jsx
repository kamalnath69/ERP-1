import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, ArrowRight, CheckCircle, Clock, CreditCard,
  LockKey, ShieldCheck, WarningCircle, XCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import {
  CancelCheckoutDialog, CheckoutSummary, PaymentSecurityNote, RegistrationPanel, RegistrationShell,
} from "@/components/registration/RegistrationLayout";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import api from "@/lib/api";
import { loadCashfreeCheckout } from "@/lib/cashfree";
import { loadRazorpayCheckout } from "@/lib/razorpay";
import {
  boundedSignupRequest, clearSignupCheckout, readSignupCheckout, storePendingVerification,
  updateSignupCheckout,
} from "@/lib/signupRegistration";

const money = (paise) => new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
}).format(Number(paise || 0) / 100);

const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export default function RegisterPayment() {
  const { checkoutId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const stored = useRef(readSignupCheckout()).current;
  const token = stored?.checkout_id === checkoutId ? stored.checkout_token : null;
  const [view, setView] = useState(() => token
    ? { status: "loading", checkout: stored, error: "" }
    : { status: "missing", checkout: null, error: "" });
  const [pending, setPending] = useState({ handoff: false, reconciling: false, cancelling: false });
  const [cancelOpen, setCancelOpen] = useState(false);
  const mounted = useRef(true);
  const handoffWatchdog = useRef(null);
  const initialRequest = useRef(false);
  const setPendingState = (name, value) => {
    if (mounted.current) setPending((current) => ({ ...current, [name]: value }));
  };

  const finishRegistration = (result) => {
    const pending = storePendingVerification(result);
    toast.success(result.email_sent === false
      ? "Workspace created. Configure email or resend the code."
      : result.email_sent === true ? "Payment confirmed. Verification code sent." : "Payment confirmed. Continue to email verification.");
    navigate("/verify-email", { state: pending, replace: true });
  };

  const acceptCheckout = (data) => {
    if (!mounted.current) return data;
    updateSignupCheckout(data);
    if (data.next_action === "verify_email" || data.status === "completed") {
      finishRegistration(data);
      return data;
    }
    setView({ status: "ready", checkout: data, error: "" });
    return data;
  };

  const requestStatus = async ({ reconcile = false, confirm = false, announce = false } = {}) => {
    if (!token) return null;
    setPendingState("reconciling", true);
    try {
      const request = () => boundedSignupRequest((signal) => reconcile
        ? api.post(`/auth/registration/checkouts/${checkoutId}/reconcile`, {}, {
          headers: { "X-Signup-Token": token }, signal,
        })
        : api.get(`/auth/registration/checkouts/${checkoutId}`, {
          headers: { "X-Signup-Token": token }, forceRefetch: true, signal,
        }));
      let { data } = await request();
      acceptCheckout(data);

      if (confirm && data.next_action === "wait") {
        for (let attempt = 0; attempt < 4 && mounted.current; attempt += 1) {
          await wait(1200 + attempt * 500);
          ({ data } = await boundedSignupRequest((signal) => api.post(
            `/auth/registration/checkouts/${checkoutId}/reconcile`, {},
            { headers: { "X-Signup-Token": token }, signal },
          )));
          acceptCheckout(data);
          if (data.next_action !== "wait") break;
        }
      }
      if (announce && data.next_action === "wait") {
        toast.info("Payment is still being confirmed. You can check again shortly.");
      }
      return data;
    } catch (error) {
      const message = error.response?.data?.detail || error.message || "Checkout status could not be loaded";
      if (view.status === "loading") setView({ status: "error", checkout: stored, error: message });
      else toast.error(message);
      return null;
    } finally {
      setPendingState("reconciling", false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (handoffWatchdog.current) window.clearTimeout(handoffWatchdog.current);
    };
  }, []);

  useEffect(() => {
    if (!token || initialRequest.current) return;
    initialRequest.current = true;
    const returned = searchParams.get("returned") === "1";
    void requestStatus({ reconcile: returned, confirm: returned, announce: returned }).then((data) => {
      if (returned && mounted.current && data?.next_action !== "verify_email" && data?.status !== "completed") {
        navigate(`/register/payment/${checkoutId}`, { replace: true });
      }
    });
    // The initial status transition must run exactly once for this route instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkoutId, token]);

  const restoreAfterHandoff = (message) => {
    if (handoffWatchdog.current) window.clearTimeout(handoffWatchdog.current);
    handoffWatchdog.current = null;
    if (!mounted.current) return;
    setPendingState("handoff", false);
    if (message) toast.error(message);
  };

  const beginCashfree = async (checkout) => {
    try {
      setPendingState("handoff", true);
      handoffWatchdog.current = window.setTimeout(() => {
        restoreAfterHandoff();
        toast.info("The payment page did not open. You can safely try again.");
      }, 13000);
      await loadCashfreeCheckout();
      if (!checkout.payment_session_id) throw new Error("This payment session is unavailable. Check its status or restart checkout.");
      const cashfree = window.Cashfree({
        mode: checkout.checkout_mode || (checkout.mode === "test" ? "sandbox" : "production"),
      });
      const providerPromise = cashfree.checkout({
        paymentSessionId: checkout.payment_session_id,
        redirectTarget: "_self",
      });
      Promise.resolve(providerPromise).then((result) => {
        if (result?.error) restoreAfterHandoff(result.error.message || "Cashfree could not open checkout");
      }).catch((error) => restoreAfterHandoff(error.message || "Cashfree could not open checkout"));
    } catch (error) {
      restoreAfterHandoff(error.message || "Cashfree checkout could not be loaded");
    }
  };

  const verifyRazorpay = async (result) => {
    setPendingState("handoff", false);
    setPendingState("reconciling", true);
    try {
      const { data } = await boundedSignupRequest((signal) => api.post("/auth/registration/payment/verify", {
        checkout_id: checkoutId,
        checkout_token: token,
        razorpay_order_id: result.razorpay_order_id,
        razorpay_payment_id: result.razorpay_payment_id,
        razorpay_signature: result.razorpay_signature,
      }, { signal }));
      acceptCheckout(data);
      if (data.next_action === "wait") toast.info("Payment received. We are confirming your workspace.");
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || "Payment confirmation failed");
    } finally {
      setPendingState("reconciling", false);
    }
  };

  const beginRazorpay = async (checkout) => {
    try {
      setPendingState("handoff", true);
      handoffWatchdog.current = window.setTimeout(() => {
        restoreAfterHandoff();
        toast.info("The payment window did not open. You can safely try again.");
      }, 13000);
      await loadRazorpayCheckout();
      if (!checkout.key_id || !checkout.order_id) throw new Error("This payment session is unavailable. Check its status or restart checkout.");
      const modal = new window.Razorpay({
        key: checkout.key_id,
        amount: checkout.amount_paise,
        currency: checkout.currency,
        order_id: checkout.order_id,
        name: "Edvatiq",
        description: `${checkout.plan?.name || "Plan"} registration`,
        handler: (result) => { void verifyRazorpay(result); },
        modal: { ondismiss: () => { setPendingState("handoff", false); } },
        theme: { color: "#0f4a38" },
      });
      modal.on("payment.failed", (result) => {
        setPendingState("handoff", false);
        toast.error(result.error?.description || "Payment was not completed");
      });
      modal.open();
      if (handoffWatchdog.current) window.clearTimeout(handoffWatchdog.current);
      handoffWatchdog.current = null;
    } catch (error) {
      setPendingState("handoff", false);
      toast.error(error.message || "Razorpay checkout could not be loaded");
    }
  };

  const completeMockPayment = async () => {
    setPendingState("handoff", true);
    try {
      const { data } = await boundedSignupRequest((signal) => api.post(
        `/auth/registration/checkouts/${checkoutId}/mock-pay`,
        { checkout_token: token }, { signal },
      ));
      acceptCheckout(data);
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || "Test payment failed");
    } finally {
      setPendingState("handoff", false);
    }
  };

  const beginPayment = () => {
    const checkout = view.checkout;
    if (!checkout || pending.handoff || pending.reconciling || pending.cancelling) return;
    if (checkout.mock_mode || checkout.mode === "mock") { void completeMockPayment(); return; }
    if (checkout.provider === "cashfree") { void beginCashfree(checkout); return; }
    void beginRazorpay(checkout);
  };

  const cancelCheckout = async () => {
    setPendingState("cancelling", true);
    try {
      await boundedSignupRequest((signal) => api.post(
        `/auth/registration/checkouts/${checkoutId}/cancel`, {},
        { headers: { "X-Signup-Token": token }, signal },
      ));
      clearSignupCheckout();
      setCancelOpen(false);
      toast.success("Checkout cancelled. Review your registration details before trying again.");
      navigate("/register", { replace: true });
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || "Checkout could not be cancelled");
      if (error.response?.status === 409) void requestStatus({ reconcile: true });
    } finally {
      setPendingState("cancelling", false);
    }
  };

  const restart = () => {
    clearSignupCheckout();
    navigate("/register", { replace: true });
  };

  return <RegistrationShell currentStep={5}>
    <PaymentView
      view={view}
      pending={pending}
      retry={() => { setView((current) => ({ ...current, status: "loading", error: "" })); void requestStatus(); }}
      checkStatus={() => { void requestStatus({ reconcile: view.checkout?.provider === "cashfree", confirm: true, announce: true }); }}
      pay={beginPayment}
      cancel={() => setCancelOpen(true)}
      restart={restart}
    />
    <CancelCheckoutDialog
      open={cancelOpen}
      onOpenChange={setCancelOpen}
      loading={pending.cancelling}
      onConfirm={() => { void cancelCheckout(); }}
    />
  </RegistrationShell>;
}

function PaymentView({ view, pending, retry, checkStatus, pay, cancel, restart }) {
  if (view.status === "missing") return <RegistrationPanel>
    <StatusHeader icon={WarningCircle} eyebrow="Payment recovery" title="This checkout is not available in this browser" text="For security, the checkout recovery token is stored only in the browser that created it." tone="warning" />
    <div className="mt-7 flex flex-col gap-3 sm:flex-row"><Button asChild><Link to="/register">Return to registration</Link></Button><Button asChild variant="outline"><Link to="/login">Sign in</Link></Button></div>
  </RegistrationPanel>;

  if (view.status === "loading") return <RegistrationPanel aside={<SummarySkeleton />}>
    <div className="space-y-5" aria-busy="true" aria-live="polite"><Skeleton className="h-10 w-10 rounded-xl" /><Skeleton className="h-4 w-32" /><Skeleton className="h-11 w-4/5" /><Skeleton className="h-20 w-full" /><Skeleton className="h-12 w-full" /></div>
  </RegistrationPanel>;

  if (view.status === "error") return <RegistrationPanel>
    <StatusHeader icon={WarningCircle} eyebrow="Checkout status" title="We could not load this checkout" text={view.error} tone="warning" />
    <div className="mt-7 flex flex-col gap-3 sm:flex-row"><Button type="button" onClick={retry}>Try again</Button><Button asChild variant="outline"><Link to="/register"><ArrowLeft />Back to registration</Link></Button></div>
  </RegistrationPanel>;

  const checkout = view.checkout;
  const quote = {
    subtotal_paise: checkout.subtotal_paise,
    tax_paise: checkout.tax_paise,
    total_paise: checkout.amount_paise,
  };
  const summary = <CheckoutSummary
    plan={{ ...(checkout.plan || {}), signup_mode: "paid" }}
    quote={quote}
    interval={checkout.billing_interval}
    money={money}
    organizationName={checkout.organization_name}
  />;

  if (checkout.next_action === "restart") return <RegistrationPanel aside={summary}>
    <StatusHeader icon={XCircle} eyebrow="Checkout closed" title="Start a fresh payment session" text="This checkout expired, failed, or was cancelled. Your safe registration details remain available." tone="danger" />
    <CheckoutFacts checkout={checkout} />
    <div className="mt-7 flex flex-col gap-3 sm:flex-row"><Button type="button" onClick={restart}>Return to registration <ArrowRight /></Button><Button asChild variant="outline"><Link to="/login">Sign in instead</Link></Button></div>
  </RegistrationPanel>;

  if (checkout.next_action === "support") return <RegistrationPanel aside={summary}>
    <StatusHeader icon={ShieldCheck} eyebrow="Manual review" title="Your payment needs support review" text="We detected a payment for an inactive checkout. No workspace will be created automatically while the payment is reviewed." tone="warning" />
    <CheckoutFacts checkout={checkout} />
    <div className="mt-7 flex flex-col gap-3 sm:flex-row"><Button asChild><Link to="/#contact">Contact Edvatiq</Link></Button><Button type="button" variant="outline" loading={pending.reconciling} loadingText="Checking..." onClick={checkStatus}>Check again</Button></div>
  </RegistrationPanel>;

  const waiting = checkout.next_action === "wait";
  return <RegistrationPanel aside={summary}>
    <StatusHeader
      icon={waiting ? Clock : CreditCard}
      eyebrow={waiting ? "Confirming payment" : "Secure payment"}
      title={waiting ? "We are confirming your payment" : "Complete your first plan payment"}
      text={waiting
        ? "This usually completes shortly. You may leave this page and return with the same browser."
        : "You will continue to the selected payment provider. Your workspace is created only after confirmation."}
      tone={waiting ? "warning" : "default"}
    />
    <CheckoutFacts checkout={checkout} />
    <div className="mt-6"><PaymentSecurityNote provider={checkout.provider} /></div>
    <div className="mt-7 flex flex-col gap-3">
      {!waiting && <Button type="button" size="lg" loading={pending.handoff} loadingText="Opening payment..." disabled={pending.cancelling || pending.reconciling} onClick={pay}>Pay {money(checkout.amount_paise)} securely <ArrowRight /></Button>}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center">
        <Button asChild variant="ghost"><Link to="/register"><ArrowLeft />Back to registration</Link></Button>
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" loading={pending.reconciling} loadingText="Checking..." disabled={pending.cancelling} onClick={checkStatus}>Check payment status</Button>
          <Button type="button" variant="ghost" disabled={pending.cancelling || pending.reconciling} onClick={cancel}>Cancel and edit</Button>
        </div>
      </div>
    </div>
    <p className="sr-only" role="status" aria-live="polite">{pending.handoff ? "Opening payment provider" : pending.reconciling ? "Checking payment status" : pending.cancelling ? "Cancelling checkout" : ""}</p>
  </RegistrationPanel>;
}

function StatusHeader({ icon: Icon, eyebrow, title, text, tone }) {
  const tones = {
    default: "bg-primary/10 text-primary",
    warning: "bg-amber-100 text-amber-700",
    danger: "bg-red-100 text-red-700",
  };
  return <header><span className={`grid h-11 w-11 place-items-center rounded-xl ${tones[tone] || tones.default}`}><Icon size={22} weight="duotone" /></span><div className="overline mt-5 text-primary">{eyebrow}</div><h1 className="mt-2 font-display text-3xl font-bold tracking-[-0.035em] sm:text-4xl">{title}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">{text}</p></header>;
}

function CheckoutFacts({ checkout }) {
  const expires = checkout.expires_at ? new Date(checkout.expires_at) : null;
  return <dl className="mt-6 grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2">
    <Fact label="Provider" value={checkout.provider === "cashfree" ? "Cashfree" : checkout.provider === "razorpay" ? "Razorpay" : "Test checkout"} icon={LockKey} />
    <Fact label="Payment status" value={checkout.status?.replaceAll("_", " ") || "Ready"} icon={CheckCircle} />
    <Fact label="Billing period" value={checkout.billing_interval === "annual" ? "Annual" : "Monthly"} icon={CreditCard} />
    <Fact label="Session expires" value={expires && !Number.isNaN(expires.valueOf()) ? expires.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Not available"} icon={Clock} />
  </dl>;
}

function Fact({ label, value, icon: Icon }) {
  return <div className="flex items-start gap-3 bg-card p-4"><Icon className="mt-0.5 shrink-0 text-muted-foreground" /><div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</dt><dd className="mt-1 text-sm font-medium capitalize">{value}</dd></div></div>;
}

function SummarySkeleton() {
  return <div className="rounded-2xl border bg-card p-5"><Skeleton className="h-3 w-24" /><Skeleton className="mt-4 h-6 w-36" /><Skeleton className="mt-6 h-px w-full" /><Skeleton className="mt-5 h-24 w-full" /></div>;
}
