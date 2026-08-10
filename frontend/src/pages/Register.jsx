import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight, Barbell, Check, CheckCircle, CircleNotch, CreditCard,
  GraduationCap, LockKey, Scissors, ShieldCheck, Stethoscope, XCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import PasswordStrength, { isPasswordAcceptable } from "@/components/PasswordStrength";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { loadRazorpayCheckout } from "@/lib/razorpay";

const industries = [
  { id: "gym", label: "Gym & fitness", icon: Barbell, desc: "Memberships, check-ins and coaching" },
  { id: "salon", label: "Salon & spa", icon: Scissors, desc: "Appointments, services and checkout" },
  { id: "clinic", label: "Outpatient clinic", icon: Stethoscope, desc: "Queue, clinical records, lab and pharmacy" },
  { id: "college", label: "College & higher education", icon: GraduationCap, desc: "Student readiness, coding and placements" },
];

const businessId = (value) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
const money = (paise) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise || 0) / 100);
const savedCheckoutKey = "edvatiq.pending_signup_checkout.v1";

function readSavedCheckout() {
  try {
    const value = JSON.parse(sessionStorage.getItem(savedCheckoutKey) || "null");
    if (value?.expires_at && new Date(value.expires_at).getTime() <= Date.now() && value.status !== "completed") {
      sessionStorage.removeItem(savedCheckoutKey);
      return null;
    }
    return value;
  }
  catch { return null; }
}

