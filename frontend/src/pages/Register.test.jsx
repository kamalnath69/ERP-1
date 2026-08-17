import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Register from "./Register";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  registerOrg: vi.fn(),
  refreshMe: vi.fn(),
  loadCashfreeCheckout: vi.fn(),
  loadRazorpayCheckout: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ registerOrg: mocks.registerOrg, refreshMe: mocks.refreshMe }),
}));

vi.mock("@/lib/api", () => ({
  default: { get: mocks.get, post: mocks.post },
}));
vi.mock("@/lib/cashfree", () => ({ loadCashfreeCheckout: mocks.loadCashfreeCheckout }));
vi.mock("@/lib/razorpay", () => ({ loadRazorpayCheckout: mocks.loadRazorpayCheckout }));

const catalog = {
  trial_enabled: false,
  payment_available: true,
  payment: { provider: "cashfree" },
  plans: [{
    id: "growth", name: "Growth", description: "For growing organizations",
    recommended: true, purchasable: true, signup_mode: "paid",
    monthly_quote: { subtotal_paise: 249900, total_paise: 294882, tax_paise: 44982 },
    annual_quote: { subtotal_paise: 2499000, total_paise: 2948820, tax_paise: 449820 },
    ai_credits: 2500,
  }],
};

const legal = {
  ready: true,
  documents: {
    terms: { id: "terms-v1" },
    privacy: { id: "privacy-v1" },
    refund: { id: "refund-v1" },
  },
};

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mocks.loadCashfreeCheckout.mockResolvedValue(undefined);
  mocks.loadRazorpayCheckout.mockResolvedValue(undefined);
  mocks.refreshMe.mockResolvedValue(undefined);
  delete window.Cashfree;
  delete window.Razorpay;
});

afterEach(() => {
  vi.useRealTimers();
  delete global.IS_REACT_ACT_ENVIRONMENT;
  delete window.Cashfree;
  delete window.Razorpay;
});

function inputValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function buttonWith(container, text) {
  return [...container.querySelectorAll("button")].find((button) => button.textContent.includes(text));
}

async function settle(milliseconds = 0) {
  await act(async () => {
    if (milliseconds) await new Promise((resolve) => setTimeout(resolve, milliseconds));
    else await Promise.resolve();
  });
}

function renderRegister(initialEntry = "/register?plan=growth") {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<MemoryRouter initialEntries={[initialEntry]}><Routes>
      <Route path="/register" element={<Register />} />
      <Route path="/register/payment/:checkoutId" element={<div>Legacy payment route reached</div>} />
      <Route path="/verify-email" element={<div>Verification reached</div>} />
      <Route path="/app" element={<div>Workspace opened</div>} />
    </Routes></MemoryRouter>);
  });
  return { container, root };
}

function storeReviewDraft({ proofExpiresAt = "2099-08-11T10:30:00Z" } = {}) {
  sessionStorage.setItem("edvatiq.signup.draft.v3", JSON.stringify({
    version: 3,
    fields: {
      industry: "gym",
      organization_name: "Northstar Gym",
      organization_slug: "northstar-gym",
      location_name: "Main Location",
      city: "Chennai",
      state: "Tamil Nadu",
      admin_first_name: "Kavya",
      admin_last_name: "Raman",
      admin_email: "owner@example.com",
      admin_phone: "9876543210",
      plan: "growth",
      billing_interval: "monthly",
    },
    flow: {
      active_step: 4,
      review_reached: true,
      edit_target: null,
      edit_snapshot: null,
    },
  }));
  sessionStorage.setItem("edvatiq.signup.email-verification.v1", JSON.stringify({
    challenge_id: "11111111-1111-4111-8111-111111111111",
    challenge_token: "a-browser-bound-challenge-token-value-long-enough",
    email: "owner@example.com",
    expires_at: "2099-08-11T10:10:00Z",
    resend_at: "2099-08-11T10:01:00Z",
    verification_proof: "a-verified-email-proof-value-that-is-long-enough",
    proof_expires_at: proofExpiresAt,
  }));
}

