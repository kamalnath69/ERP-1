const CHECKOUT_KEY = "edvatiq.signup.checkout.v2";
const LEGACY_CHECKOUT_KEY = "edvatiq.pending_signup_checkout.v1";
const DRAFT_KEY = "edvatiq.signup.draft.v2";

const draftFields = [
  "industry", "organization_name", "organization_slug", "location_name", "city", "state",
  "admin_first_name", "admin_last_name", "admin_email", "admin_phone", "plan", "billing_interval",
];

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

export function readSignupDraft() {
  const value = parse(storage()?.getItem(DRAFT_KEY));
  return value && typeof value === "object" ? value : {};
}

export function saveSignupDraft(values) {
  const target = storage();
  if (!target) return;
  const safe = Object.fromEntries(draftFields.map((key) => [key, values?.[key] ?? ""]));
  target.setItem(DRAFT_KEY, JSON.stringify(safe));
}

export function clearSignupDraft() {
  storage()?.removeItem(DRAFT_KEY);
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
