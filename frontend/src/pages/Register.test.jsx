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

vi.mock("@/lib/razorpay", () => ({ loadRazorpayCheckout: vi.fn() }));
vi.mock("@/lib/cashfree", () => ({ loadCashfreeCheckout: vi.fn() }));

const catalog = {
  trial_enabled: false,
  payment_available: true,
  plans: [{
    id: "growth", name: "Growth", description: "For growing organizations",
    recommended: true, purchasable: true, signup_mode: "paid",
    monthly_quote: { total_paise: 294882, tax_paise: 44982 },
    annual_quote: { total_paise: 2948820, tax_paise: 449820 },
    ai_credits: 2500,
  }],
};

function inputValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function buttonWith(container, text) {
  return [...container.querySelectorAll("button")].find((button) => button.textContent.includes(text));
}

test("uses payment-first signup and never calls free registration when Trial is disabled", async () => {
  mocks.get.mockImplementation((url) => {
    if (url === "/billing/public/plans") return Promise.resolve({ data: catalog });
    if (url === "/auth/organization-id/availability") return Promise.resolve({ data: { available: true, message: "Available", suggestions: [] } });
    throw new Error(`Unexpected GET ${url}`);
  });
  mocks.post.mockImplementation((url) => {
    if (url === "/auth/registration/checkout") return Promise.resolve({ data: {
      checkout_id: "checkout-1", checkout_token: "a-secure-checkout-token-value", status: "ready",
      mock_mode: true, mode: "mock", order_id: "mock-order", amount_paise: 294882,
      currency: "INR", expires_at: "2026-08-11T10:00:00Z", plan: { name: "Growth" },
    } });
    if (url === "/auth/registration/checkouts/checkout-1/mock-pay") return Promise.resolve({ data: {
      status: "completed", email: "owner@example.com", organization_slug: "northstar-gym",
      email_sent: true, requires_verification: true,
    } });
    throw new Error(`Unexpected POST ${url}`);
  });

  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter initialEntries={["/register?plan=growth"]}><Routes><Route path="/register" element={<Register />} /><Route path="/verify-email" element={<div>Verification reached</div>} /></Routes></MemoryRouter>);
    await Promise.resolve();
  });

  await act(async () => { buttonWith(container, "Continue").click(); });
  let inputs = container.querySelectorAll("input");
  await act(async () => {
    inputValue(inputs[0], "Northstar Gym");
    inputValue(inputs[2], "Main Location");
    inputValue(inputs[3], "Chennai");
  });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
  await act(async () => { buttonWith(container, "Continue").click(); });

  await act(async () => {
    inputValue(container.querySelector("#admin-first-name"), "Kavya");
    inputValue(container.querySelector("#admin-last-name"), "Raman");
    inputValue(container.querySelector("#admin-email"), "owner@example.com");
    inputValue(container.querySelector("#admin-password"), "StrongPass123");
    inputValue(container.querySelector("#admin-password-confirm"), "StrongPass123");
  });
  await act(async () => { buttonWith(container, "Continue").click(); await Promise.resolve(); });

  expect(container.textContent).toContain("Trial is currently unavailable");
  const state = container.querySelector('input[placeholder="Tamil Nadu"]');
  await act(async () => { inputValue(state, "Tamil Nadu"); });
  await act(async () => { buttonWith(container, "Pay").click(); await Promise.resolve(); await Promise.resolve(); });

  expect(mocks.registerOrg).not.toHaveBeenCalled();
  expect(mocks.post).toHaveBeenCalledWith("/auth/registration/checkout", expect.objectContaining({ plan: "growth", state: "Tamil Nadu" }));
  expect(container.textContent).toContain("Verification reached");

  act(() => root.unmount());
  container.remove();
  sessionStorage.clear();
  delete global.IS_REACT_ACT_ENVIRONMENT;
});