test("creates a paid checkout from Review and opens Cashfree in a modal", async () => {
  const providerCheckout = vi.fn(() => new Promise(() => {}));
  window.Cashfree = vi.fn(() => ({ checkout: providerCheckout }));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockImplementation((url) => {
    if (url === "/auth/registration/email/challenges") return Promise.resolve({ data: {
      challenge_id: "11111111-1111-4111-8111-111111111111",
      challenge_token: "a-browser-bound-challenge-token-value-long-enough",
      email: "owner@example.com",
      expires_at: "2099-08-11T10:10:00Z",
      resend_at: "2099-08-11T10:01:00Z",
    } });
    if (url === "/auth/registration/email/challenges/11111111-1111-4111-8111-111111111111/verify") return Promise.resolve({ data: {
      challenge_id: "11111111-1111-4111-8111-111111111111",
      email: "owner@example.com",
      verification_proof: "a-verified-email-proof-value-that-is-long-enough",
      proof_expires_at: "2099-08-11T10:30:00Z",
    } });
    if (url === "/auth/registration/checkout") return Promise.resolve({ data: {
      checkout_id: "checkout-1",
      checkout_token: "a-secure-checkout-token-value",
      status: "ready",
      next_action: "pay",
      provider: "cashfree",
      mode: "test",
      checkout_mode: "sandbox",
      payment_session_id: "payment-session-1",
      amount_paise: 294882,
      subtotal_paise: 249900,
      tax_paise: 44982,
      currency: "INR",
      expires_at: "2099-08-11T10:00:00Z",
      plan: { name: "Growth" },
      organization_name: "Northstar Gym",
      organization_slug: "northstar-gym",
      billing_interval: "monthly",
    } });
    throw new Error(`Unexpected POST ${url}`);
  });

  const { container, root } = renderRegister();
  await settle();
  expect(container.textContent).toContain("Choose your plan");

  await act(async () => { buttonWith(container, "Continue to workspace").click(); });
  await act(async () => {
    inputValue(container.querySelector("#organization-name"), "Northstar Gym");
    inputValue(container.querySelector("#organization-slug"), "northstar-gym");
    inputValue(container.querySelector("#location-name"), "Main Location");
    inputValue(container.querySelector("#city"), "Chennai");
  });
  await settle(420);
  expect(buttonWith(container, "Continue").disabled).toBe(false);
  await act(async () => { buttonWith(container, "Continue").click(); });

  await act(async () => { inputValue(container.querySelector("#admin-email"), "owner@example.com"); });
  await act(async () => { buttonWith(container, "Send code").click(); await Promise.resolve(); });
  await settle();
  await act(async () => { inputValue(container.querySelector("#owner-email-code"), "123456"); });
  await act(async () => { buttonWith(container, "Verify email").click(); await Promise.resolve(); });
  await settle();
  await act(async () => {
    inputValue(container.querySelector("#admin-first-name"), "Kavya");
    inputValue(container.querySelector("#admin-last-name"), "Raman");
    inputValue(container.querySelector("#admin-phone"), "9876543210");
    inputValue(container.querySelector("#admin-password"), "StrongPass123");
    inputValue(container.querySelector("#admin-password-confirm"), "StrongPass123");
  });
  expect(buttonWith(container, "Continue").disabled).toBe(false);
  await act(async () => { buttonWith(container, "Continue").click(); });

  expect(container.textContent).toContain("Confirm and continue");
  expect(container.textContent).not.toContain("Choose the right starting point");
  await act(async () => {
    inputValue(container.querySelector("#billing-state"), "Tamil Nadu");
    container.querySelector("#legal-accepted").click();
  });
  expect(container.textContent).toContain("Step 4 of 4");
  expect(container.textContent).not.toContain("Complete your first plan payment");
  const submit = buttonWith(container, "Pay");
  expect(submit.disabled).toBe(false);
  await act(async () => { submit.click(); await Promise.resolve(); });
  await settle();
  await settle();

  expect(mocks.registerOrg).not.toHaveBeenCalled();
  expect(mocks.post).toHaveBeenCalledWith("/auth/registration/checkout", expect.objectContaining({
    plan: "growth",
    billing_interval: "monthly",
    state: "Tamil Nadu",
    checkout_token: expect.any(String),
    legal_acceptance: {
      accepted: true,
      terms_document_id: "terms-v1",
      privacy_document_id: "privacy-v1",
      refund_document_id: "refund-v1",
    },
    email_verification: {
      challenge_id: "11111111-1111-4111-8111-111111111111",
      proof: "a-verified-email-proof-value-that-is-long-enough",
    },
  }));
  expect(providerCheckout).toHaveBeenCalledWith({
    paymentSessionId: "payment-session-1",
    redirectTarget: "_modal",
  });
  expect(container.textContent).toContain("Confirm and continue");
  expect(container.textContent).not.toContain("Legacy payment route reached");
  expect([...mocks.post.mock.calls].some(([url]) => url.includes("mock-pay"))).toBe(false);

  act(() => root.unmount());
  container.remove();
});

