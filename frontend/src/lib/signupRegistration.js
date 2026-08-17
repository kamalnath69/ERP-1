const CHECKOUT_KEY = "edvatiq.signup.checkout.v2";
const LEGACY_CHECKOUT_KEY = "edvatiq.pending_signup_checkout.v1";
const DRAFT_KEY = "edvatiq.signup.draft.v3";
const LEGACY_DRAFT_KEY = "edvatiq.signup.draft.v2";
const EMAIL_VERIFICATION_KEY = "edvatiq.signup.email-verification.v1";

const draftFields = [
  "industry", "organization_name", "organization_slug", "location_name", "city", "state",
  "admin_first_name", "admin_last_name", "admin_email", "admin_phone", "plan", "billing_interval",
];

const defaultFlow = {
  active_step: 1,
  review_reached: false,
  edit_target: null,
  edit_snapshot: null,
};

function storage() {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

function parse(value) {
  try { return JSON.parse(value || "null"); }
  catch { return null; }
}

export function readSignupCheckout() {
  const target = storage();
  if (!target) return null;
  const current = parse(target.getItem(CHECKOUT_KEY));
  if (current?.checkout_id && current?.checkout_token) return current;
  const legacy = parse(target.getItem(LEGACY_CHECKOUT_KEY));
  if (!legacy?.checkout_id || !legacy?.checkout_token) return null;
  target.setItem(CHECKOUT_KEY, JSON.stringify(legacy));
  target.removeItem(LEGACY_CHECKOUT_KEY);
  return legacy;
}

export function saveSignupCheckout(value) {
  const target = storage();
  if (target && value?.checkout_id && value?.checkout_token) {
    target.setItem(CHECKOUT_KEY, JSON.stringify(value));
    target.removeItem(LEGACY_CHECKOUT_KEY);
  }
  return value;
}

export function updateSignupCheckout(value) {
  const current = readSignupCheckout();
  if (!current || current.checkout_id !== value?.checkout_id) return current;
  return saveSignupCheckout({ ...current, ...value, checkout_token: current.checkout_token });
}

export function clearSignupCheckout() {
  const target = storage();
  target?.removeItem(CHECKOUT_KEY);
  target?.removeItem(LEGACY_CHECKOUT_KEY);
}

function safeFields(values) {
  return Object.fromEntries(draftFields.map((key) => [key, values?.[key] ?? ""]));
}

function safeFlow(value) {
  const activeStep = Number(value?.active_step);
  const editTarget = Number(value?.edit_target);
  return {
    active_step: [1, 2, 3, 4].includes(activeStep) ? activeStep : 1,
    review_reached: Boolean(value?.review_reached),
    edit_target: [1, 2, 3].includes(editTarget) ? editTarget : null,
    edit_snapshot: value?.edit_snapshot && typeof value.edit_snapshot === "object"
      ? safeFields(value.edit_snapshot)
      : null,
  };
}

export function readSignupDraftState() {
  const target = storage();
  if (!target) return { fields: {}, flow: defaultFlow };
  const current = parse(target.getItem(DRAFT_KEY));
  if (current?.version === 3 && current.fields && typeof current.fields === "object") {
    return { fields: safeFields(current.fields), flow: safeFlow(current.flow) };
  }
  const legacy = parse(target.getItem(LEGACY_DRAFT_KEY));
  if (!legacy || typeof legacy !== "object") return { fields: {}, flow: defaultFlow };
  const migrated = { version: 3, fields: safeFields(legacy), flow: defaultFlow };
  target.setItem(DRAFT_KEY, JSON.stringify(migrated));
  target.removeItem(LEGACY_DRAFT_KEY);
  return { fields: migrated.fields, flow: migrated.flow };
}

export function readSignupDraft() {
  return readSignupDraftState().fields;
}

export function saveSignupDraft(values, flow = defaultFlow) {
  const target = storage();
  if (!target) return;
  target.setItem(DRAFT_KEY, JSON.stringify({
    version: 3,
    fields: safeFields(values),
    flow: safeFlow(flow),
  }));
  target.removeItem(LEGACY_DRAFT_KEY);
}

export function clearSignupDraft() {
  const target = storage();
  target?.removeItem(DRAFT_KEY);
  target?.removeItem(LEGACY_DRAFT_KEY);
}

export function readSignupEmailVerification() {
  const value = parse(storage()?.getItem(EMAIL_VERIFICATION_KEY));
  if (!value?.challenge_id || !value?.challenge_token || !value?.email) return null;
  if (value.verification_proof && Date.parse(value.proof_expires_at || "") <= Date.now()) {
    storage()?.removeItem(EMAIL_VERIFICATION_KEY);
    return null;
  }
  return value;
}

export function saveSignupEmailVerification(value) {
  const target = storage();
  if (!target || !value?.challenge_id || !value?.challenge_token || !value?.email) return null;
  const safe = {
    challenge_id: value.challenge_id,
    challenge_token: value.challenge_token,
    email: value.email.trim().toLowerCase(),
    expires_at: value.expires_at,
    resend_at: value.resend_at,
    verification_proof: value.verification_proof || null,
    proof_expires_at: value.proof_expires_at || null,
  };
  target.setItem(EMAIL_VERIFICATION_KEY, JSON.stringify(safe));
  return safe;
}

export function clearSignupEmailVerification() {
  storage()?.removeItem(EMAIL_VERIFICATION_KEY);
}

export function storePendingVerification(result) {
  const pending = {
    email: result.email,
    org_slug: result.organization_slug,
    email_sent: result.email_sent,
  };
  clearSignupCheckout();
  clearSignupDraft();
  storage()?.setItem("edvatiq.pending_verification", JSON.stringify(pending));
  return pending;
}

export async function boundedSignupRequest(run, timeoutMs = 12000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try { return await run(controller.signal); }
  catch (error) {
    if (error?.code === "ERR_CANCELED" || error?.name === "CanceledError" || error?.name === "AbortError") {
      throw new Error("The request took too long. Please try again.");
    }
    throw error;
  }
  finally { window.clearTimeout(timeout); }
}

export const signupCheckoutStorageKey = CHECKOUT_KEY;
export const signupDraftStorageKey = DRAFT_KEY;
