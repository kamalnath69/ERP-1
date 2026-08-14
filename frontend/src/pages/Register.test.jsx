import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Register from "./Register";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  registerOrg: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ registerOrg: mocks.registerOrg }),
}));

vi.mock("@/lib/api", () => ({
  default: { get: mocks.get, post: mocks.post },
}));

const catalog = {
  trial_enabled: false,
  payment_available: true,
  payment: { provider: "razorpay" },
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
});

afterEach(() => {
  delete global.IS_REACT_ACT_ENVIRONMENT;
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
      <Route path="/register/payment/:checkoutId" element={<div>Dedicated payment reached</div>} />
      <Route path="/verify-email" element={<div>Verification reached</div>} />
    </Routes></MemoryRouter>);
  });
  return { container, root };
}

test("creates a paid checkout after focused plan, workspace, owner, and review phases", async () => {
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockImplementation((url) => {
    if (url === "/auth/registration/checkout") return Promise.resolve({ data: {
      checkout_id: "checkout-1",
      checkout_token: "a-secure-checkout-token-value",
      status: "ready",
      next_action: "pay",
      provider: "razorpay",
      mode: "test",
      order_id: "order-1",
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
  expect(container.textContent).toContain("Choose the right starting point");

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

  await act(async () => {
    inputValue(container.querySelector("#admin-first-name"), "Kavya");
    inputValue(container.querySelector("#admin-last-name"), "Raman");
    inputValue(container.querySelector("#admin-email"), "owner@example.com");
    inputValue(container.querySelector("#admin-password"), "StrongPass123");
    inputValue(container.querySelector("#admin-password-confirm"), "StrongPass123");
  });
  expect(buttonWith(container, "Continue").disabled).toBe(false);
  await act(async () => { buttonWith(container, "Continue").click(); });

  expect(container.textContent).toContain("Review before you continue");
  expect(container.textContent).not.toContain("Choose the right starting point");
  await act(async () => {
    inputValue(container.querySelector("#billing-state"), "Tamil Nadu");
    container.querySelector("#legal-accepted").click();
  });
  const submit = buttonWith(container, "Continue to secure payment");
  expect(submit.disabled).toBe(false);
  await act(async () => { submit.click(); await Promise.resolve(); });
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
  }));
  expect(container.textContent).toContain("Dedicated payment reached");
  expect([...mocks.post.mock.calls].some(([url]) => url.includes("mock-pay"))).toBe(false);

  act(() => root.unmount());
  container.remove();
});

test("migrates an existing checkout and shows recovery without reopening a provider", async () => {
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
  };
  sessionStorage.setItem("edvatiq.pending_signup_checkout.v1", JSON.stringify(saved));
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/public/legal/current") return Promise.resolve({ data: legal });
    if (url === "/auth/registration/checkouts/checkout-cashfree") return Promise.resolve({ data: saved });
    throw new Error(`Unexpected GET ${url}`);
  });

  const { container, root } = renderRegister();
  await settle();
  await settle();

  expect(container.textContent).toContain("Your secure checkout is ready");
  expect(sessionStorage.getItem("edvatiq.pending_signup_checkout.v1")).toBeNull();
  expect(sessionStorage.getItem("edvatiq.signup.checkout.v2")).toContain("checkout-cashfree");
  await act(async () => { buttonWith(container, "Continue payment").click(); });
  expect(container.textContent).toContain("Dedicated payment reached");
  expect(mocks.post).not.toHaveBeenCalled();

  act(() => root.unmount());
  container.remove();
});