test("restores Review after refresh and requests the non-persisted password before payment", async () => {
  storeReviewDraft();
  const providerCheckout = vi.fn(() => new Promise(() => {}));
  window.Cashfree = vi.fn(() => ({ checkout: providerCheckout }));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockImplementation((url) => {
    if (url === "/auth/registration/checkout") return Promise.resolve({ data: {
      checkout_id: "checkout-restored",
      checkout_token: "a-secure-checkout-token-value",
      status: "ready",
      next_action: "pay",
      provider: "cashfree",
      mode: "test",
      checkout_mode: "sandbox",
      payment_session_id: "payment-session-restored",
      amount_paise: 294882,
      subtotal_paise: 249900,
      tax_paise: 44982,
      currency: "INR",
      plan: { name: "Growth" },
      organization_name: "Northstar Gym",
      organization_slug: "northstar-gym",
      billing_interval: "monthly",
    } });
    throw new Error(`Unexpected POST ${url}`);
  });

  const { container, root } = renderRegister();
  expect(container.textContent).not.toContain("Choose your plan");
  await settle();
  await settle();

  expect(container.textContent).toContain("Confirm and continue");
  expect(container.textContent).toContain("owner@example.com");
  expect(container.querySelector("#admin-password")).toBeNull();
  await settle(420);
  await act(async () => { container.querySelector("#legal-accepted").click(); });
  await settle();
  const pay = buttonWith(container, "Pay");
  expect(pay.disabled).toBe(false);
  await act(async () => { pay.click(); await Promise.resolve(); });

  expect(document.body.textContent).toContain("Confirm account security");
  expect(mocks.post).not.toHaveBeenCalledWith("/auth/registration/checkout", expect.anything());
  await act(async () => {
    inputValue(document.querySelector("#restored-password"), "StrongPass123");
    inputValue(document.querySelector("#restored-password-confirm"), "StrongPass123");
  });
  await act(async () => { buttonWith(document.body, "Confirm and continue").click(); await Promise.resolve(); });
  await settle();
  await settle();

  expect(mocks.post).toHaveBeenCalledWith("/auth/registration/checkout", expect.objectContaining({
    admin_email: "owner@example.com",
    admin_password: "StrongPass123",
  }));
  expect(providerCheckout).toHaveBeenCalledWith({ paymentSessionId: "payment-session-restored", redirectTarget: "_modal" });
  const persistedDraft = sessionStorage.getItem("edvatiq.signup.draft.v3");
  expect(persistedDraft).not.toContain("StrongPass123");
  expect(persistedDraft).not.toContain("legal_accepted");

  act(() => root.unmount());
  container.remove();
});

test("returns directly to Review after editing a completed plan", async () => {
  storeReviewDraft();
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });

  const { container, root } = renderRegister();
  await settle();
  await settle();
  await act(async () => { container.querySelector('button[aria-label="Edit Plan"]').click(); });
  expect(container.textContent).toContain("Editing from Review");
  await act(async () => { buttonWith(container, "Annual").click(); });
  await act(async () => { buttonWith(container, "Save and return to Review").click(); });

  expect(container.textContent).toContain("Confirm and continue");
  expect(container.textContent).toContain("Growth / annual");
  expect(container.textContent).not.toContain("Set up your organization");

  act(() => root.unmount());
  container.remove();
});