export default function Register() {
  const { registerOrg } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState(null);
  const [catalogError, setCatalogError] = useState("");
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [interval, setInterval] = useState(searchParams.get("interval") === "annual" ? "annual" : "monthly");
  const [selectedPlanId, setSelectedPlanId] = useState(searchParams.get("plan") || "");
  const [checkoutSession, setCheckoutSession] = useState(readSavedCheckout);
  const [slugState, setSlugState] = useState({ status: "idle", message: "", suggestions: [] });
  const [form, setForm] = useState({
    industry: "gym", organization_name: "", organization_slug: "", location_name: "Main Location",
    city: "", state: "", admin_first_name: "", admin_last_name: "", admin_email: "",
    admin_password: "", admin_password_confirm: "",
  });
  const set = (key) => (event) => {
    const value = event.target.value;
    setForm((old) => ({ ...old, [key]: value, ...(key === "organization_name" && !old.organization_slug ? { organization_slug: businessId(value) } : {}) }));
  };

  useEffect(() => {
    const controller = new AbortController();
    setCatalogError("");
    api.get("/billing/public/plans", { signal: controller.signal, forceRefetch: true })
      .then(({ data }) => setCatalog(data))
      .catch((error) => { if (error.code !== "ERR_CANCELED") setCatalogError("Plans could not be loaded. Please try again."); });
    return () => controller.abort();
  }, [catalogAttempt]);

  useEffect(() => {
    if (!catalog?.plans?.length) return;
    const requested = catalog.plans.find((plan) => plan.id === selectedPlanId && plan.signup_mode !== "contact");
    if (requested) return;
    const fallback = catalog.trial_enabled
      ? catalog.plans.find((plan) => plan.id === "trial")
      : catalog.plans.find((plan) => plan.recommended && plan.purchasable) || catalog.plans.find((plan) => plan.purchasable);
    setSelectedPlanId(fallback?.id || "");
  }, [catalog, selectedPlanId]);

  useEffect(() => {
    const value = form.organization_slug;
    if (!value || value.length < 2) { setSlugState({ status: "idle", message: value ? "Use at least 2 characters" : "", suggestions: [] }); return undefined; }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) { setSlugState({ status: "invalid", message: "Use lowercase letters, numbers, and single hyphens", suggestions: [] }); return undefined; }
    if (checkoutSession?.organization_slug === value && checkoutSession?.status === "ready" && new Date(checkoutSession.expires_at).getTime() > Date.now()) { setSlugState({ status: "available", message: "Reserved for your pending checkout", suggestions: [] }); return undefined; }
    const controller = new AbortController();
    setSlugState({ status: "checking", message: "Checking availability...", suggestions: [] });
    const timer = setTimeout(() => api.get("/auth/organization-id/availability", { params: { value }, signal: controller.signal })
      .then(({ data }) => setSlugState({ status: data.available ? "available" : "taken", message: data.message, suggestions: data.suggestions || [] }))
      .catch((error) => { if (error.code !== "ERR_CANCELED") setSlugState({ status: "error", message: "Could not check right now. Try again.", suggestions: [] }); }), 350);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [form.organization_slug, checkoutSession]);

  const detailsReady = Boolean(form.organization_name.trim() && form.location_name.trim() && slugState.status === "available");
  const passwordReady = isPasswordAcceptable(form.admin_password);
  const passwordsMatch = Boolean(form.admin_password_confirm && form.admin_password_confirm === form.admin_password);
  const ownerReady = Boolean(form.admin_first_name.trim() && form.admin_email.trim() && passwordReady && passwordsMatch);
  const selectedPlan = catalog?.plans?.find((plan) => plan.id === selectedPlanId);
  const selectedQuote = interval === "annual" ? selectedPlan?.annual_quote : selectedPlan?.monthly_quote;
  const isTrial = selectedPlan?.signup_mode === "trial";

  const finishRegistration = (result) => {
    const pending = { email: result.email, org_slug: result.organization_slug, email_sent: result.email_sent };
    sessionStorage.removeItem(savedCheckoutKey);
    setCheckoutSession(null);
    sessionStorage.setItem("edvatiq.pending_verification", JSON.stringify(pending));
    toast.success(result.email_sent === false ? "Workspace created. Configure email or resend the code." : "Verification code sent");
    navigate("/verify-email", { state: pending });
  };

  const waitForCompletedCheckout = async (session) => {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const { data } = await api.get(`/auth/registration/checkouts/${session.checkout_id}`, { headers: { "X-Signup-Token": session.checkout_token }, forceRefetch: true });
      if (data.status === "completed") return data;
      if (["expired", "failed", "manual_review"].includes(data.status)) throw new Error(data.status === "manual_review" ? "Payment needs support review" : "This checkout can no longer be completed");
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }
    return null;
  };

  const runPaidCheckout = async (session) => {
    if (session.mock_mode) {
      const { data } = await api.post(`/auth/registration/checkouts/${session.checkout_id}/mock-pay`, { checkout_token: session.checkout_token });
      return data;
    }
    await loadRazorpayCheckout();
    const payment = await new Promise((resolve, reject) => {
      let completed = false;
      const checkout = new window.Razorpay({
        key: session.key_id,
        amount: session.amount_paise,
        currency: session.currency,
        order_id: session.order_id,
        name: "Edvatiq",
        description: `${session.plan?.name || "Edvatiq"} ${interval} plan`,
        prefill: { name: `${form.admin_first_name} ${form.admin_last_name}`.trim() || session.first_name, email: form.admin_email || session.email },
        theme: { color: "#0f4938" },
        handler: (response) => { completed = true; resolve(response); },
        modal: { ondismiss: () => { if (!completed) reject(Object.assign(new Error("Payment window closed"), { code: "PAYMENT_DISMISSED" })); } },
      });
      checkout.on("payment.failed", (response) => reject(new Error(response.error?.description || "Payment failed")));
      checkout.open();
    });
    const { data } = await api.post("/auth/registration/payment/verify", {
      checkout_id: session.checkout_id,
      checkout_token: session.checkout_token,
      razorpay_order_id: payment.razorpay_order_id,
      razorpay_payment_id: payment.razorpay_payment_id,
      razorpay_signature: payment.razorpay_signature,
    });
    if (data.status === "completed") return data;
    return await waitForCompletedCheckout(session);
  };

  const resumeCheckout = async () => {
    if (!checkoutSession) return;
    setLoading(true);
    try {
      const { data: status } = await api.get(`/auth/registration/checkouts/${checkoutSession.checkout_id}`, { headers: { "X-Signup-Token": checkoutSession.checkout_token }, forceRefetch: true });
      if (status.status === "completed") { finishRegistration(status); return; }
      if (status.status !== "ready") throw new Error("This checkout has expired. Please start a new one.");
      const result = await runPaidCheckout({ ...checkoutSession, ...status, checkout_token: checkoutSession.checkout_token });
      if (result) finishRegistration(result);
      else toast.info("Payment received. We are still confirming it; use Resume payment to check again.");
    } catch (error) {
      if (error.code === "PAYMENT_DISMISSED") toast.info("Payment was not completed. Your details are safely reserved for 24 hours.");
      else toast.error(error.response?.data?.detail || error.message || "Could not resume checkout");
    } finally { setLoading(false); }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (step !== 4 || !selectedPlan) return;
    if (!passwordReady) { toast.error("Please choose a stronger password"); return; }
    if (!passwordsMatch) { toast.error("Passwords do not match"); return; }
    setLoading(true);
    try {
      const payload = { ...form };
      delete payload.admin_password_confirm;
      if (isTrial) {
        const result = await registerOrg(payload);
        finishRegistration(result);
        return;
      }
      if (!catalog.payment_available) throw new Error("Secure checkout is temporarily unavailable");
      const reusable = checkoutSession
        && checkoutSession.organization_slug === form.organization_slug
        && checkoutSession.plan_id === selectedPlan.id
        && checkoutSession.billing_interval === interval;
      const idempotencyKey = reusable ? checkoutSession.idempotency_key : crypto.randomUUID();
      const { data: checkout } = await api.post("/auth/registration/checkout", {
        ...payload,
        plan: selectedPlan.id,
        billing_interval: interval,
        idempotency_key: idempotencyKey,
        ...(reusable ? { checkout_token: checkoutSession.checkout_token } : {}),
      });
      const session = {
        ...checkout,
        idempotency_key: idempotencyKey,
        plan_id: selectedPlan.id,
        billing_interval: interval,
        organization_slug: form.organization_slug,
        email: form.admin_email,
        first_name: form.admin_first_name,
      };
      setCheckoutSession(session);
      sessionStorage.setItem(savedCheckoutKey, JSON.stringify(session));
      const result = await runPaidCheckout(session);
      if (result) finishRegistration(result);
      else toast.info("Payment received. Account creation is waiting for provider confirmation.");
    } catch (error) {
      const detail = error.response?.data?.detail || error.message || "Could not create your workspace";
      if (detail.includes("Free trial is unavailable")) {
        setSelectedPlanId("");
        setCatalogAttempt((value) => value + 1);
        toast.info("Trial availability changed. Choose a paid plan to continue.");
        return;
      }
      if (detail.includes("plan is not available for new accounts")) {
        setSelectedPlanId("");
        setCatalogAttempt((value) => value + 1);
        toast.info("Plan availability changed. Please choose another plan.");
        return;
      }
      if (detail.includes("slug") || detail.includes("Business ID")) {
        setStep(2); setSlugState({ status: "taken", message: detail, suggestions: [] });
      }
      if (error.code === "PAYMENT_DISMISSED") toast.info("Payment was not completed. You can resume when ready.");
      else toast.error(detail);
    } finally { setLoading(false); }
  };

  return <div className="auth-shell min-h-screen bg-background lg:grid lg:grid-cols-[minmax(320px,.72fr)_minmax(0,1.28fr)]">
    <aside className="auth-aside auth-register-aside relative hidden flex-col justify-between overflow-hidden bg-primary text-primary-foreground lg:flex"><div className="paper-grid absolute inset-0 opacity-10" /><Link to="/" className="relative font-display text-3xl font-bold">Edvatiq</Link><div className="relative max-w-md"><div className="overline text-accent">A workspace worth entering</div><h1 className="auth-register-title mt-4 font-display text-5xl font-bold leading-[1.02] xl:text-6xl">Start with clarity, not setup noise.</h1><div className="auth-register-benefits mt-7 space-y-3 text-sm text-white/65">{["Choose the workspace built for your industry", "Know the full first-term price before account creation", "Confirm your email and invite the right team"].map((text) => <div className="flex gap-2" key={text}><CheckCircle className="shrink-0 text-accent" />{text}</div>)}</div></div><div className="relative flex items-center gap-2 text-sm text-white/45"><ShieldCheck /> Secure checkout / GST-ready / Permission scoped</div></aside>
    <main className="auth-main min-w-0"><div className="auth-register-inner mx-auto w-full max-w-3xl"><div className="auth-mobile-brand mb-6 font-display text-3xl font-bold lg:hidden"><Link to="/">Edvatiq</Link></div>
      {checkoutSession?.status === "ready" && <div className="mb-5 flex flex-col gap-3 rounded-xl border border-accent/25 bg-accent/5 p-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="text-sm font-semibold">A secure checkout is waiting</div><div className="mt-1 text-xs text-muted-foreground">{checkoutSession.organization_slug} is reserved until {new Date(checkoutSession.expires_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}.</div></div><Button type="button" variant="outline" disabled={loading} onClick={resumeCheckout}>{loading ? "Checking..." : "Resume payment"}</Button></div>}
      <div className="mb-6 flex gap-2">{[1, 2, 3, 4].map((item) => <div key={item} className={`h-1.5 flex-1 rounded-full ${item <= step ? "bg-accent" : "bg-secondary"}`} />)}</div>
      <form onSubmit={submit}>
        {step === 1 && <section><StepTitle step={1} title="Choose your organization type." text="This shapes terminology, navigation, and the workflows available on day one." /><div className="mt-6 grid gap-3 sm:grid-cols-2">{industries.map((item) => <button type="button" key={item.id} onClick={() => setForm((old) => ({ ...old, industry: item.id }))} className={`rounded-2xl border p-4 text-left transition-colors ${form.industry === item.id ? "border-accent bg-accent/5 ring-2 ring-accent/15" : "bg-card hover:bg-secondary/50"}`}><item.icon size={26} /><div className="mt-3 font-semibold">{item.label}</div><div className="mt-1.5 text-xs text-muted-foreground">{item.desc}</div></button>)}</div><Button type="button" className="mt-6 w-full rounded-xl" onClick={() => setStep(2)}>Continue</Button></section>}
        {step === 2 && <section><StepTitle step={2} title="Name your workspace." text="Your Workspace ID is used at sign in and cannot be silently reassigned." /><div className="mt-6 grid gap-4 sm:grid-cols-2"><Field label="Organization name"><Input required value={form.organization_name} onChange={set("organization_name")} /></Field><Field label="Workspace ID"><div className="relative"><Input required value={form.organization_slug} onChange={(event) => setForm((old) => ({ ...old, organization_slug: businessId(event.target.value) }))} aria-describedby="business-id-status" className={slugState.status === "available" ? "border-emerald-500 pr-10" : ["taken", "invalid"].includes(slugState.status) ? "border-red-400 pr-10" : "pr-10"} />{slugState.status === "checking" && <CircleNotch className="absolute right-3 top-2.5 animate-spin text-muted-foreground" />}{slugState.status === "available" && <CheckCircle weight="fill" className="absolute right-3 top-2.5 text-emerald-600" />}{["taken", "invalid", "error"].includes(slugState.status) && <XCircle weight="fill" className="absolute right-3 top-2.5 text-red-500" />}</div><div id="business-id-status" className={`mt-1.5 text-xs ${slugState.status === "available" ? "text-emerald-700" : ["taken", "invalid", "error"].includes(slugState.status) ? "text-red-600" : "text-muted-foreground"}`}>{slugState.message}</div>{slugState.suggestions?.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{slugState.suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setForm((old) => ({ ...old, organization_slug: suggestion }))} className="rounded-full border px-2.5 py-1 text-[11px] hover:border-accent">{suggestion}</button>)}</div>}</Field><Field label="Primary location"><Input required value={form.location_name} onChange={set("location_name")} /></Field><Field label="City"><Input value={form.city} onChange={set("city")} /></Field></div><Nav back={() => setStep(1)} next={() => detailsReady && setStep(3)} disabled={!detailsReady} /></section>}
        {step === 3 && <section><StepTitle step={3} title="Create the workspace owner." text="This person receives full administrative access and the verification code." /><div className="mt-6 grid gap-4 sm:grid-cols-2"><Field label="First name"><Input required value={form.admin_first_name} onChange={set("admin_first_name")} /></Field><Field label="Last name"><Input value={form.admin_last_name} onChange={set("admin_last_name")} /></Field><div className="sm:col-span-2"><Field label="Work email"><Input type="email" autoComplete="email" required value={form.admin_email} onChange={set("admin_email")} /></Field></div><div className="sm:col-span-2"><Field label="Password"><Input type="password" autoComplete="new-password" minLength={10} required value={form.admin_password} onChange={set("admin_password")} /><PasswordStrength password={form.admin_password} compact /></Field></div><div className="sm:col-span-2"><Field label="Confirm password"><Input type="password" autoComplete="new-password" minLength={10} required value={form.admin_password_confirm} onChange={set("admin_password_confirm")} />{form.admin_password_confirm && <p className={`mt-1 text-xs ${passwordsMatch ? "text-emerald-700" : "text-red-600"}`}>{passwordsMatch ? "Passwords match" : "Passwords do not match"}</p>}</Field></div></div><Nav back={() => setStep(2)} next={() => ownerReady && setStep(4)} disabled={!ownerReady} /></section>}
        {step === 4 && <section><StepTitle step={4} title="Choose how you want to start." text={catalog?.trial_enabled ? "Select Trial or pay securely for your first plan term." : "Trial is currently unavailable. Your account is created only after successful payment."} />
          {!isTrial && <div className="mt-6 max-w-sm"><Field label="Billing state"><Input required value={form.state} onChange={set("state")} placeholder="Tamil Nadu" /><p className="text-xs text-muted-foreground">Used to create the correct GST invoice snapshot.</p></Field></div>}
          {catalogError && <div className="mt-6 rounded-xl border bg-card p-5 text-center"><p className="text-sm font-semibold">{catalogError}</p><Button type="button" variant="outline" className="mt-3" onClick={() => setCatalogAttempt((value) => value + 1)}>Try again</Button></div>}
          {!catalog && !catalogError && <div className="mt-6 grid gap-3 sm:grid-cols-2">{[1, 2, 3, 4].map((item) => <div key={item} className="h-40 animate-pulse rounded-2xl border bg-card" />)}</div>}
          {catalog && <><div className="mt-6 flex w-fit rounded-xl border bg-card p-1">{[["monthly", "Monthly"], ["annual", "Annual"]].map(([value, label]) => <button type="button" key={value} onClick={() => setInterval(value)} className={`rounded-lg px-4 py-2 text-sm font-semibold ${interval === value ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>{label}</button>)}</div><div className="mt-4 grid gap-3 sm:grid-cols-2">{catalog.plans.filter((plan) => plan.signup_mode !== "contact").map((plan) => <PlanChoice key={plan.id} plan={plan} interval={interval} selected={selectedPlanId === plan.id} onSelect={() => setSelectedPlanId(plan.id)} />)}</div>{catalog.plans.some((plan) => plan.signup_mode === "contact") && <a href="mailto:sales@edvatiq.com?subject=Edvatiq%20Enterprise" className="mt-3 flex items-center justify-between rounded-xl border bg-card px-4 py-3 text-sm font-semibold">Need enterprise scale? Talk to sales <ArrowRight /></a>}</>}
          {selectedPlan && <div className="mt-5 rounded-2xl border bg-surface-subtle p-4"><div className="flex items-start justify-between gap-4"><div><div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Your selection</div><div className="mt-1 text-lg font-semibold">{selectedPlan.name} / {isTrial ? `${selectedPlan.trial_days || 30}-day trial` : interval}</div></div><div className="text-right"><div className="text-xl font-semibold">{isTrial ? "Free" : selectedQuote ? money(selectedQuote.total_paise) : "Unavailable"}</div>{selectedQuote?.tax_paise > 0 && <div className="text-[11px] text-muted-foreground">Includes {money(selectedQuote.tax_paise)} GST</div>}</div></div>{!isTrial && <div className="mt-4 flex items-start gap-2 border-t pt-4 text-xs text-muted-foreground"><LockKey className="shrink-0" />No workspace or owner account is created until Razorpay confirms the payment.</div>}</div>}
          <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row"><Button type="button" variant="outline" onClick={() => setStep(3)}>Back</Button><Button disabled={loading || !selectedPlan || (!isTrial && (!form.state.trim() || !selectedQuote || !catalog?.payment_available))} className="flex-1">{loading ? <><CircleNotch className="mr-2 animate-spin" />Please wait</> : isTrial ? "Create trial workspace" : selectedQuote ? <><CreditCard className="mr-2" />Pay {money(selectedQuote.total_paise)} and create workspace</> : "Plan unavailable"}</Button></div>
        </section>}
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">Already use Edvatiq? <Link to="/login" className="font-medium text-foreground">Sign in</Link></p>
    </div></main>
  </div>;
}

function StepTitle({ step, title, text }) { return <div><div className="overline">Step {step} of 4</div><h2 className="mt-2 font-display text-3xl font-bold md:text-4xl">{title}</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">{text}</p></div>; }
function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function Nav({ back, next, disabled }) { return <div className="mt-6 flex gap-3"><Button type="button" variant="outline" onClick={back}>Back</Button><Button type="button" className="flex-1" disabled={disabled} onClick={next}>Continue</Button></div>; }

function PlanChoice({ plan, interval, selected, onSelect }) {
  const quote = interval === "annual" ? plan.annual_quote : plan.monthly_quote;
  const trial = plan.signup_mode === "trial";
  return <button type="button" onClick={onSelect} className={`relative rounded-2xl border p-4 text-left transition-colors ${selected ? "border-primary bg-primary/5 ring-2 ring-primary/10" : "bg-card hover:bg-secondary/50"}`}><div className="flex items-start justify-between gap-3"><div><div className="font-semibold">{plan.name}</div><div className="mt-1 text-xs text-muted-foreground">{trial ? `${plan.trial_days || 30} days` : interval === "annual" ? "Billed for one year" : "Billed for one month"}</div></div><span className={`grid h-6 w-6 place-items-center rounded-full border ${selected ? "border-primary bg-primary text-primary-foreground" : ""}`}>{selected && <Check size={14} weight="bold" />}</span></div><div className="mt-5 text-xl font-semibold">{trial ? "Free" : quote ? money(quote.total_paise) : "Unavailable"}</div><div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground"><CheckCircle className="text-positive" weight="fill" />{Number(plan.ai_credits || 0).toLocaleString("en-IN")} AI credits</div>{plan.recommended && <span className="absolute bottom-3 right-3 rounded-full bg-primary px-2 py-1 text-[9px] font-semibold uppercase tracking-wider text-primary-foreground">Recommended</span>}</button>;
}
