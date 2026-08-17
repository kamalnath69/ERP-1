import React, { useEffect, useRef, useState } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, ArrowRight, Barbell, Briefcase, Buildings, Check, CheckCircle, CircleNotch,
  Clock, CreditCard, EnvelopeSimple, GraduationCap, Lightning, LockKey, MapPin,
  PencilSimple, Scissors, ShieldCheck, Sparkle, Stethoscope, UserCircle, WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import PasswordStrength from "@/components/PasswordStrength";
import {
  CancelCheckoutDialog, CheckoutSummary, RegistrationPanel, RegistrationShell,
} from "@/components/registration/RegistrationLayout";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { FieldError, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { useRegistrationCheckout } from "@/features/account/useRegistrationCheckout";
import { useSignupEmailVerification } from "@/features/account/useSignupEmailVerification";
import api from "@/lib/api";
import {
  clearSignupCheckout, clearSignupDraft, clearSignupEmailVerification,
  readSignupCheckout, readSignupDraft, readSignupDraftState, readSignupEmailVerification,
  saveSignupDraft, storePendingVerification,
} from "@/lib/signupRegistration";
import {
  applyApiErrors, registrationEmailSchema, registrationOrganizationSchema,
  registrationOwnerProfileSchema, registrationOwnerSchema, registrationPasswordSchema,
  registrationSchema,
} from "@/lib/validation";

const industries = [
  { id: "gym", label: "Gym & fitness", icon: Barbell, tone: "bg-[hsl(var(--chart-1)/0.11)] text-[hsl(var(--chart-1))]", desc: "Memberships, coaching, and daily operations" },
  { id: "salon", label: "Salon & spa", icon: Scissors, tone: "bg-[hsl(var(--chart-4)/0.12)] text-[hsl(var(--chart-4))]", desc: "Bookings, services, and client retention" },
  { id: "clinic", label: "Outpatient clinic", icon: Stethoscope, tone: "bg-[hsl(var(--chart-2)/0.12)] text-[hsl(var(--chart-2))]", desc: "Patient flow, records, lab, and pharmacy" },
  { id: "college", label: "College", icon: GraduationCap, tone: "bg-[hsl(var(--chart-3)/0.12)] text-[hsl(var(--chart-3))]", desc: "Academic evidence, readiness, and placements" },
];

const businessId = (value) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
const money = (paise) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise || 0) / 100);
const blankDefaults = {
  industry: "gym", organization_name: "", organization_slug: "", location_name: "Main Location",
  city: "", state: "", admin_first_name: "", admin_last_name: "", admin_email: "",
  admin_phone: "", admin_password: "", admin_password_confirm: "", plan: "",
  billing_interval: "monthly", legal_accepted: false,
};

const workspaceFields = ["industry", "organization_name", "organization_slug", "location_name", "city"];
const ownerProfileFields = ["admin_first_name", "admin_last_name", "admin_email", "admin_phone"];

function restoredStep(flow, checkout, storedVerification, draftEmail) {
  if (checkout) return 4;
  const requested = [1, 2, 3, 4].includes(Number(flow?.active_step)) ? Number(flow.active_step) : 1;
  if (requested !== 4) return requested;
  const verifiedEmail = storedVerification?.email?.trim().toLowerCase();
  const proofValid = Boolean(
    flow?.review_reached
    && storedVerification?.verification_proof
    && verifiedEmail
    && verifiedEmail === draftEmail?.trim().toLowerCase()
    && Date.parse(storedVerification.proof_expires_at || "") > Date.now(),
  );
  return proofValid ? 4 : 3;
}