test("cancelling an Owner edit restores the previously verified email", async () => {
  storeReviewDraft();
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });

  const { container, root } = renderRegister();
  await settle();
  await settle(420);
  await act(async () => { container.querySelector('button[aria-label="Edit Owner"]').click(); });
  await act(async () => { buttonWith(container, "Change").click(); });
  const confirmChange = [...document.body.querySelectorAll("button")]
    .filter((button) => button.textContent.includes("Change email"))
    .at(-1);
  await act(async () => { confirmChange.click(); });
  await act(async () => { inputValue(container.querySelector("#admin-email"), "new-owner@example.com"); });
  await act(async () => { buttonWith(container, "Cancel").click(); });

  expect(container.textContent).toContain("Confirm and continue");
  expect(container.textContent).toContain("owner@example.com");
  expect(JSON.parse(sessionStorage.getItem("edvatiq.signup.email-verification.v1")).email).toBe("owner@example.com");

  act(() => root.unmount());
  container.remove();
});

test("moves an expired restored email proof back to Owner", async () => {
  storeReviewDraft({ proofExpiresAt: "2020-08-11T10:30:00Z" });
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });

  const { container, root } = renderRegister();
  await settle();
  await settle();

  expect(container.textContent).toContain("Set up the workspace owner");
  expect(container.querySelector("#admin-email")).not.toBeNull();
  expect(container.textContent).not.toContain("Confirm and continue");

  act(() => root.unmount());
  container.remove();
});

test("migrates an existing checkout and shows recovery without reopening a provider", async () => {
  const providerCheckout = vi.fn(() => new Promise(() => {}));
  window.Cashfree = vi.fn(() => ({ checkout: providerCheckout }));
  const saved = {
    checkout_id: "checkout-cashfree",
    checkout_token: "a-secure-checkout-token-value",
    status: "ready",
    next_action: "pay",
    provider: "cashfree",
    mode: "test",
    checkout_mode: "sandbox",
    payment_session_id: "cashfree-session",
    amount_paise: 117882,
    subtotal_paise: 99900,
    tax_paise: 17982,
    expires_at: "2099-08-15T10:00:00Z",
    organization_name: "Northstar College",
    organization_slug: "northstar-college",
    plan: { name: "Starter" },
    billing_interval: "monthly",
    plan_id: "growth",
  };
  sessionStorage.setItem("edvatiq.pending_signup_checkout.v1", JSON.stringify(saved));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/registration/checkouts/checkout-cashfree") return Promise.resolve({ data: saved });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });

  const { container, root } = renderRegister();
  await settle();
  await settle();

  expect(container.textContent).toContain("Confirm and continue");
  expect(container.textContent).toContain("Continue payment");
  expect(sessionStorage.getItem("edvatiq.pending_signup_checkout.v1")).toBeNull();
  expect(sessionStorage.getItem("edvatiq.signup.checkout.v2")).toContain("checkout-cashfree");
  expect(providerCheckout).not.toHaveBeenCalled();
  await act(async () => { buttonWith(container, "Continue payment").click(); });
  await settle();
  expect(providerCheckout).toHaveBeenCalledWith({ paymentSessionId: "cashfree-session", redirectTarget: "_modal" });
  expect(container.textContent).not.toContain("Legacy payment route reached");
  expect(mocks.post).not.toHaveBeenCalled();

  act(() => root.unmount());
  container.remove();
});

