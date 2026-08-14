import React, { useEffect, useRef, useState } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, ArrowRight, Barbell, Buildings, Check, CheckCircle, CircleNotch,
  CreditCard, GraduationCap, MapPin, PencilSimple, Scissors, Stethoscope, UserCircle, XCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import PasswordStrength from "@/components/PasswordStrength";
import {
  CancelCheckoutDialog, CheckoutSummary, RegistrationPanel, RegistrationShell,
} from "@/components/registration/RegistrationLayout";
import { Button } from "@/components/ui/button";
import { FieldError, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import {
  boundedSignupRequest, clearSignupCheckout, readSignupCheckout, readSignupDraft,
  saveSignupCheckout, saveSignupDraft, storePendingVerification,
} from "@/lib/signupRegistration";
import {
  applyApiErrors, registrationOrganizationSchema, registrationOwnerSchema, registrationSchema,
} from "@/lib/validation";

const industries = [
  { id: "gym", label: "Gym & fitness", icon: Barbell, desc: "Memberships, coaching, and daily operations" },
  { id: "salon", label: "Salon & spa", icon: Scissors, desc: "Bookings, services, and client retention" },
  { id: "clinic", label: "Outpatient clinic", icon: Stethoscope, desc: "Patient flow, records, lab, and pharmacy" },
  { id: "college", label: "College", icon: GraduationCap, desc: "Academic evidence, readiness, and placements" },
];

const businessId = (value) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
const money = (paise) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise || 0) / 100);
const blankDefaults = {
  industry: "gym", organization_name: "", organization_slug: "", location_name: "Main Location",
  city: "", state: "", admin_first_name: "", admin_last_name: "", admin_email: "",
  admin_phone: "", admin_password: "", admin_password_confirm: "", plan: "",
  billing_interval: "monthly", legal_accepted: false,
};