export default function Register() {
  const { registerOrg, refreshMe } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialDraftState = useRef(readSignupDraftState()).current;
  const initialDraft = initialDraftState.fields;
  const initialFlow = initialDraftState.flow;
  const initialCheckout = useRef(readSignupCheckout()).current;
  const initialVerification = useRef(readSignupEmailVerification()).current;
  const requestedPlan = searchParams.get("plan") || initialDraft.plan || initialCheckout?.plan_id || "";
  const requestedInterval = searchParams.get("interval") === "annual"
    || initialDraft.billing_interval === "annual"
    || initialCheckout?.billing_interval === "annual"
    ? "annual"
    : "monthly";
  const [step, setStep] = useState(restoredStep(initialFlow, initialCheckout, initialVerification, initialDraft.admin_email));
  const [reviewReached, setReviewReached] = useState(Boolean(initialCheckout || initialFlow.review_reached));
  const [editContext, setEditContext] = useState(initialFlow.edit_target ? {
    target: initialFlow.edit_target,
    snapshot: initialFlow.edit_snapshot || initialDraft,
  } : null);
  const [restoring, setRestoring] = useState(true);
  const [catalogState, setCatalogState] = useState({ status: "loading", data: null, error: "" });
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [legal, setLegal] = useState({ status: "loading", ready: false, documents: {}, error: "" });
  const [interval, setInterval] = useState(requestedInterval);
  const [selectedPlanId, setSelectedPlanId] = useState(requestedPlan);
  const [slugState, setSlugState] = useState({ status: "idle", message: "", suggestions: [] });
  const [cancelOpen, setCancelOpen] = useState(false);
  const [changeEmailOpen, setChangeEmailOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [passwordDraft, setPasswordDraft] = useState({ admin_password: "", admin_password_confirm: "" });
  const [passwordErrors, setPasswordErrors] = useState({});
  const [workspaceState, setWorkspaceState] = useState({ status: "idle", error: "" });
  const checkoutAttempt = useRef(null);
  const workspaceAttempt = useRef(false);
  const ownerEmailRef = useRef(null);

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
  const emailVerification = useSignupEmailVerification();
  const catalog = catalogState.data;
  const selectedPlan = catalog?.plans?.find((plan) => plan.id === selectedPlanId);
  const selectedQuote = interval === "annual" ? selectedPlan?.annual_quote : selectedPlan?.monthly_quote;
  const isTrial = selectedPlan?.signup_mode === "trial";
  const paymentProvider = catalog?.payment?.provider || catalog?.provider || "razorpay";
  const phoneRequired = Boolean(!isTrial && paymentProvider === "cashfree");
  const ownerEmailVerified = emailVerification.isVerified(form.admin_email);
  const ownerEmailValid = registrationEmailSchema.safeParse({ admin_email: form.admin_email }).success;
  const detailsValid = registrationOrganizationSchema.safeParse(form).success && slugState.status === "available";
  const ownerProfileValid = ownerEmailVerified
    && registrationOwnerProfileSchema.safeParse(form).success
    && (!phoneRequired || Boolean(form.admin_phone));
  const ownerValid = ownerEmailVerified
    && registrationOwnerSchema.safeParse(form).success
    && (!phoneRequired || Boolean(form.admin_phone));
  const passwordValid = registrationPasswordSchema.safeParse(form).success;
  const reviewVisibleValid = Boolean(
    selectedPlan
    && detailsValid
    && ownerProfileValid
    && legal.ready
    && form.legal_accepted
    && (isTrial || (form.state?.trim() && selectedQuote && catalog?.payment_available)),
  );

  const finishLegacyRegistration = (result) => {
    const pending = storePendingVerification(result);
    toast.success(result.email_sent === false
      ? "Workspace created. Configure email or resend the code."
      : result.email_sent === true ? "Verification code sent" : "Workspace ready. Continue to email verification.");
    navigate("/verify-email", { state: pending, replace: true });
  };

  const clearRegistrationState = () => {
    clearSignupCheckout();
    clearSignupDraft();
    clearSignupEmailVerification();
  };

  const openWorkspace = async (checkout = null) => {
    if (workspaceAttempt.current) return;
    if (checkout?.next_action === "verify_email") {
      finishLegacyRegistration(checkout);
      return;
    }
    workspaceAttempt.current = true;
    setWorkspaceState({ status: "opening", error: "" });
    try {
      if (checkout?.checkout_id) {
        await api.post(`/auth/registration/checkouts/${checkout.checkout_id}/session`, {}, {
          headers: { "X-Signup-Token": checkout.checkout_token },
        });
      }
      await refreshMe();
      clearRegistrationState();
      navigate("/app", { replace: true });
    } catch (error) {
      setWorkspaceState({
        status: "error",
        error: error?.response?.data?.detail || error?.message || "Your workspace is ready, but the session could not be opened.",
      });
    } finally {
      workspaceAttempt.current = false;
    }
  };

  const resetAfterCancellation = () => {
    checkoutAttempt.current = null;
    setCancelOpen(false);
    reset({
      ...blankDefaults,
      ...readSignupDraft(),
      admin_password: "",
      admin_password_confirm: "",
      legal_accepted: false,
    });
    emailVerification.clear();
    setWorkspaceState({ status: "idle", error: "" });
    setReviewReached(false);
    setEditContext(null);
    setStep(3);
  };

  const payment = useRegistrationCheckout({
    initialCheckout,
    paymentReturnId: searchParams.get("payment_return"),
    preloadProvider: step === 4 && (initialCheckout || (selectedPlan && !isTrial))
      ? (catalog ? paymentProvider : initialCheckout?.provider)
      : null,
    onComplete: (checkout) => { void openWorkspace(checkout); },
    onCancelled: resetAfterCancellation,
    onReturnHandled: () => navigate("/register", { replace: true }),
  });

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
    if (catalogState.status === "loading" || legal.status === "loading") return;
    if (catalog?.plans?.length && !payment.checkout) {
      const requested = catalog.plans.find((plan) => plan.id === selectedPlanId && plan.signup_mode !== "contact" && plan.purchasable !== false);
      if (!requested) {
        const fallback = catalog.trial_enabled
          ? catalog.plans.find((plan) => plan.id === "trial")
          : catalog.plans.find((plan) => plan.recommended && plan.purchasable)
            || catalog.plans.find((plan) => plan.purchasable && plan.signup_mode !== "contact");
        setSelectedPlanId(fallback?.id || "");
        if (step > 1) {
          setReviewReached(false);
          setEditContext(null);
          setStep(1);
          toast.info("Your saved plan is no longer available. Choose another plan to continue.");
        }
      }
    }
    setRestoring(false);
  }, [catalog, catalogState.status, legal.status, payment.checkout, selectedPlanId, step]);

  useEffect(() => {
    setValue("plan", selectedPlanId, { shouldValidate: Boolean(selectedPlanId) });
  }, [selectedPlanId, setValue]);

  useEffect(() => {
    setValue("billing_interval", interval, { shouldValidate: true });
  }, [interval, setValue]);

  useEffect(() => {
    const verifiedEmail = emailVerification.challenge?.email;
    if (verifiedEmail && !form.admin_email) {
      setValue("admin_email", verifiedEmail, { shouldValidate: true });
    }
  }, [emailVerification.challenge?.email, form.admin_email, setValue]);

  useEffect(() => {
    if (restoring) return;
    const frame = window.requestAnimationFrame(() => {
      document.querySelector("[data-registration-step-title]")?.focus({ preventScroll: true });
      const scrollRegion = document.querySelector("[data-registration-scroll-region]");
      if (scrollRegion) scrollRegion.scrollTop = 0;
      if (window.scrollY > 0) window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [restoring, step]);

  useEffect(() => {
    saveSignupDraft(form, {
      active_step: step,
      review_reached: reviewReached,
      edit_target: editContext?.target || null,
      edit_snapshot: editContext?.snapshot || null,
    });
  }, [
    form.industry, form.organization_name, form.organization_slug, form.location_name, form.city,
    form.state, form.admin_first_name, form.admin_last_name, form.admin_email, form.admin_phone,
    form.plan, form.billing_interval, step, reviewReached, editContext,
  ]);

  useEffect(() => {
    if (payment.checkout) return undefined;
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
  }, [form.organization_slug, payment.checkout, clearErrors]);

  const cancelCheckout = async () => {
    try {
      await payment.cancelCheckout();
      toast.success("Checkout cancelled. You can update the registration details.");
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || "Checkout could not be cancelled");
    }
  };

  const reviewSnapshot = () => ({
    ...Object.fromEntries([...workspaceFields, ...ownerProfileFields].map((field) => [field, form[field] ?? ""])),
    plan: selectedPlanId,
    billing_interval: interval,
  });

  const beginReviewEdit = (target) => {
    if (payment.checkout || !reviewReached || ![1, 2, 3].includes(target)) return;
    const snapshot = reviewSnapshot();
    if (target === 3) snapshot.email_verification = emailVerification.challenge;
    setEditContext({ target, snapshot });
    setStep(target);
  };

  const finishReviewEdit = () => {
    setEditContext(null);
    setReviewReached(true);
    setStep(4);
  };

  const cancelReviewEdit = () => {
    if (!editContext) return;
    const { target, snapshot } = editContext;
    if (target === 1) {
      setSelectedPlanId(snapshot.plan || "");
      setInterval(snapshot.billing_interval === "annual" ? "annual" : "monthly");
    }
    const fields = target === 2 ? workspaceFields : target === 3 ? ownerProfileFields : [];
    fields.forEach((field) => setValue(field, snapshot[field] ?? "", { shouldDirty: true, shouldValidate: true }));
    if (target === 3) {
      if (snapshot.email_verification) emailVerification.restore(snapshot.email_verification);
      else emailVerification.clear();
    }
    setEditContext(null);
    setStep(4);
  };

  const selectJourneyStep = (target) => {
    if (payment.checkout || editContext) return;
    if (reviewReached) beginReviewEdit(target);
    else setStep(target);
  };

  const continuePlan = () => {
    if (!selectedPlan || selectedPlan.signup_mode === "contact" || selectedPlan.purchasable === false) return;
    if (editContext?.target === 1) finishReviewEdit();
    else setStep(2);
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
    if (editContext?.target === 2) finishReviewEdit();
    else setStep(3);
  };

  const sendOwnerCode = async () => {
    clearErrors("root.server");
    const valid = await trigger("admin_email", { shouldFocus: true });
    if (!valid || !registrationEmailSchema.safeParse({ admin_email: form.admin_email }).success) return;
    try {
      await emailVerification.send(form.admin_email);
      toast.success("Verification code sent");
    } catch {
      // The inline challenge state carries the actionable error.
    }
  };

  const verifyOwnerCode = async () => {
    try {
      const result = await emailVerification.verify();
      if (result) toast.success("Work email verified");
    } catch {
      // The code field remains available for correction.
    }
  };

  const changeOwnerEmail = () => {
    emailVerification.clear();
    setChangeEmailOpen(false);
    window.requestAnimationFrame(() => ownerEmailRef.current?.focus());
  };

  const requestOwnerEmailChange = () => {
    if (ownerEmailVerified) setChangeEmailOpen(true);
    else changeOwnerEmail();
  };

  const continueOwner = async () => {
    clearErrors("root.server");
    if (!ownerEmailVerified) {
      await sendOwnerCode();
      return;
    }
    const passwordRequiredHere = !editContext || !reviewReached || Boolean(form.admin_password || form.admin_password_confirm);
    const valid = await trigger([
      "admin_first_name", "admin_last_name", "admin_email",
      ...(phoneRequired ? ["admin_phone"] : []),
      ...(passwordRequiredHere ? ["admin_password", "admin_password_confirm"] : []),
    ], { shouldFocus: true });
    if (valid && phoneRequired && !form.admin_phone) {
      setError("admin_phone", { type: "required", message: "Phone number is required for Cashfree checkout" }, { shouldFocus: true });
      return;
    }
    if (valid) {
      setReviewReached(true);
      if (editContext?.target === 3) finishReviewEdit();
      else setStep(4);
    }
  };

  const submit = async (values) => {
    if (step !== 4 || !selectedPlan) return;
    clearErrors("root.server");
    if (!legal.ready) {
      setError("root.server", { type: "legal", message: "Registration is temporarily unavailable until the current legal documents are published." });
      return;
    }
    if (!emailVerification.proofPayload || !ownerEmailVerified) {
      setStep(3);
      toast.info("Verify the owner email before continuing.");
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
        admin_phone: phoneRequired ? registration.admin_phone : null,
        email_verification: emailVerification.proofPayload,
        legal_acceptance: {
          accepted,
          terms_document_id: legal.documents.terms.id,
          privacy_document_id: legal.documents.privacy.id,
          refund_document_id: legal.documents.refund.id,
        },
      };
      if (isTrial) {
        await registerOrg(payload);
        await openWorkspace();
        return;
      }
      if (!catalog.payment_available) throw new Error("Secure checkout is temporarily unavailable");
      const signature = JSON.stringify([
        values.organization_slug, values.admin_email, selectedPlan.id, interval, values.state,
        emailVerification.proofPayload.challenge_id,
      ]);
      if (!checkoutAttempt.current || checkoutAttempt.current.signature !== signature) {
        checkoutAttempt.current = {
          signature,
          key: crypto.randomUUID(),
          token: `${crypto.randomUUID()}${crypto.randomUUID()}`,
        };
      }
      const session = await payment.createCheckout(async () => {
        const { data: checkout } = await api.post("/auth/registration/checkout", {
          ...payload,
          plan: selectedPlan.id,
          billing_interval: interval,
          idempotency_key: checkoutAttempt.current.key,
          checkout_token: checkoutAttempt.current.token,
        });
        return {
          ...checkout,
          checkout_token: checkout.checkout_token,
          plan_id: selectedPlan.id,
          billing_interval: interval,
        };
      });
      clearSignupEmailVerification();
      payment.openCheckout(session);
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
      if (detail.includes("phone number is required") && detail.includes("Cashfree")) {
        setCatalogAttempt((value) => value + 1);
        setStep(3);
        setError("admin_phone", { type: "server", message: detail });
        toast.info("The payment provider changed. Add the phone required for checkout.");
        return;
      }
      if (detail.includes("Verify the owner email again")) {
        emailVerification.clear();
        setStep(3);
        toast.info("Email verification expired or was already used. Verify it again to continue.");
        return;
      }
      if (detail.includes("slug") || detail.includes("Business ID")) {
        setStep(2);
        setSlugState({ status: "taken", message: detail, suggestions: [] });
        setError("organization_slug", { type: "server", message: detail });
      } else toast.error(detail);
    }
  };

  const requestFinalSubmit = async () => {
    const visibleFields = [
      ...workspaceFields,
      ...ownerProfileFields,
      "plan", "billing_interval", "legal_accepted",
      ...(!isTrial ? ["state"] : []),
    ];
    const valid = await trigger(visibleFields, { shouldFocus: true });
    if (!valid || !reviewVisibleValid) return;
    if (!passwordValid) {
      setPasswordErrors({});
      setPasswordDraft({ admin_password: "", admin_password_confirm: "" });
      setPasswordOpen(true);
      return;
    }
    void handleSubmit(submit)();
  };

  const confirmRestoredPassword = () => {
    const result = registrationPasswordSchema.safeParse(passwordDraft);
    if (!result.success) {
      const nextErrors = {};
      result.error.issues.forEach((issue) => {
        const field = issue.path[0];
        if (field && !nextErrors[field]) nextErrors[field] = issue.message;
      });
      setPasswordErrors(nextErrors);
      return;
    }
    setValue("admin_password", result.data.admin_password, { shouldDirty: true, shouldValidate: true });
    setValue("admin_password_confirm", result.data.admin_password_confirm, { shouldDirty: true, shouldValidate: true });
    setPasswordOpen(false);
    setPasswordErrors({});
    setPasswordDraft({ admin_password: "", admin_password_confirm: "" });
    window.setTimeout(() => { void handleSubmit(submit)(); }, 0);
  };

  const checkoutPlan = payment.checkout?.plan
    ? { ...payment.checkout.plan, signup_mode: "paid" }
    : selectedPlan;
  const checkoutQuote = payment.checkout
    ? {
      subtotal_paise: payment.checkout.subtotal_paise,
      tax_paise: payment.checkout.tax_paise,
      total_paise: payment.checkout.amount_paise,
    }
    : selectedQuote;
  const summary = <CheckoutSummary
    plan={checkoutPlan}
    quote={checkoutQuote}
    interval={payment.checkout?.billing_interval || interval}
    money={money}
    organizationName={payment.checkout?.organization_name || form.organization_name}
    showWorkspace={step !== 4}
  />;
  const completedSteps = [
    ...(selectedPlan ? [1] : []),
    ...(payment.checkout || detailsValid ? [2] : []),
    ...(ownerProfileValid ? [3] : []),
  ];
  const journeySummaries = {
    1: selectedPlan ? `${selectedPlan.name} / ${isTrial ? "trial" : interval}` : "Choose access",
    2: form.organization_name || "Organization details",
    3: ownerEmailVerified ? form.admin_email : "Secure the owner",
    4: reviewReached ? "Ready for confirmation" : "Confirm and pay",
  };
  const adminEmailField = register("admin_email", {
    onChange: (event) => emailVerification.invalidateIfDifferent(event.target.value),
  });

  if (restoring) return <RegistrationShell currentStep={step} completedSteps={completedSteps} summaries={journeySummaries}>
    <RegistrationRestoreSkeleton />
  </RegistrationShell>;

  return <FormProvider {...methods}><RegistrationShell
    currentStep={step}
    completedSteps={completedSteps}
    summaries={journeySummaries}
    editingStep={editContext?.target || null}
    onStepSelect={selectJourneyStep}
  >
    <form onSubmit={handleSubmit(submit)} noValidate className="min-h-0 md:h-full">
      {step === 1 && <RegistrationPanel wide footer={<WizardActions
        back={editContext?.target === 1 ? cancelReviewEdit : null}
        backLabel="Cancel"
        next={continuePlan}
        nextLabel={editContext?.target === 1 ? "Save and return to Review" : "Continue to workspace"}
        disabled={!selectedPlan || selectedPlan.signup_mode === "contact" || selectedPlan.purchasable === false}
      />}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <StepTitle icon={CreditCard} eyebrow={editContext?.target === 1 ? "Editing from Review" : "Plan"} title="Choose your plan" text="Select the access and billing period that fits your workspace." />
          {catalog && <IntervalToggle interval={interval} onChange={setInterval} />}
        </div>
        <FormRootError error={errors.root?.server} className="mt-5" />
        {catalogState.status === "loading" && <PlanSkeleton />}
        {catalogState.status === "error" && <LoadError message={catalogState.error} retry={() => setCatalogAttempt((value) => value + 1)} />}
        {catalog && <>
          <div className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(min(100%,13rem),1fr))] gap-3">{catalog.plans
            .filter((plan) => plan.signup_mode !== "contact")
            .map((plan) => <PlanChoice key={plan.id} plan={plan} interval={interval} selected={selectedPlanId === plan.id} onSelect={() => setSelectedPlanId(plan.id)} />)}</div>
          {catalog.plans.some((plan) => plan.signup_mode === "contact") && <div className="mt-4 border-t pt-4">{catalog.plans
            .filter((plan) => plan.signup_mode === "contact")
            .map((plan) => <ContactPlanChoice key={plan.id} plan={plan} />)}</div>}
        </>}
      </RegistrationPanel>}

      {step === 2 && <RegistrationPanel aside={summary} footer={<WizardActions
        back={editContext?.target === 2 ? cancelReviewEdit : () => setStep(1)}
        backLabel={editContext?.target === 2 ? "Cancel" : "Back"}
        next={continueWorkspace}
        nextLabel={editContext?.target === 2 ? "Save and return to Review" : "Continue"}
        disabled={!detailsValid}
      />}>
        <StepTitle icon={Buildings} eyebrow={editContext?.target === 2 ? "Editing from Review" : "Workspace"} title="Set up your organization" text="Add the identity and primary location your team will recognize." />
        <FormRootError error={errors.root?.server} className="mt-5" />
        <FormSection title="Workspace type" text="Controls the terminology and operating modules available after setup.">
          <div className="grid gap-2 sm:grid-cols-2">{industries.map((item) => {
            const active = form.industry === item.id;
            return <button type="button" key={item.id} onClick={() => setValue("industry", item.id, { shouldDirty: true, shouldValidate: true })} className={`relative overflow-hidden rounded-xl border p-3 text-left transition-[border-color,background-color,box-shadow,transform] hover:-translate-y-0.5 ${active ? "border-primary/35 bg-[linear-gradient(110deg,hsl(var(--primary)/0.075),hsl(var(--card)),hsl(var(--accent)/0.035))] text-foreground shadow-sm" : "bg-background hover:border-primary/25 hover:shadow-sm"}`} aria-pressed={active}>
              {active && <span className="absolute inset-y-0 left-0 w-1 bg-accent" />}
              <div className="flex items-center gap-3"><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${active ? "bg-primary text-accent" : item.tone}`}><item.icon size={18} weight="duotone" /></span><span className="min-w-0"><span className="block text-sm font-semibold">{item.label}</span><span className="block truncate text-[10px] text-muted-foreground">{item.desc}</span></span>{active && <CheckCircle className="ml-auto shrink-0 text-primary" size={17} weight="fill" />}</div>
            </button>;
          })}</div>
        </FormSection>
        <FormSection title="Organization and location" text="Use a stable Workspace ID; your team will use it when needed.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Organization name" htmlFor="organization-name" error={errors.organization_name}><Input id="organization-name" {...register("organization_name", { onChange: (event) => { if (!form.organization_slug) setValue("organization_slug", businessId(event.target.value), { shouldDirty: true }); } })} aria-invalid={Boolean(errors.organization_name)} /></Field>
          <Field label="Workspace ID" htmlFor="organization-slug" error={errors.organization_slug}><WorkspaceIdField register={register} setValue={setValue} state={slugState} error={errors.organization_slug} /></Field>
          <Field label="Primary location" htmlFor="location-name" error={errors.location_name}><Input id="location-name" {...register("location_name")} aria-invalid={Boolean(errors.location_name)} /></Field>
          <Field label="City" htmlFor="city" error={errors.city}><Input id="city" {...register("city")} aria-invalid={Boolean(errors.city)} /></Field>
        </div>
        </FormSection>
      </RegistrationPanel>}

      {step === 3 && <RegistrationPanel aside={summary} footer={<OwnerActions
        back={editContext?.target === 3 ? cancelReviewEdit : () => setStep(2)}
        backLabel={editContext?.target === 3 ? "Cancel" : "Back"}
        verified={ownerEmailVerified}
        ownerValid={editContext?.target === 3 ? ownerProfileValid : ownerValid}
        editMode={editContext?.target === 3}
        onContinue={continueOwner}
      />}>
        <StepTitle icon={UserCircle} eyebrow={editContext?.target === 3 ? "Editing from Review" : "Owner"} title="Set up the workspace owner" text="Verify the email, then finish the account details." />
        <FormRootError error={errors.root?.server} className="mt-5" />
        <div className="mt-5 max-w-3xl">
          <EmailVerificationCard
            emailField={adminEmailField}
            emailRef={ownerEmailRef}
            error={errors.admin_email}
            verification={emailVerification}
            verified={ownerEmailVerified}
            emailValid={ownerEmailValid}
            onSend={sendOwnerCode}
            onVerify={verifyOwnerCode}
            onChangeEmail={requestOwnerEmailChange}
          />
          {ownerEmailVerified && <div className="animate-in fade-in-0 slide-in-from-bottom-1 duration-200">
            <FormSection title="Owner profile" text="Used for account ownership and workspace administration.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="First name" htmlFor="admin-first-name" error={errors.admin_first_name}><Input id="admin-first-name" {...register("admin_first_name")} autoComplete="given-name" aria-invalid={Boolean(errors.admin_first_name)} /></Field>
              <Field label="Last name" htmlFor="admin-last-name" error={errors.admin_last_name}><Input id="admin-last-name" {...register("admin_last_name")} autoComplete="family-name" aria-invalid={Boolean(errors.admin_last_name)} /></Field>
              {phoneRequired && <div className="sm:col-span-2"><Field label="Phone" htmlFor="admin-phone" error={errors.admin_phone}><Input id="admin-phone" type="tel" autoComplete="tel" {...register("admin_phone")} aria-invalid={Boolean(errors.admin_phone)} /><p className="text-xs text-muted-foreground">Required by Cashfree for this payment. You can update it later in My Profile.</p></Field></div>}
            </div>
            </FormSection>
            {editContext?.target === 3 && reviewReached
              ? <div className="mt-5 flex items-start gap-3 rounded-xl border bg-secondary/30 px-4 py-3 text-sm"><LockKey className="mt-0.5 shrink-0 text-muted-foreground" /><div><div className="font-semibold">Account security remains unchanged</div><p className="mt-0.5 text-xs text-muted-foreground">If the page was refreshed, your password will be requested securely from Review.</p></div></div>
              : <FormSection title="Account security" text="Use a strong password reserved for this account.">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Password" htmlFor="admin-password" error={errors.admin_password}><Input id="admin-password" type="password" autoComplete="new-password" {...register("admin_password")} aria-invalid={Boolean(errors.admin_password)} /><PasswordStrength password={form.admin_password || ""} compact /></Field>
                  <Field label="Confirm password" htmlFor="admin-password-confirm" error={errors.admin_password_confirm}><Input id="admin-password-confirm" type="password" autoComplete="new-password" {...register("admin_password_confirm")} aria-invalid={Boolean(errors.admin_password_confirm)} />{form.admin_password_confirm && !errors.admin_password_confirm && form.admin_password_confirm === form.admin_password && <p className="text-xs text-positive">Passwords match</p>}</Field>
                </div>
              </FormSection>}
          </div>}
        </div>
      </RegistrationPanel>}

      {step === 4 && <RegistrationPanel aside={summary} footer={<ReviewPaymentActions
        payment={payment}
        workspaceState={workspaceState}
        trial={Boolean(isTrial && !payment.checkout)}
        amountPaise={payment.checkout?.amount_paise || selectedQuote?.total_paise}
        submitting={isSubmitting}
        canSubmit={reviewVisibleValid}
        paymentUnavailable={Boolean(!isTrial && selectedQuote && catalogState.status === "ready" && !catalog?.payment_available)}
        paymentAvailabilityLoading={catalogState.status === "loading"}
        onSubmit={() => { void requestFinalSubmit(); }}
        onBack={() => beginReviewEdit(3)}
        onCancel={() => setCancelOpen(true)}
        onRestart={() => { void cancelCheckout(); }}
        onRetryPaymentAvailability={() => setCatalogAttempt((attempt) => attempt + 1)}
        onOpenWorkspace={() => { void openWorkspace(payment.checkout); }}
      />}>
        <StepTitle icon={CheckCircle} eyebrow="Review" title="Confirm and continue" text="Check the essentials once, then continue securely." />
        <FormRootError error={errors.root?.server} className="mt-5" />
        <div className="mt-5 divide-y overflow-hidden rounded-2xl border border-primary/10 bg-card shadow-[0_10px_30px_hsl(var(--shadow-color)/0.035)]">
          <ReviewRow icon={CreditCard} label="Plan" value={`${checkoutPlan?.name || "No plan"} / ${isTrial && !payment.checkout ? "trial" : payment.checkout?.billing_interval || interval}`} status={Boolean(checkoutPlan)} edit={!payment.checkout ? () => beginReviewEdit(1) : null} />
          <ReviewRow icon={Buildings} label="Workspace" value={`${payment.checkout?.organization_name || form.organization_name || "Unnamed workspace"} / ${payment.checkout?.organization_slug || form.organization_slug || "No ID"}`} status={Boolean(payment.checkout || detailsValid)} edit={!payment.checkout ? () => beginReviewEdit(2) : null} />
          <ReviewRow icon={UserCircle} label="Owner" value={form.admin_email || "Saved with this checkout"} status={ownerProfileValid || Boolean(payment.checkout)} edit={!payment.checkout ? () => beginReviewEdit(3) : null} />
          <ReviewRow icon={MapPin} label="Billing state" value={payment.checkout?.billing_state || form.state || (isTrial ? "Not required for trial" : "Required for GST invoice")} status={Boolean(payment.checkout || isTrial || form.state?.trim())} />
        </div>
        {!payment.checkout && !isTrial && <div className="mt-5 max-w-md"><Field label="Billing state" htmlFor="billing-state" error={errors.state}><Input id="billing-state" {...register("state")} placeholder="Tamil Nadu" aria-invalid={Boolean(errors.state)} /><p className="text-xs text-muted-foreground">Used for the GST invoice.</p></Field></div>}
        {payment.checkout
          ? <div className="mt-5 flex items-start gap-3 rounded-xl border bg-secondary/30 px-4 py-3 text-sm"><CheckCircle className="mt-0.5 shrink-0 text-positive" weight="fill" /><span>The current policies were accepted when this checkout was created.</span></div>
          : <div className="mt-5 rounded-xl border border-primary/10 bg-[linear-gradient(100deg,hsl(var(--primary)/0.045),hsl(var(--accent)/0.04))] px-4 py-3"><label htmlFor="legal-accepted" className="flex cursor-pointer items-start gap-3"><input id="legal-accepted" type="checkbox" className="mt-1 h-4 w-4 rounded border-input accent-[hsl(var(--primary))]" checked={Boolean(form.legal_accepted)} onChange={(event) => setValue("legal_accepted", event.target.checked, { shouldDirty: true, shouldValidate: true })} disabled={!legal.ready || isSubmitting} /><span className="text-sm leading-6">I agree to the <Link to="/terms" target="_blank" className="font-semibold underline decoration-accent/50 underline-offset-4">Terms</Link> and acknowledge the <Link to="/privacy" target="_blank" className="font-semibold underline decoration-accent/50 underline-offset-4">Privacy</Link> and <Link to="/refund-policy" target="_blank" className="font-semibold underline decoration-accent/50 underline-offset-4">Refund Policies</Link>.</span></label><FieldError id="legal-accepted-error" error={errors.legal_accepted} />{legal.status === "loading" && <p className="mt-2 text-xs text-muted-foreground">Loading current policies...</p>}{legal.error && <p className="mt-2 text-xs text-danger">{legal.error}</p>}</div>}
        {!payment.checkout && !ownerProfileValid && <div className="mt-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"><WarningCircle className="mt-0.5 shrink-0" /><div><div className="font-semibold">Owner details need attention</div><button type="button" className="mt-1 text-xs font-semibold underline underline-offset-4" onClick={() => beginReviewEdit(3)}>Complete owner details</button></div></div>}
      </RegistrationPanel>}
    </form>
    <CancelCheckoutDialog
      open={cancelOpen}
      onOpenChange={setCancelOpen}
      loading={payment.phase === "cancelling"}
      onConfirm={() => { void cancelCheckout(); }}
    />
    <ConfirmEmailChangeDialog open={changeEmailOpen} onOpenChange={setChangeEmailOpen} onConfirm={changeOwnerEmail} />
    <RestoredPasswordDialog
      open={passwordOpen}
      onOpenChange={setPasswordOpen}
      values={passwordDraft}
      errors={passwordErrors}
      loading={isSubmitting || payment.phase === "creating"}
      onChange={(field, value) => {
        setPasswordDraft((current) => ({ ...current, [field]: value }));
        setPasswordErrors((current) => ({ ...current, [field]: "" }));
      }}
      onConfirm={confirmRestoredPassword}
    />
  </RegistrationShell></FormProvider>;
}

function StepTitle({ icon: Icon = Sparkle, eyebrow, title, text }) {
  return <header className="flex items-start gap-3.5">
    <span className="relative mt-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-[0_10px_24px_hsl(var(--primary)/0.16)]"><Icon size={21} weight="duotone" /><i className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-card bg-accent" /></span>
    <div className="min-w-0"><div className="overline flex items-center gap-2 text-primary"><span className="h-px w-5 bg-accent" />{eyebrow}</div><h1 data-registration-step-title tabIndex={-1} className="mt-1 font-marketing text-3xl font-semibold leading-none tracking-[-0.035em] outline-none sm:text-[2rem]">{title}</h1><p className="mt-2 max-w-2xl text-sm leading-5 text-muted-foreground">{text}</p></div>
  </header>;
}

function Field({ label, htmlFor, error, children }) {
  return <div className="space-y-2"><Label htmlFor={htmlFor}>{label}</Label>{children}<FieldError id={`${htmlFor}-error`} error={error} /></div>;
}

function FormSection({ title, text, children }) {
  return <section className="mt-5 border-t pt-5"><div className="mb-3 flex items-start gap-2.5"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" /><div><h2 className="text-base font-semibold leading-5">{title}</h2>{text && <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">{text}</p>}</div></div>{children}</section>;
}

function IntervalToggle({ interval, onChange }) {
  return <div className="inline-flex w-full shrink-0 rounded-xl border border-primary/10 bg-secondary/45 p-1 sm:w-auto" aria-label="Billing interval">{[["monthly", "Monthly"], ["annual", "Annual"]].map(([value, label]) => <button type="button" key={value} onClick={() => onChange(value)} className={`flex-1 rounded-lg px-4 py-2 text-xs font-semibold transition-colors sm:flex-none ${interval === value ? "bg-primary text-primary-foreground shadow-[0_6px_16px_hsl(var(--primary)/0.16)]" : "text-muted-foreground hover:text-foreground"}`} aria-pressed={interval === value}>{label}</button>)}</div>;
}

function WizardActions({ back, backLabel = "Back", next, nextLabel = "Continue", disabled }) {
  return <div className={`flex flex-col-reverse gap-3 sm:flex-row ${back ? "" : "sm:justify-end"}`}>
    {back && <Button type="button" variant="outline" onClick={back}>{backLabel === "Back" && <ArrowLeft />}{backLabel}</Button>}
    <Button type="button" className={back ? "flex-1" : "w-full sm:w-auto sm:min-w-56"} disabled={disabled} onClick={next}>{nextLabel} <ArrowRight /></Button>
  </div>;
}

function OwnerActions({ back, backLabel, verified, ownerValid, editMode, onContinue }) {
  return <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center">
    <Button type="button" variant="outline" onClick={back}>{backLabel === "Back" && <ArrowLeft />}{backLabel}</Button>
    {verified
      ? <Button type="button" className="flex-1" disabled={!ownerValid} onClick={onContinue}>{editMode ? "Save and return to Review" : "Continue"} <ArrowRight /></Button>
      : <div className="flex-1 text-center text-xs text-muted-foreground sm:text-right">Verify the work email to continue.</div>}
  </div>;
}

function EmailVerificationCard({
  emailField, emailRef, error, verification, verified, emailValid,
  onSend, onVerify, onChangeEmail,
}) {
  const sending = verification.status === "sending";
  const verifying = verification.status === "verifying";
  const codeExpired = Boolean(verification.challenge && verification.expiresSeconds <= 0);
  const digits = verification.code.padEnd(6, " ").slice(0, 6).split("");

  if (verified) return <section className="relative flex items-center gap-3 overflow-hidden rounded-2xl border border-primary/20 bg-[linear-gradient(110deg,hsl(var(--primary)/0.08),hsl(var(--card))_68%,hsl(var(--accent)/0.04))] p-4 text-foreground shadow-sm">
    <span className="relative grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-accent"><ShieldCheck size={20} weight="fill" /></span>
    <div className="relative min-w-0 flex-1"><div className="text-[10px] font-bold uppercase tracking-wider text-primary">Verified work email</div><div className="mt-0.5 truncate text-sm font-semibold">{verification.challenge?.email}</div></div>
    <Button type="button" size="sm" variant="ghost" className="relative text-muted-foreground hover:bg-primary/8 hover:text-primary" onClick={onChangeEmail}>Change</Button>
  </section>;

  return <section className="relative overflow-hidden rounded-2xl border border-primary/10 bg-[linear-gradient(120deg,hsl(var(--primary)/0.035),hsl(var(--card))_48%,hsl(var(--accent)/0.035))] shadow-[0_10px_30px_hsl(var(--shadow-color)/0.035)]">
    <div className="absolute inset-y-0 left-0 w-1 bg-[linear-gradient(to_bottom,hsl(var(--primary)),hsl(var(--accent)))]" />
    <div className="p-4 pl-5 sm:p-5 sm:pl-6">
      <div className="flex items-center gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-accent shadow-sm"><EnvelopeSimple size={19} weight="duotone" /></span><div><h2 className="text-base font-semibold">Verify the owner email</h2><p className="mt-0.5 text-[11px] text-muted-foreground">We will send a six-digit code to this address.</p></div></div>
      {!verification.challenge
        ? <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1"><Label htmlFor="admin-email" className="sr-only">Work email</Label><Input id="admin-email" type="email" autoComplete="email" {...emailField} ref={(node) => { emailField.ref(node); emailRef.current = node; }} aria-invalid={Boolean(error)} placeholder="name@organization.com" /><FieldError id="admin-email-error" error={error} /></div>
          <Button type="button" className="sm:min-w-32" loading={sending} loadingText="Sending..." disabled={!emailValid} onClick={() => { void onSend(); }}>Send code</Button>
        </div>
        : <div className="mt-4 border-t pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="text-xs text-muted-foreground">Code sent to <span className="font-semibold text-foreground">{verification.challenge.email}</span></div><button type="button" className="text-xs font-semibold text-primary hover:underline" onClick={onChangeEmail}>Change email</button></div>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="group relative w-full max-w-[17rem]">
              <div className="grid grid-cols-6 gap-1.5" aria-hidden="true">{digits.map((digit, index) => <span key={index} className="grid h-11 place-items-center rounded-lg border bg-card font-mono text-base font-semibold shadow-sm group-focus-within:border-accent group-focus-within:ring-2 group-focus-within:ring-accent/15">{digit.trim()}</span>)}</div>
              <input id="owner-email-code" value={verification.code} onChange={(event) => verification.setCode(event.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={6} aria-label="Six-digit code" className="absolute inset-0 h-full w-full cursor-text opacity-0" autoFocus />
            </div>
            <Button type="button" className="sm:min-w-32" loading={verifying} loadingText="Verifying..." disabled={verification.code.length !== 6 || codeExpired || sending} onClick={() => { void onVerify(); }}>Verify email</Button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-muted-foreground">
            <span>{verification.expiresSeconds > 0 ? `Expires in ${Math.ceil(verification.expiresSeconds / 60)} min` : "Code expired"}</span>
            <button type="button" className="font-semibold text-foreground disabled:cursor-not-allowed disabled:opacity-50" disabled={verification.resendSeconds > 0 || sending || verifying} onClick={() => { void onSend(); }}>{verification.resendSeconds > 0 ? `Resend in ${verification.resendSeconds}s` : "Resend code"}</button>
            {verification.testCode && <span className="rounded-md bg-warning/10 px-2 py-1 font-mono text-warning">Test code: {verification.testCode}</span>}
          </div>
        </div>}
      {verification.error && <div className="mt-3 text-xs font-medium text-danger" role="alert">{verification.error}</div>}
    </div>
  </section>;
}

function WorkspaceIdField({ register, setValue, state, error }) {
  return <><div className="relative"><Input id="organization-slug" {...register("organization_slug")} onChange={(event) => setValue("organization_slug", businessId(event.target.value), { shouldDirty: true, shouldValidate: Boolean(error) })} aria-invalid={Boolean(error) || ["taken", "invalid", "error"].includes(state.status)} className={state.status === "available" ? "border-emerald-500 pr-10" : ["taken", "invalid", "error"].includes(state.status) ? "border-red-400 pr-10" : "pr-10"} />{state.status === "checking" && <CircleNotch className="absolute right-3 top-2.5 animate-spin text-muted-foreground" />}{state.status === "available" && <CheckCircle weight="fill" className="absolute right-3 top-2.5 text-emerald-600" />}{["taken", "invalid", "error"].includes(state.status) && <XCircle weight="fill" className="absolute right-3 top-2.5 text-red-500" />}</div><div className={`text-xs ${state.status === "available" ? "text-emerald-700" : ["taken", "invalid", "error"].includes(state.status) ? "text-red-600" : "text-muted-foreground"}`}>{state.message}</div>{state.suggestions?.length > 0 && <div className="flex flex-wrap gap-1.5">{state.suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setValue("organization_slug", suggestion, { shouldDirty: true, shouldValidate: true })} className="rounded-full border px-2.5 py-1 text-[11px] hover:border-primary">{suggestion}</button>)}</div>}</>;
}

function PlanChoice({ plan, interval, selected, onSelect }) {
  const quote = interval === "annual" ? plan.annual_quote : plan.monthly_quote;
  const trial = plan.signup_mode === "trial";
  const unavailable = !trial && (!quote || plan.purchasable === false);
  const PlanIcon = trial ? Lightning : plan.recommended ? Sparkle : CreditCard;
  return <button type="button" disabled={unavailable} onClick={onSelect} className={`group relative flex min-h-36 flex-col overflow-hidden rounded-2xl border p-4 text-left transition-[transform,border-color,background-color,box-shadow] disabled:cursor-not-allowed disabled:opacity-55 ${selected ? "border-primary/45 bg-[linear-gradient(145deg,hsl(var(--primary)/0.075),hsl(var(--card))_58%,hsl(var(--accent)/0.035))] text-foreground shadow-[0_12px_28px_hsl(var(--shadow-color)/0.08)] ring-1 ring-primary/8" : "bg-background hover:-translate-y-0.5 hover:border-primary/25 hover:shadow-md"}`} aria-pressed={selected}>
    {plan.recommended && <span className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,hsl(var(--primary)),hsl(var(--accent)))]" />}
    <div className="flex items-start justify-between gap-3"><div className="flex items-center gap-2.5"><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${selected ? "bg-primary text-accent" : "bg-primary/8 text-primary"}`}><PlanIcon size={18} weight={plan.recommended ? "fill" : "duotone"} /></span><div className="text-base font-semibold">{plan.name}</div></div><span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full border ${selected ? "border-primary bg-primary text-primary-foreground" : "bg-card text-transparent"}`}><Check size={14} weight="bold" /></span></div>
    <div className="mt-3 font-marketing text-2xl font-semibold leading-none">{trial ? "Free" : quote ? money(quote.total_paise) : "Unavailable"}</div>
    <div className="mt-1 text-[11px] text-muted-foreground">{trial ? `${plan.trial_days || 30} days` : interval === "annual" ? "One year, GST included" : "One month, GST included"}</div>
    <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-3"><span className="text-[11px] text-muted-foreground">{Number(plan.ai_credits || 0).toLocaleString("en-IN")} AI credits</span>{plan.recommended && <span className="rounded-full bg-accent/10 px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-accent">Recommended</span>}</div>
  </button>;
}

function ContactPlanChoice({ plan }) {
  return <article className="relative flex flex-col gap-4 overflow-hidden rounded-2xl border border-primary/15 bg-[linear-gradient(120deg,hsl(var(--primary)/0.07),hsl(var(--card))_58%,hsl(var(--accent)/0.055))] p-4 sm:flex-row sm:items-center sm:justify-between"><span className="absolute inset-y-0 left-0 w-1 bg-accent" /><div className="flex min-w-0 items-center gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-accent"><Briefcase size={19} weight="duotone" /></span><div className="min-w-0"><div className="text-sm font-semibold">{plan.name} <span className="ml-1 text-muted-foreground">/ Custom</span></div><p className="mt-1 text-xs leading-5 text-muted-foreground">{plan.description || "Custom limits and rollout support for larger organizations."}</p></div></div><Button asChild variant="outline" className="shrink-0 border-primary/20 bg-card"><Link to="/#contact">Talk to sales <ArrowRight /></Link></Button></article>;
}

function ReviewRow({ icon: Icon, label, value, status = true, edit }) {
  return <div className="flex items-center gap-3 px-4 py-3.5 transition-colors hover:bg-secondary/25"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/8 text-primary"><Icon weight="duotone" /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div><span className={`inline-flex items-center gap-1 text-[10px] font-semibold ${status ? "text-positive" : "text-amber-700"}`}>{status ? <CheckCircle size={12} weight="fill" /> : <WarningCircle size={12} weight="fill" />}{status ? "Ready" : "Needs attention"}</span></div><div className="mt-0.5 truncate text-sm font-medium">{value}</div></div>{edit && <Button type="button" size="icon" variant="ghost" className="text-muted-foreground hover:bg-primary/8 hover:text-primary" onClick={edit} aria-label={`Edit ${label}`}><PencilSimple /></Button>}</div>;
}

function ReviewPaymentActions({
  payment, workspaceState, trial, amountPaise, submitting, canSubmit,
  paymentUnavailable, paymentAvailabilityLoading, onBack, onCancel, onRestart,
  onRetryPaymentAvailability, onOpenWorkspace, onSubmit,
}) {
  const { checkout, phase, error } = payment;
  const busy = ["creating", "opening", "reconciling", "waiting", "cancelling", "completed"].includes(phase);

  if (workspaceState.status === "error") return <div className="space-y-3">
    <PaymentNotice icon={CheckCircle} tone="warning" title="Workspace created" text={workspaceState.error} />
    <Button type="button" className="w-full" onClick={onOpenWorkspace}>Open workspace again <ArrowRight /></Button>
  </div>;

  if (workspaceState.status === "opening") return <PaymentNotice icon={CircleNotch} spin title="Opening your workspace" text="Your account is ready. We are starting the secure session now." />;

  if (!checkout && paymentUnavailable) return <div className="space-y-3">
    <PaymentNotice
      icon={XCircle}
      tone="warning"
      title="Secure checkout is temporarily unavailable"
      text="Payment setup is not ready right now. Recheck the connection or return after it has been configured."
    />
    <div className="flex flex-col-reverse gap-3 sm:flex-row">
      <Button type="button" variant="outline" disabled={paymentAvailabilityLoading} onClick={onBack}><ArrowLeft />Back</Button>
      <Button type="button" className="flex-1" variant="outline" loading={paymentAvailabilityLoading} loadingText="Checking checkout..." onClick={onRetryPaymentAvailability}>Check payment setup</Button>
    </div>
  </div>;

  if (!checkout) return <div className="flex flex-col-reverse gap-3 sm:flex-row">
    <Button type="button" variant="outline" disabled={submitting || phase === "creating"} onClick={onBack}><ArrowLeft />Back</Button>
    <Button type="button" size="lg" className="flex-1" loading={submitting || phase === "creating"} loadingText={trial ? "Creating workspace..." : "Opening payment..."} disabled={!canSubmit || paymentAvailabilityLoading} onClick={onSubmit}>
      {paymentAvailabilityLoading && !trial ? "Checking checkout..." : trial ? "Create trial workspace" : <>Pay {money(amountPaise)} <ArrowRight /></>}
    </Button>
  </div>;

  if (phase === "loading") return <PaymentNotice icon={CircleNotch} spin title="Checking your payment" text="Confirming the saved checkout securely." />;

  if (phase === "error") return <div className="space-y-3">
    <PaymentNotice icon={XCircle} tone="danger" title="Payment status is unavailable" text={error || "We could not check this payment."} />
    <div className="flex flex-col gap-3 sm:flex-row"><Button type="button" className="flex-1" onClick={payment.retryRecovery}>Try again</Button><Button type="button" variant="outline" onClick={onCancel}>Cancel and edit</Button></div>
  </div>;

  if (phase === "restart") return <div className="space-y-3">
    <PaymentNotice icon={XCircle} tone="warning" title="This payment session has ended" text="Start again to create a fresh checkout." />
    <Button type="button" className="w-full" onClick={onRestart}>Start a new payment session <ArrowRight /></Button>
  </div>;

  if (phase === "support") return <div className="space-y-3">
    <PaymentNotice icon={CheckCircle} tone="warning" title="Payment is under review" text="Your workspace will not be created twice. Edvatiq support can help complete the review." />
    <Button asChild className="w-full"><Link to="/#contact">Contact Edvatiq</Link></Button>
  </div>;

  if (phase === "cancelling") return <PaymentNotice icon={CircleNotch} spin title="Preparing your details" text="Closing the current checkout safely." />;

  if (["reconciling", "completed"].includes(phase)) return <PaymentNotice icon={CircleNotch} spin title={phase === "completed" ? "Opening your workspace" : "Confirming payment"} text="This normally takes only a few seconds. You can keep this page open." />;

  if (phase === "waiting") return <div className="space-y-3">
    <PaymentNotice icon={Clock} title="Payment confirmation is pending" text="The provider has not confirmed the payment yet. Your workspace will be created only after confirmation." />
    <Button type="button" variant="outline" className="w-full" onClick={payment.confirmPending}>Check again</Button>
  </div>;

  return <div className="space-y-3">
    {error && <PaymentNotice icon={XCircle} tone="warning" title="Payment was not completed" text={error} />}
    <Button type="button" size="lg" className="w-full" loading={phase === "opening"} loadingText="Opening payment..." disabled={busy} onClick={() => payment.openCheckout()}>
      {phase === "opening" ? "Opening payment" : `${error ? "Try payment again" : "Continue payment"} - ${money(checkout.amount_paise)}`} <ArrowRight />
    </Button>
    <Button type="button" variant="ghost" className="w-full" disabled={busy} onClick={onCancel}>Cancel checkout and edit</Button>
  </div>;
}

function PaymentNotice({ icon: Icon, title, text, tone = "neutral", spin = false, className = "" }) {
  const colors = {
    neutral: "border-border bg-secondary/35 text-foreground",
    warning: "border-amber-200 bg-amber-50 text-amber-950",
    danger: "border-red-200 bg-red-50 text-red-950",
  };
  return <div className={`flex items-start gap-3 rounded-xl border p-4 ${colors[tone] || colors.neutral} ${className}`} role="status" aria-live="polite">
    <Icon className={`mt-0.5 shrink-0 ${spin ? "animate-spin" : ""}`} />
    <div><div className="text-sm font-semibold">{title}</div><p className="mt-1 text-xs leading-5 opacity-75">{text}</p></div>
  </div>;
}

function PlanSkeleton() {
  return <div className="mt-5"><Skeleton className="h-10 w-52" /><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[1, 2, 3].map((item) => <Skeleton key={item} className="h-36 rounded-2xl" />)}</div></div>;
}

function ConfirmEmailChangeDialog({ open, onOpenChange, onConfirm }) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>Change the verified email?</DialogTitle><DialogDescription>This removes the current verification. The new address must be verified before you can return to Review.</DialogDescription></DialogHeader>
      <DialogFooter className="gap-2 sm:space-x-0"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Keep email</Button><Button type="button" onClick={onConfirm}>Change email</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

function RestoredPasswordDialog({ open, onOpenChange, values, errors, loading, onChange, onConfirm }) {
  return <Dialog open={open} onOpenChange={(value) => { if (!loading) onOpenChange(value); }}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>Confirm account security</DialogTitle><DialogDescription>For your protection, passwords are never saved with registration progress. Enter the owner password to continue.</DialogDescription></DialogHeader>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onConfirm(); }}>
        <Field label="Password" htmlFor="restored-password" error={errors.admin_password}><Input id="restored-password" type="password" autoComplete="new-password" value={values.admin_password} onChange={(event) => onChange("admin_password", event.target.value)} aria-invalid={Boolean(errors.admin_password)} autoFocus /><PasswordStrength password={values.admin_password || ""} compact /></Field>
        <Field label="Confirm password" htmlFor="restored-password-confirm" error={errors.admin_password_confirm}><Input id="restored-password-confirm" type="password" autoComplete="new-password" value={values.admin_password_confirm} onChange={(event) => onChange("admin_password_confirm", event.target.value)} aria-invalid={Boolean(errors.admin_password_confirm)} /></Field>
        <DialogFooter className="gap-2 pt-1 sm:space-x-0"><Button type="button" variant="outline" disabled={loading} onClick={() => onOpenChange(false)}>Cancel</Button><Button type="button" loading={loading} loadingText="Continuing..." onClick={onConfirm}>Confirm and continue</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}

function RegistrationRestoreSkeleton() {
  const summary = <div className="rounded-2xl border bg-card p-4"><Skeleton className="h-3 w-24" /><Skeleton className="mt-3 h-5 w-36" /><Skeleton className="mt-4 h-14 w-full" /></div>;
  return <RegistrationPanel aside={summary} footer={<div className="flex justify-end"><Skeleton className="h-11 w-full sm:w-56" /></div>}>
    <div role="status" aria-live="polite" aria-label="Restoring registration progress"><Skeleton className="h-3 w-20" /><Skeleton className="mt-3 h-8 w-72 max-w-full" /><Skeleton className="mt-2 h-4 w-96 max-w-full" /><div className="mt-6 space-y-3"><Skeleton className="h-16 w-full rounded-xl" /><Skeleton className="h-16 w-full rounded-xl" /><Skeleton className="h-16 w-full rounded-xl" /></div></div>
  </RegistrationPanel>;
}

function LoadError({ message, retry }) {
  return <div className="mt-6 rounded-2xl border bg-secondary/35 p-6 text-center"><p className="font-semibold">{message}</p><Button type="button" variant="outline" className="mt-4" onClick={retry}>Try again</Button></div>;
}