test("reconciles a completed verified checkout and opens the workspace", async () => {
  const saved = {
    checkout_id: "checkout-cashfree",
    checkout_token: "a-secure-checkout-token-value",
    status: "ready",
    next_action: "pay",
    provider: "cashfree",
    mode: "test",
    checkout_mode: "sandbox",
    payment_session_id: "cashfree-session",
    amount_paise: 117882,
    subtotal_paise: 99900,
    tax_paise: 17982,
    organization_name: "Northstar College",
    organization_slug: "northstar-college",
    plan: { name: "Starter" },
    billing_interval: "monthly",
    plan_id: "growth",
  };
  sessionStorage.setItem("edvatiq.signup.checkout.v2", JSON.stringify(saved));
  window.Cashfree = vi.fn(() => ({ checkout: vi.fn(() => Promise.resolve({ paymentDetails: {} })) }));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/registration/checkouts/checkout-cashfree") return Promise.resolve({ data: saved });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockImplementation((url) => {
    if (url === "/auth/registration/checkouts/checkout-cashfree/reconcile") return Promise.resolve({ data: {
      ...saved,
      status: "completed",
      next_action: "open_workspace",
      email: "owner@example.com",
    } });
    if (url === "/auth/registration/checkouts/checkout-cashfree/session") return Promise.resolve({ data: { user: { id: "owner-1" }, csrf_token: "csrf" } });
    throw new Error(`Unexpected POST ${url}`);
  });

  const { container, root } = renderRegister();
  await settle();
  await settle();
  await act(async () => { buttonWith(container, "Continue payment").click(); await Promise.resolve(); });
  await settle();
  await settle();

  expect(mocks.post).toHaveBeenCalledWith(
    "/auth/registration/checkouts/checkout-cashfree/reconcile",
    {},
    expect.objectContaining({ headers: { "X-Signup-Token": saved.checkout_token } }),
  );
  expect(container.textContent).toContain("Workspace opened");
  expect(mocks.post).toHaveBeenCalledWith(
    "/auth/registration/checkouts/checkout-cashfree/session",
    {},
    expect.objectContaining({ headers: { "X-Signup-Token": saved.checkout_token } }),
  );
  expect(mocks.refreshMe).toHaveBeenCalled();
  expect(sessionStorage.getItem("edvatiq.signup.checkout.v2")).toBeNull();

  act(() => root.unmount());
  container.remove();
});

test("restores payment controls after bounded checks do not confirm payment", async () => {
  const saved = {
    checkout_id: "checkout-cashfree",
    checkout_token: "a-secure-checkout-token-value",
    status: "ready",
    next_action: "pay",
    provider: "cashfree",
    mode: "test",
    checkout_mode: "sandbox",
    payment_session_id: "cashfree-session",
    amount_paise: 117882,
    subtotal_paise: 99900,
    tax_paise: 17982,
    organization_name: "Northstar College",
    organization_slug: "northstar-college",
    plan: { name: "Starter" },
    billing_interval: "monthly",
    plan_id: "growth",
  };
  sessionStorage.setItem("edvatiq.signup.checkout.v2", JSON.stringify(saved));
  window.Cashfree = vi.fn(() => ({ checkout: vi.fn(() => Promise.resolve({})) }));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/registration/checkouts/checkout-cashfree") return Promise.resolve({ data: saved });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockResolvedValue({ data: saved });

  const { container, root } = renderRegister();
  await settle();
  await settle();
  vi.useFakeTimers();
  await act(async () => { buttonWith(container, "Continue payment").click(); await Promise.resolve(); });
  await settle();
  for (const delay of [1200, 1700, 2200, 2700]) {
    await act(async () => { await vi.advanceTimersByTimeAsync(delay); });
  }
  await settle();

  expect(container.textContent).toContain("Payment has not been confirmed");
  expect(buttonWith(container, "Try payment again").disabled).toBe(false);
  expect(mocks.post).toHaveBeenCalledTimes(5);

  act(() => root.unmount());
  container.remove();
});