export default function Register() {
  const { registerOrg } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialDraft = useRef(readSignupDraft()).current;
  const requestedPlan = searchParams.get("plan") || initialDraft.plan || "";
  const requestedInterval = searchParams.get("interval") === "annual" || initialDraft.billing_interval === "annual" ? "annual" : "monthly";
  const [step, setStep] = useState(1);
  const [catalogState, setCatalogState] = useState({ status: "loading", data: null, error: "" });
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [legal, setLegal] = useState({ status: "loading", ready: false, documents: {}, error: "" });
  const [interval, setInterval] = useState(requestedInterval);
  const [selectedPlanId, setSelectedPlanId] = useState(requestedPlan);
  const [slugState, setSlugState] = useState({ status: "idle", message: "", suggestions: [] });
  const [savedCheckout, setSavedCheckout] = useState(() => readSignupCheckout());
  const [recovery, setRecovery] = useState(() => savedCheckout ? { status: "loading", checkout: null, error: "" } : null);
  const [recoveryAction, setRecoveryAction] = useState("");
  const [cancelOpen, setCancelOpen] = useState(false);
  const checkoutAttempt = useRef(null);

  const methods = useForm({
    resolver: zodResolver(registrationSchema),
    mode: "onChange",
    reValidateMode: "onChange",
    shouldFocusError: true,
    defaultValues: {
      ...blankDefaults,
      ...initialDraft,
      plan: requestedPlan,
      billing_interval: requestedInterval,
      admin_password: "",
      admin_password_confirm: "",
      legal_accepted: false,
    },
  });
  const {
    register, handleSubmit, setValue, setError, clearErrors, trigger, reset, watch,
    formState: { errors, isSubmitting },
  } = methods;
  const form = watch();
  const catalog = catalogState.data;
  const selectedPlan = catalog?.plans?.find((plan) => plan.id === selectedPlanId);
  const selectedQuote = interval === "annual" ? selectedPlan?.annual_quote : selectedPlan?.monthly_quote;
  const isTrial = selectedPlan?.signup_mode === "trial";
  const paymentProvider = catalog?.payment?.provider || catalog?.provider || "razorpay";
  const detailsValid = registrationOrganizationSchema.safeParse(form).success && slugState.status === "available";
  const ownerValid = registrationOwnerSchema.safeParse(form).success
    && (isTrial || paymentProvider !== "cashfree" || Boolean(form.admin_phone));
  const registrationValid = registrationSchema.safeParse(form).success
    && (isTrial || Boolean(form.state?.trim()));

  const finishRegistration = (result) => {
    const pending = storePendingVerification(result);
    toast.success(result.email_sent === false
      ? "Workspace created. Configure email or resend the code."
      : result.email_sent === true ? "Verification code sent" : "Workspace ready. Continue to email verification.");
    navigate("/verify-email", { state: pending, replace: true });
  };

  const recoverCheckout = async (checkout = savedCheckout) => {
    if (!checkout) return;
    setRecovery({ status: "loading", checkout: null, error: "" });
    try {
      const { data } = await boundedSignupRequest((signal) => api.get(
        `/auth/registration/checkouts/${checkout.checkout_id}`,
        { headers: { "X-Signup-Token": checkout.checkout_token }, forceRefetch: true, signal },
      ));
      saveSignupCheckout({ ...checkout, ...data, checkout_token: checkout.checkout_token });
      setSavedCheckout({ ...checkout, ...data, checkout_token: checkout.checkout_token });
      if (data.next_action === "verify_email") { finishRegistration(data); return; }
      setRecovery({ status: "ready", checkout: data, error: "" });
    } catch (error) {
      setRecovery({ status: "error", checkout: null, error: error.response?.data?.detail || error.message || "Checkout status could not be loaded" });
    }
  };

  useEffect(() => {
    if (savedCheckout?.checkout_id) recoverCheckout(savedCheckout);
    // A checkout is recovered once per stored identity; explicit retries call recoverCheckout directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedCheckout?.checkout_id]);

  useEffect(() => {
    let active = true;
    setCatalogState({ status: "loading", data: null, error: "" });
    api.get("/billing/public/plans", { forceRefetch: true })
      .then(({ data }) => { if (active) setCatalogState({ status: "ready", data, error: "" }); })
      .catch(() => { if (active) setCatalogState({ status: "error", data: null, error: "Plans could not be loaded. Please try again." }); });
    return () => { active = false; };
  }, [catalogAttempt]);

  useEffect(() => {
    let active = true;
    api.get("/public/legal/current", { forceRefetch: true })
      .then(({ data }) => { if (active) setLegal({ status: "ready", ready: Boolean(data.ready), documents: data.documents || {}, error: "" }); })
      .catch(() => { if (active) setLegal({ status: "error", ready: false, documents: {}, error: "Registration policies could not be loaded." }); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!catalog?.plans?.length) return;
    const requested = catalog.plans.find((plan) => plan.id === selectedPlanId && plan.signup_mode !== "contact" && plan.purchasable !== false);
    if (requested) return;
    const fallback = catalog.trial_enabled
      ? catalog.plans.find((plan) => plan.id === "trial")
      : catalog.plans.find((plan) => plan.recommended && plan.purchasable) || catalog.plans.find((plan) => plan.purchasable && plan.signup_mode !== "contact");
    setSelectedPlanId(fallback?.id || "");
  }, [catalog, selectedPlanId]);

  useEffect(() => {
    setValue("plan", selectedPlanId, { shouldValidate: Boolean(selectedPlanId) });
  }, [selectedPlanId, setValue]);

  useEffect(() => {
    setValue("billing_interval", interval, { shouldValidate: true });
  }, [interval, setValue]);

  useEffect(() => {
    saveSignupDraft(form);
  }, [
    form.industry, form.organization_name, form.organization_slug, form.location_name, form.city,
    form.state, form.admin_first_name, form.admin_last_name, form.admin_email, form.admin_phone,
    form.plan, form.billing_interval,
  ]);

  useEffect(() => {
    if (savedCheckout) return undefined;
    const value = form.organization_slug;
    if (!value || value.length < 2) {
      setSlugState({ status: "idle", message: value ? "Use at least 2 characters" : "", suggestions: [] });
      return undefined;
    }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) {
      setSlugState({ status: "invalid", message: "Use lowercase letters, numbers, and single hyphens", suggestions: [] });
      return undefined;
    }
    const controller = new AbortController();
    setSlugState({ status: "checking", message: "Checking availability...", suggestions: [] });
    const timer = window.setTimeout(() => api.get("/auth/organization-id/availability", { params: { value }, signal: controller.signal })
      .then(({ data }) => {
        if (data.available) clearErrors("organization_slug");
        setSlugState({ status: data.available ? "available" : "taken", message: data.message, suggestions: data.suggestions || [] });
      })
      .catch((error) => {
        if (error.code !== "ERR_CANCELED") setSlugState({ status: "error", message: "Could not check right now. Try again.", suggestions: [] });
      }), 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [form.organization_slug, savedCheckout, clearErrors]);

  const cancelCheckout = async () => {
    if (!savedCheckout) return;
    setRecoveryAction("cancelling");
    try {
      await boundedSignupRequest((signal) => api.post(
        `/auth/registration/checkouts/${savedCheckout.checkout_id}/cancel`,
        {},
        { headers: { "X-Signup-Token": savedCheckout.checkout_token }, signal },
      ));
      clearSignupCheckout();
      setSavedCheckout(null);
      setRecovery(null);
      setCancelOpen(false);
      reset({ ...blankDefaults, ...readSignupDraft(), admin_password: "", admin_password_confirm: "", legal_accepted: false });
      setStep(1);
      toast.success("Checkout cancelled. You can update the registration details.");
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || "Checkout could not be cancelled");
      if (error.response?.status === 409) await recoverCheckout(savedCheckout);
    } finally { setRecoveryAction(""); }
  };

  const startOver = () => {
    clearSignupCheckout();
    setSavedCheckout(null);
    setRecovery(null);
    reset({ ...blankDefaults, ...readSignupDraft(), admin_password: "", admin_password_confirm: "", legal_accepted: false });
    setStep(1);
  };

  const continueWorkspace = async () => {
    clearErrors("root.server");
    const valid = await trigger(["organization_name", "organization_slug", "location_name", "city"], { shouldFocus: true });
    if (!valid) return;
    if (slugState.status !== "available") {
      setError("organization_slug", {
        type: "availability",
        message: slugState.status === "checking" ? "Wait for the Workspace ID check to finish" : slugState.message || "Choose an available Workspace ID",
      }, { shouldFocus: true });
      return;
    }
    setStep(3);
  };

  const continueOwner = async () => {
    clearErrors("root.server");
    const valid = await trigger([
      "admin_first_name", "admin_last_name", "admin_email", "admin_phone",
      "admin_password", "admin_password_confirm",
    ], { shouldFocus: true });
    if (valid && !isTrial && paymentProvider === "cashfree" && !form.admin_phone) {
      setError("admin_phone", { type: "required", message: "Phone number is required for Cashfree checkout" }, { shouldFocus: true });
      return;
    }
    if (valid) setStep(4);
  };

  const submit = async (values) => {
    if (step !== 4 || !selectedPlan) return;
    clearErrors("root.server");
    if (!legal.ready) {
      setError("root.server", { type: "legal", message: "Registration is temporarily unavailable until the current legal documents are published." });
      return;
    }
    if (!isTrial && !values.state?.trim()) {
      setError("state", { type: "required", message: "Billing state is required for the GST invoice" }, { shouldFocus: true });
      return;
    }
    try {
      const {
        admin_password_confirm: _confirm, plan: _plan, billing_interval: _billingInterval,
        legal_accepted: accepted, ...registration
      } = values;
      const payload = {
        ...registration,
        legal_acceptance: {
          accepted,
          terms_document_id: legal.documents.terms.id,
          privacy_document_id: legal.documents.privacy.id,
          refund_document_id: legal.documents.refund.id,
        },
      };
      if (isTrial) {
        const result = await registerOrg(payload);
        finishRegistration(result);
        return;
      }
      if (!catalog.payment_available) throw new Error("Secure checkout is temporarily unavailable");
      const signature = JSON.stringify([values.organization_slug, values.admin_email, selectedPlan.id, interval, values.state]);
      if (!checkoutAttempt.current || checkoutAttempt.current.signature !== signature) {
        checkoutAttempt.current = {
          signature,
          key: crypto.randomUUID(),
          token: `${crypto.randomUUID()}${crypto.randomUUID()}`,
        };
      }
      const { data: checkout } = await api.post("/auth/registration/checkout", {
        ...payload,
        plan: selectedPlan.id,
        billing_interval: interval,
        idempotency_key: checkoutAttempt.current.key,
        checkout_token: checkoutAttempt.current.token,
      });
      const session = saveSignupCheckout({
        ...checkout,
        checkout_token: checkout.checkout_token,
        plan_id: selectedPlan.id,
        billing_interval: interval,
      });
      setSavedCheckout(session);
      navigate(`/register/payment/${checkout.checkout_id}`);
    } catch (error) {
      if (error.response) checkoutAttempt.current = null;
      const normalized = applyApiErrors(error, setError, { fallback: "Could not create your workspace" });
      const detail = normalized.message;
      if (detail.includes("Free trial is unavailable") || detail.includes("plan is not available for new accounts")) {
        setSelectedPlanId("");
        setCatalogAttempt((value) => value + 1);
        setStep(1);
        toast.info("Plan availability changed. Please choose another plan.");
        return;
      }
      if (detail.includes("slug") || detail.includes("Business ID")) {
        setStep(2);
        setSlugState({ status: "taken", message: detail, suggestions: [] });
        setError("organization_slug", { type: "server", message: detail });
      } else toast.error(detail);
    }
  };

  if (recovery) {
    return <RegistrationShell currentStep={5}>
      <RecoveryPanel
        recovery={recovery}
        checkout={savedCheckout}
        action={recoveryAction}
        retry={() => recoverCheckout(savedCheckout)}
        continuePayment={() => navigate(`/register/payment/${savedCheckout.checkout_id}`)}
        cancel={() => setCancelOpen(true)}
        startOver={startOver}
      />
      <CancelCheckoutDialog open={cancelOpen} onOpenChange={setCancelOpen} loading={recoveryAction === "cancelling"} onConfirm={cancelCheckout} />
    </RegistrationShell>;
  }

  const summary = <CheckoutSummary plan={selectedPlan} quote={selectedQuote} interval={interval} money={money} organizationName={form.organization_name} />;

  return <FormProvider {...methods}><RegistrationShell currentStep={step}>
    <form onSubmit={handleSubmit(submit)} noValidate>
      {step === 1 && <RegistrationPanel wide>
        <StepTitle eyebrow="Plan" title="Choose the right starting point" text="Pick a plan and billing period first. You can review the exact total before checkout." />
        <FormRootError error={errors.root?.server} className="mt-5" />
        {catalogState.status === "loading" && <PlanSkeleton />}
        {catalogState.status === "error" && <LoadError message={catalogState.error} retry={() => setCatalogAttempt((value) => value + 1)} />}
        {catalog && <>
          <div className="mt-6 inline-flex w-full rounded-xl border bg-secondary/45 p-1 sm:w-auto">{[["monthly", "Monthly"], ["annual", "Annual"]].map(([value, label]) => <button type="button" key={value} onClick={() => setInterval(value)} className={`flex-1 rounded-lg px-5 py-2.5 text-sm font-semibold transition-colors sm:flex-none ${interval === value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>{label}</button>)}</div>
          <div className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-4">{catalog.plans.map((plan) => plan.signup_mode === "contact"
            ? <ContactPlanChoice key={plan.id} plan={plan} />
            : <PlanChoice key={plan.id} plan={plan} interval={interval} selected={selectedPlanId === plan.id} onSelect={() => setSelectedPlanId(plan.id)} />)}</div>
          <div className="mt-7 flex justify-end"><Button type="button" size="lg" disabled={!selectedPlan || selectedPlan.signup_mode === "contact" || selectedPlan.purchasable === false} onClick={() => setStep(2)}>Continue to workspace <ArrowRight /></Button></div>
        </>}
      </RegistrationPanel>}

      {step === 2 && <RegistrationPanel aside={summary}>
        <StepTitle eyebrow="Workspace" title="Set up your organization" text="Choose the operating model, business identity, and primary location for this workspace." />
        <FormRootError error={errors.root?.server} className="mt-5" />
        <div className="mt-6 grid gap-3 sm:grid-cols-2">{industries.map((item) => <button type="button" key={item.id} onClick={() => setValue("industry", item.id, { shouldDirty: true, shouldValidate: true })} className={`rounded-xl border p-4 text-left transition-all ${form.industry === item.id ? "border-primary bg-primary/5 ring-2 ring-primary/10" : "bg-background hover:border-foreground/20"}`} aria-pressed={form.industry === item.id}><div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-secondary"><item.icon size={19} /></span><span><span className="block text-sm font-semibold">{item.label}</span><span className="mt-1 block text-[11px] leading-4 text-muted-foreground">{item.desc}</span></span></div></button>)}</div>
        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          <Field label="Organization name" htmlFor="organization-name" error={errors.organization_name}><Input id="organization-name" {...register("organization_name", { onChange: (event) => { if (!form.organization_slug) setValue("organization_slug", businessId(event.target.value), { shouldDirty: true }); } })} aria-invalid={Boolean(errors.organization_name)} /></Field>
          <Field label="Workspace ID" htmlFor="organization-slug" error={errors.organization_slug}><WorkspaceIdField register={register} setValue={setValue} state={slugState} error={errors.organization_slug} /></Field>
          <Field label="Primary location" htmlFor="location-name" error={errors.location_name}><Input id="location-name" {...register("location_name")} aria-invalid={Boolean(errors.location_name)} /></Field>
          <Field label="City" htmlFor="city" error={errors.city}><Input id="city" {...register("city")} aria-invalid={Boolean(errors.city)} /></Field>
        </div>
        <WizardActions back={() => setStep(1)} next={continueWorkspace} disabled={!detailsValid} />
      </RegistrationPanel>}

      {step === 3 && <RegistrationPanel aside={summary}>
        <StepTitle eyebrow="Owner" title="Create the workspace owner" text="This account receives administrative access and the email verification code." />
        <FormRootError error={errors.root?.server} className="mt-5" />
        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          <Field label="First name" htmlFor="admin-first-name" error={errors.admin_first_name}><Input id="admin-first-name" {...register("admin_first_name")} autoComplete="given-name" aria-invalid={Boolean(errors.admin_first_name)} /></Field>
          <Field label="Last name" htmlFor="admin-last-name" error={errors.admin_last_name}><Input id="admin-last-name" {...register("admin_last_name")} autoComplete="family-name" aria-invalid={Boolean(errors.admin_last_name)} /></Field>
          <Field label="Work email" htmlFor="admin-email" error={errors.admin_email}><Input id="admin-email" type="email" autoComplete="email" {...register("admin_email")} aria-invalid={Boolean(errors.admin_email)} /></Field>
          <Field label="Phone" htmlFor="admin-phone" error={errors.admin_phone}><Input id="admin-phone" type="tel" autoComplete="tel" {...register("admin_phone")} aria-invalid={Boolean(errors.admin_phone)} /><p className="text-xs text-muted-foreground">{!isTrial && paymentProvider === "cashfree" ? "Required for secure checkout." : "Optional contact number."}</p></Field>
          <div className="sm:col-span-2"><Field label="Password" htmlFor="admin-password" error={errors.admin_password}><Input id="admin-password" type="password" autoComplete="new-password" {...register("admin_password")} aria-invalid={Boolean(errors.admin_password)} /><PasswordStrength password={form.admin_password || ""} compact /></Field></div>
          <div className="sm:col-span-2"><Field label="Confirm password" htmlFor="admin-password-confirm" error={errors.admin_password_confirm}><Input id="admin-password-confirm" type="password" autoComplete="new-password" {...register("admin_password_confirm")} aria-invalid={Boolean(errors.admin_password_confirm)} />{form.admin_password_confirm && !errors.admin_password_confirm && form.admin_password_confirm === form.admin_password && <p className="text-xs text-positive">Passwords match</p>}</Field></div>
        </div>
        <WizardActions back={() => setStep(2)} next={continueOwner} disabled={!ownerValid} />
      </RegistrationPanel>}

      {step === 4 && <RegistrationPanel aside={summary}>
        <StepTitle eyebrow="Review" title="Review before you continue" text={isTrial ? "Confirm the workspace and accept the current policies." : "Confirm the workspace, billing details, and first-term total before payment."} />
        <FormRootError error={errors.root?.server} className="mt-5" />
        <div className="mt-6 divide-y rounded-2xl border">
          <ReviewRow icon={CreditCard} label="Plan" value={`${selectedPlan?.name || "No plan"} / ${isTrial ? "trial" : interval}`} edit={() => setStep(1)} />
          <ReviewRow icon={Buildings} label="Workspace" value={`${form.organization_name || "Unnamed workspace"} / ${form.organization_slug || "No ID"}`} edit={() => setStep(2)} />
          <ReviewRow icon={MapPin} label="Primary location" value={[form.location_name, form.city].filter(Boolean).join(", ") || "Not provided"} edit={() => setStep(2)} />
          <ReviewRow icon={UserCircle} label="Owner" value={`${form.admin_first_name} ${form.admin_last_name}`.trim() || form.admin_email || "Not provided"} edit={() => setStep(3)} />
        </div>
        {!isTrial && <div className="mt-6 max-w-md"><Field label="Billing state" htmlFor="billing-state" error={errors.state}><Input id="billing-state" {...register("state")} placeholder="Tamil Nadu" aria-invalid={Boolean(errors.state)} /><p className="text-xs text-muted-foreground">Used for the GST invoice snapshot.</p></Field></div>}
        <div className="mt-6 rounded-xl border bg-secondary/35 p-4"><label htmlFor="legal-accepted" className="flex cursor-pointer items-start gap-3"><input id="legal-accepted" type="checkbox" className="mt-1 h-4 w-4 rounded border-input accent-[hsl(var(--primary))]" checked={Boolean(form.legal_accepted)} onChange={(event) => setValue("legal_accepted", event.target.checked, { shouldDirty: true, shouldValidate: true })} disabled={!legal.ready || isSubmitting} /><span className="text-sm leading-6">I agree to the <Link to="/terms" target="_blank" className="font-semibold underline underline-offset-4">Terms</Link> and acknowledge the <Link to="/privacy" target="_blank" className="font-semibold underline underline-offset-4">Privacy</Link> and <Link to="/refund-policy" target="_blank" className="font-semibold underline underline-offset-4">Refund Policies</Link>.</span></label><FieldError id="legal-accepted-error" error={errors.legal_accepted} />{legal.status === "loading" && <p className="mt-2 text-xs text-muted-foreground">Loading current policies...</p>}{legal.error && <p className="mt-2 text-xs text-danger">{legal.error}</p>}</div>
        <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row"><Button type="button" variant="outline" disabled={isSubmitting} onClick={() => setStep(3)}><ArrowLeft />Back</Button><Button type="submit" size="lg" className="flex-1" loading={isSubmitting} loadingText={isTrial ? "Creating workspace..." : "Preparing checkout..."} disabled={!registrationValid || !legal.ready || !selectedPlan || (!isTrial && (!selectedQuote || !catalog?.payment_available))}>{isTrial ? "Create trial workspace" : <>Continue to secure payment <ArrowRight /></>}</Button></div>
      </RegistrationPanel>}
    </form>
  </RegistrationShell></FormProvider>;
}

function StepTitle({ eyebrow, title, text }) {
  return <header><div className="overline text-primary">{eyebrow}</div><h1 className="mt-2 font-display text-3xl font-bold tracking-[-0.035em] sm:text-4xl">{title}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">{text}</p></header>;
}

function Field({ label, htmlFor, error, children }) {
  return <div className="space-y-2"><Label htmlFor={htmlFor}>{label}</Label>{children}<FieldError id={`${htmlFor}-error`} error={error} /></div>;
}

function WizardActions({ back, next, disabled }) {
  return <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row"><Button type="button" variant="outline" onClick={back}><ArrowLeft />Back</Button><Button type="button" className="flex-1" disabled={disabled} onClick={next}>Continue <ArrowRight /></Button></div>;
}

function WorkspaceIdField({ register, setValue, state, error }) {
  return <><div className="relative"><Input id="organization-slug" {...register("organization_slug")} onChange={(event) => setValue("organization_slug", businessId(event.target.value), { shouldDirty: true, shouldValidate: Boolean(error) })} aria-invalid={Boolean(error) || ["taken", "invalid", "error"].includes(state.status)} className={state.status === "available" ? "border-emerald-500 pr-10" : ["taken", "invalid", "error"].includes(state.status) ? "border-red-400 pr-10" : "pr-10"} />{state.status === "checking" && <CircleNotch className="absolute right-3 top-2.5 animate-spin text-muted-foreground" />}{state.status === "available" && <CheckCircle weight="fill" className="absolute right-3 top-2.5 text-emerald-600" />}{["taken", "invalid", "error"].includes(state.status) && <XCircle weight="fill" className="absolute right-3 top-2.5 text-red-500" />}</div><div className={`text-xs ${state.status === "available" ? "text-emerald-700" : ["taken", "invalid", "error"].includes(state.status) ? "text-red-600" : "text-muted-foreground"}`}>{state.message}</div>{state.suggestions?.length > 0 && <div className="flex flex-wrap gap-1.5">{state.suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setValue("organization_slug", suggestion, { shouldDirty: true, shouldValidate: true })} className="rounded-full border px-2.5 py-1 text-[11px] hover:border-primary">{suggestion}</button>)}</div>}</>;
}

function PlanChoice({ plan, interval, selected, onSelect }) {
  const quote = interval === "annual" ? plan.annual_quote : plan.monthly_quote;
  const trial = plan.signup_mode === "trial";
  const unavailable = !trial && (!quote || plan.purchasable === false);
  return <button type="button" disabled={unavailable} onClick={onSelect} className={`relative flex min-h-56 flex-col rounded-2xl border p-5 text-left transition-all disabled:cursor-not-allowed disabled:opacity-55 ${selected ? "border-primary bg-primary/[0.045] ring-2 ring-primary/10" : "bg-background hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-lg"}`} aria-pressed={selected}>
    {plan.recommended && <span className="absolute right-4 top-4 rounded-full bg-primary px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-primary-foreground">Recommended</span>}
    <div className="pr-20"><div className="text-lg font-semibold">{plan.name}</div><p className="mt-2 text-xs leading-5 text-muted-foreground">{plan.description || "A focused Edvatiq workspace with the essential operating tools."}</p></div>
    <div className="mt-5 text-2xl font-semibold">{trial ? "Free" : quote ? money(quote.total_paise) : "Unavailable"}</div>
    <div className="mt-1 text-[11px] text-muted-foreground">{trial ? `${plan.trial_days || 30} days` : interval === "annual" ? "Total for one year" : "Total for one month"}{quote?.tax_paise > 0 ? " / GST included" : ""}</div>
    <div className="mt-auto flex items-end justify-between gap-3 pt-6"><span className="text-xs text-muted-foreground">{Number(plan.ai_credits || 0).toLocaleString("en-IN")} AI credits</span><span className={`grid h-7 w-7 place-items-center rounded-full border ${selected ? "border-primary bg-primary text-primary-foreground" : "bg-card"}`}>{selected && <Check size={14} weight="bold" />}</span></div>
  </button>;
}

function ContactPlanChoice({ plan }) {
  return <article className="flex min-h-56 flex-col rounded-2xl border bg-[linear-gradient(145deg,hsl(var(--primary)/0.06),hsl(var(--card)))] p-5"><div className="text-lg font-semibold">{plan.name}</div><p className="mt-2 text-xs leading-5 text-muted-foreground">{plan.description || "Custom limits, rollout support, and commercial terms for larger organizations."}</p><div className="mt-auto pt-6"><div className="text-2xl font-semibold">Custom</div><Link to="/#contact" className="mt-4 inline-flex h-10 items-center gap-2 rounded-xl border bg-card px-4 text-sm font-semibold hover:bg-secondary">Talk to sales <ArrowRight /></Link></div></article>;
}

function ReviewRow({ icon: Icon, label, value, edit }) {
  return <div className="flex items-center gap-3 p-4"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-secondary text-muted-foreground"><Icon /></span><div className="min-w-0 flex-1"><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div><div className="mt-1 truncate text-sm font-medium">{value}</div></div><Button type="button" size="icon" variant="ghost" onClick={edit} aria-label={`Edit ${label}`}><PencilSimple /></Button></div>;
}

function RecoveryPanel({ recovery, checkout, action, retry, continuePayment, cancel, startOver }) {
  const data = recovery.checkout;
  if (recovery.status === "loading") return <RegistrationPanel><div className="space-y-4" aria-busy="true"><Skeleton className="h-5 w-32" /><Skeleton className="h-11 w-3/4" /><Skeleton className="h-20 w-full" /><Skeleton className="h-11 w-full" /></div></RegistrationPanel>;
  if (recovery.status === "error") return <RegistrationPanel><StepTitle eyebrow="Checkout recovery" title="We could not check your payment" text={recovery.error} /><div className="mt-6 flex flex-col gap-3 sm:flex-row"><Button type="button" onClick={retry}>Try again</Button><Button type="button" variant="outline" onClick={() => window.location.assign("/login")}>Sign in instead</Button></div></RegistrationPanel>;
  if (data?.next_action === "restart") return <RegistrationPanel><StepTitle eyebrow="Checkout closed" title="This payment session is no longer active" text="Your non-sensitive details are still available. Start again to create a fresh payment session." /><Button type="button" className="mt-6" onClick={startOver}>Return to registration</Button></RegistrationPanel>;
  if (data?.next_action === "support") return <RegistrationPanel><StepTitle eyebrow="Payment review" title="This checkout needs support review" text="A payment may have reached an inactive checkout. We will not create or charge the workspace again while it is being reviewed." /><div className="mt-6 flex gap-3"><Button asChild><Link to="/#contact">Contact Edvatiq</Link></Button><Button type="button" variant="outline" onClick={retry}>Check again</Button></div></RegistrationPanel>;
  const waiting = data?.next_action === "wait";
  return <RegistrationPanel aside={<CheckoutSummary plan={{ ...(data?.plan || {}), signup_mode: "paid" }} quote={{ subtotal_paise: data?.subtotal_paise, tax_paise: data?.tax_paise, total_paise: data?.amount_paise }} interval={data?.billing_interval} money={money} organizationName={data?.organization_name} />}>
    <StepTitle eyebrow={waiting ? "Payment confirmation" : "Checkout recovery"} title={waiting ? "Your payment is being confirmed" : "Your secure checkout is ready"} text={waiting ? "Open the payment status page to finish account creation when confirmation completes." : `Continue the payment for ${data?.organization_name || checkout?.organization_slug}. Nothing has been charged twice.`} />
    <div className="mt-6 rounded-xl border bg-secondary/40 p-4 text-sm"><div className="font-semibold">Workspace ID reserved</div><div className="mt-1 text-xs text-muted-foreground">Available until {new Date(data?.expires_at || checkout?.expires_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</div></div>
    <div className="mt-6 flex flex-col gap-3 sm:flex-row"><Button type="button" size="lg" className="flex-1" onClick={continuePayment}>{waiting ? "View payment status" : "Continue payment"} <ArrowRight /></Button>{!waiting && <Button type="button" variant="outline" disabled={Boolean(action)} onClick={cancel}>Cancel and edit</Button>}</div>
  </RegistrationPanel>;
}

function PlanSkeleton() {
  return <div className="mt-6"><Skeleton className="h-11 w-56" /><div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[1, 2, 3].map((item) => <Skeleton key={item} className="h-56 rounded-2xl" />)}</div></div>;
}

function LoadError({ message, retry }) {
  return <div className="mt-6 rounded-2xl border bg-secondary/35 p-6 text-center"><p className="font-semibold">{message}</p><Button type="button" variant="outline" className="mt-4" onClick={retry}>Try again</Button></div>;
}
