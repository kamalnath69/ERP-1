import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import RegisterPayment from "./RegisterPayment";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  loadCashfreeCheckout: vi.fn(),
  loadRazorpayCheckout: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ default: { get: mocks.get, post: mocks.post } }));
vi.mock("@/lib/cashfree", () => ({ loadCashfreeCheckout: mocks.loadCashfreeCheckout }));
vi.mock("@/lib/razorpay", () => ({ loadRazorpayCheckout: mocks.loadRazorpayCheckout }));

const checkout = {
  checkout_id: "checkout-1",
  checkout_token: "a-secure-checkout-token-value",
  status: "ready",
  next_action: "pay",
  provider: "cashfree",
  mode: "test",
  checkout_mode: "sandbox",
  payment_session_id: "session-1",
  amount_paise: 117882,
  subtotal_paise: 99900,
  tax_paise: 17982,
  currency: "INR",
  expires_at: "2099-08-15T10:00:00Z",
  organization_name: "Northstar College",
  organization_slug: "northstar-college",
  plan: { name: "Starter" },
  billing_interval: "monthly",
};

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem("edvatiq.signup.checkout.v2", JSON.stringify(checkout));
  global.IS_REACT_ACT_ENVIRONMENT = true;
  delete window.Cashfree;
});

afterEach(() => {
  vi.useRealTimers();
  delete global.IS_REACT_ACT_ENVIRONMENT;
  delete window.Cashfree;
});

function buttonWith(container, text) {
  return [...container.querySelectorAll("button")].find((button) => button.textContent.includes(text));
}

function renderPayment(entry = "/register/payment/checkout-1") {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<MemoryRouter initialEntries={[entry]}><Routes>
      <Route path="/register/payment/:checkoutId" element={<RegisterPayment />} />
      <Route path="/register" element={<div>Registration reached</div>} />
      <Route path="/verify-email" element={<div>Verification reached</div>} />
    </Routes></MemoryRouter>);
  });
  return { container, root };
}

async function settle() {
  await act(async () => { await Promise.resolve(); });
}

test("Cashfree uses a full-page handoff without locking navigation on an unresolved provider promise", async () => {
  mocks.get.mockResolvedValue({ data: checkout });
  mocks.loadCashfreeCheckout.mockResolvedValue(undefined);
  const providerPromise = new Promise(() => {});
  const providerCheckout = vi.fn(() => providerPromise);
  window.Cashfree = vi.fn(() => ({ checkout: providerCheckout }));

  const { container, root } = renderPayment();
  await settle();
  await settle();
  expect(container.textContent).toContain("Complete your first plan payment");

  vi.useFakeTimers();
  await act(async () => { buttonWith(container, "Pay").click(); await Promise.resolve(); });
  expect(providerCheckout).toHaveBeenCalledWith({ paymentSessionId: "session-1", redirectTarget: "_self" });
  expect(container.querySelector('a[href="/register"]').getAttribute("aria-disabled")).toBeNull();
  expect(buttonWith(container, "Check payment status").disabled).toBe(false);

  await act(async () => { vi.advanceTimersByTime(13050); });
  expect(buttonWith(container, "Pay").disabled).toBe(false);

  act(() => root.unmount());
  container.remove();
});

test("a Cashfree return reconciles once and continues to email verification", async () => {
  mocks.post.mockImplementation((url) => {
    if (url === "/auth/registration/checkouts/checkout-1/reconcile") return Promise.resolve({ data: {
      ...checkout,
      status: "completed",
      next_action: "verify_email",
      email: "owner@example.com",
      organization_slug: "northstar-college",
      email_sent: true,
    } });
    throw new Error(`Unexpected POST ${url}`);
  });

  const { container, root } = renderPayment("/register/payment/checkout-1?returned=1");
  await settle();
  await settle();

  expect(mocks.post).toHaveBeenCalledTimes(1);
  expect(mocks.post.mock.calls[0][0]).toBe("/auth/registration/checkouts/checkout-1/reconcile");
  expect(container.textContent).toContain("Verification reached");
  expect(sessionStorage.getItem("edvatiq.signup.checkout.v2")).toBeNull();

  act(() => root.unmount());
  container.remove();
});

test("cancelling a checkout clears recovery and returns to editable registration", async () => {
  mocks.get.mockResolvedValue({ data: checkout });
  mocks.post.mockImplementation((url) => {
    if (url === "/auth/registration/checkouts/checkout-1/cancel") return Promise.resolve({ data: { ...checkout, status: "cancelled", next_action: "restart" } });
    throw new Error(`Unexpected POST ${url}`);
  });

  const { container, root } = renderPayment();
  await settle();
  await act(async () => { buttonWith(container, "Cancel and edit").click(); });
  expect(document.body.textContent).toContain("Cancel this checkout?");
  const confirm = [...document.body.querySelectorAll("button")].filter((button) => button.textContent.includes("Cancel and edit")).at(-1);
  await act(async () => { confirm.click(); await Promise.resolve(); });
  await settle();

  expect(container.textContent).toContain("Registration reached");
  expect(sessionStorage.getItem("edvatiq.signup.checkout.v2")).toBeNull();

  act(() => root.unmount());
  container.remove();
});