test("cancelling a recovered checkout clears it and returns to owner details", async () => {
  const saved = {
    checkout_id: "checkout-cashfree",
    checkout_token: "a-secure-checkout-token-value",
    status: "ready",
    next_action: "pay",
    provider: "cashfree",
    mode: "test",
    checkout_mode: "sandbox",
    payment_session_id: "cashfree-session",
    amount_paise: 117882,
    subtotal_paise: 99900,
    tax_paise: 17982,
    organization_name: "Northstar College",
    organization_slug: "northstar-college",
    plan: { name: "Starter" },
    billing_interval: "monthly",
    plan_id: "growth",
  };
  sessionStorage.setItem("edvatiq.signup.checkout.v2", JSON.stringify(saved));
  sessionStorage.setItem("edvatiq.signup.draft.v2", JSON.stringify({
    organization_name: "Northstar College",
    organization_slug: "northstar-college",
    admin_first_name: "Kavya",
    admin_last_name: "Raman",
    admin_email: "owner@example.com",
    plan: "growth",
    billing_interval: "monthly",
  }));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/registration/checkouts/checkout-cashfree") return Promise.resolve({ data: saved });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockResolvedValue({ data: { ...saved, status: "cancelled", next_action: "restart" } });

  const { container, root } = renderRegister();
  await settle();
  await settle();
  await act(async () => { buttonWith(container, "Cancel checkout and edit").click(); });
  const confirm = [...document.body.querySelectorAll("button")]
    .filter((button) => button.textContent.includes("Cancel and edit"))
    .at(-1);
  await act(async () => { confirm.click(); await Promise.resolve(); });
  await settle();

  expect(container.textContent).toContain("Set up the workspace owner");
  expect(container.querySelector("#admin-email")).not.toBeNull();
  expect(container.querySelector("#admin-password")).toBeNull();
  expect(sessionStorage.getItem("edvatiq.signup.checkout.v2")).toBeNull();

  act(() => root.unmount());
  container.remove();
});

test("restores payment controls when the Cashfree promise does not settle", async () => {
  const saved = {
    checkout_id: "checkout-cashfree",
    checkout_token: "a-secure-checkout-token-value",
    status: "ready",
    next_action: "pay",
    provider: "cashfree",
    mode: "test",
    checkout_mode: "sandbox",
    payment_session_id: "cashfree-session",
    amount_paise: 117882,
    subtotal_paise: 99900,
    tax_paise: 17982,
    organization_name: "Northstar College",
    organization_slug: "northstar-college",
    plan: { name: "Starter" },
    billing_interval: "monthly",
    plan_id: "growth",
  };
  sessionStorage.setItem("edvatiq.signup.checkout.v2", JSON.stringify(saved));
  window.Cashfree = vi.fn(() => ({ checkout: vi.fn(() => new Promise(() => {})) }));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/registration/checkouts/checkout-cashfree") return Promise.resolve({ data: saved });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockResolvedValue({ data: saved });

  const { container, root } = renderRegister();
  await settle();
  await settle();
  vi.useFakeTimers();
  await act(async () => { buttonWith(container, "Continue payment").click(); await Promise.resolve(); });
  await act(async () => { vi.advanceTimersByTime(13050); await Promise.resolve(); });
  await settle();

  expect(container.textContent).toContain("The payment window did not respond");
  expect(buttonWith(container, "Try payment again").disabled).toBe(false);

  act(() => root.unmount());
  container.remove();
});

test("a legacy provider return reconciles without overriding verification navigation", async () => {
  const saved = {
    checkout_id: "checkout-cashfree",
    checkout_token: "a-secure-checkout-token-value",
    status: "ready",
    next_action: "pay",
    provider: "cashfree",
    mode: "test",
    checkout_mode: "sandbox",
    payment_session_id: "cashfree-session",
    amount_paise: 117882,
    subtotal_paise: 99900,
    tax_paise: 17982,
    organization_name: "Northstar College",
    organization_slug: "northstar-college",
    plan: { name: "Starter" },
    billing_interval: "monthly",
    plan_id: "growth",
  };
  sessionStorage.setItem("edvatiq.signup.checkout.v2", JSON.stringify(saved));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockResolvedValue({ data: {
    ...saved,
    status: "completed",
    next_action: "verify_email",
    email: "owner@example.com",
    email_sent: true,
  } });

  const { container, root } = renderRegister("/register?payment_return=checkout-cashfree");
  await settle();
  await settle();

  expect(container.textContent).toContain("Verification reached");
  expect(mocks.post).toHaveBeenCalledWith(
    "/auth/registration/checkouts/checkout-cashfree/reconcile",
    {},
    expect.objectContaining({ headers: { "X-Signup-Token": saved.checkout_token } }),
  );

  act(() => root.unmount());
  container.remove();
});
