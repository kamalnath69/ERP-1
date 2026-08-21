import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import PublicSiteLayout from "@/components/public/PublicSiteLayout";
import Landing from "./Landing";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock("@/lib/api", () => ({
  default: { get: mocks.get, post: mocks.post },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: null }),
}));

const paidPlan = {
  id: "growth",
  name: "Growth",
  description: "For growing organizations",
  recommended: true,
  purchasable: true,
  signup_mode: "paid",
  monthly_quote: { total_paise: 294882, tax_paise: 44982 },
  annual_quote: { total_paise: 2948820, tax_paise: 449820 },
  annual_saving_percent: 17,
  ai_credits: 2500,
  location_limit: 3,
  employee_limit: 15,
  client_limit: 2000,
};

async function renderLanding(catalog, { legalReady = true, initialEntry = "/" } = {}) {
  mocks.get.mockImplementation((url) => {
    if (url === "/public/site") return Promise.resolve({ data: { brand: "Edvatiq", support_email: "sales@edvatiq.com", contact_phone: "+919787867648", legal_ready: legalReady, legal_documents: { privacy: { id: "privacy-1" } } } });
    if (url === "/billing/public/plans") return typeof catalog === "function" ? catalog() : Promise.resolve({ data: catalog });
    throw new Error(`Unexpected GET ${url}`);
  });
  window.scrollTo = vi.fn();
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter initialEntries={[initialEntry]}><Routes><Route element={<PublicSiteLayout />}><Route index element={<Landing />} /></Route></Routes></MemoryRouter>);
    await Promise.resolve();
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
      delete global.IS_REACT_ACT_ENVIRONMENT;
    },
  };
}

test("shows live paid pricing without onboarding implementation copy when Trial is disabled", async () => {
  const view = await renderLanding({ plans: [paidPlan], trial_enabled: false, payment_available: true });
  expect(view.container.textContent).not.toContain("Secure paid onboarding");
  expect(view.container.textContent).toContain("Growth");
  expect(view.container.textContent).toContain("Pay and register");
  expect(view.container.textContent).not.toContain("30-day trial");
  expect(view.container.textContent).toContain("Start a conversation");
  expect(view.container.textContent).toContain("Need software built around your workflow?");
  expect(view.container.querySelector("#about")).not.toBeNull();
  expect(view.container.querySelector("#contact")).not.toBeNull();
  expect(view.container.querySelector("#contact form")).not.toBeNull();
  expect(view.container.querySelector('a[href^="mailto:sales@edvatiq.com"]')).not.toBeNull();
  expect(view.container.querySelector('a[href="tel:+919787867648"]')).not.toBeNull();
  expect(view.container.querySelector('a[href^="https://wa.me/919787867648"]')).not.toBeNull();
  const growthLink = [...view.container.querySelectorAll("a")].find((link) => link.textContent.includes("Pay and register"));
  expect(growthLink?.getAttribute("href")).toContain("plan=growth");
  expect(growthLink?.getAttribute("href")).toContain("interval=monthly");
  view.cleanup();
});

test("does not show form validation before the visitor interacts", async () => {
  const view = await renderLanding({ plans: [paidPlan], trial_enabled: false, payment_available: true });
  expect(view.container.textContent).not.toContain("Enter your organization");
  expect(view.container.querySelector('input[name="organization_name"]').getAttribute("aria-invalid")).toBe("false");
  view.cleanup();
});

test("fetches current public pricing once when the public site mounts", async () => {
  const view = await renderLanding({ plans: [paidPlan], trial_enabled: false, payment_available: true });
  const planCalls = mocks.get.mock.calls.filter(([url]) => url === "/billing/public/plans");
  expect(planCalls).toHaveLength(1);
  expect(planCalls[0][1]).toMatchObject({ forceRefetch: true });
  expect(planCalls[0][1]).not.toHaveProperty("signal");
  view.cleanup();
});

test("retries public pricing only when the user asks", async () => {
  let planRequestCount = 0;
  const view = await renderLanding(() => {
    planRequestCount += 1;
    if (planRequestCount === 1) return Promise.reject(new Error("Temporary failure"));
    return Promise.resolve({ data: { plans: [paidPlan], trial_enabled: false, payment_available: true } });
  });
  expect(view.container.textContent).toContain("Pricing is temporarily unavailable");

  const retry = [...view.container.querySelectorAll("button")].find((button) => button.textContent.includes("Try again"));
  await act(async () => {
    retry.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(planRequestCount).toBe(2);
  expect(view.container.textContent).toContain("Growth");
  view.cleanup();
});

test("offers the published Trial without inventing a hardcoded plan", async () => {
  const trial = {
    id: "trial", name: "Trial", description: "Explore Edvatiq", signup_mode: "trial",
    trial_days: 30, monthly_quote: { total_paise: 0, tax_paise: 0 },
    annual_quote: { total_paise: 0, tax_paise: 0 }, ai_credits: 100,
    location_limit: 1, employee_limit: 5, client_limit: 100,
  };
  const view = await renderLanding({ plans: [trial, paidPlan], trial_enabled: true, payment_available: true });
  expect(view.container.textContent).toContain("30-day trial");
  expect(view.container.querySelector('a[href="/register?plan=trial"]')).not.toBeNull();
  const trialLinks = [...view.container.querySelectorAll("a")].filter((link) => link.getAttribute("href")?.includes("plan=trial"));
  expect(trialLinks.some((link) => link.getAttribute("href").includes("interval=monthly"))).toBe(true);
  view.cleanup();
});

test("keeps priced plans connected to registration while legal publication is checked again there", async () => {
  const view = await renderLanding(
    { plans: [paidPlan], trial_enabled: false, payment_available: true },
    { legalReady: false },
  );
  expect(view.container.querySelector('a[href^="/register"]')).not.toBeNull();
  expect(view.container.textContent).toContain("Pay and register");
  expect(view.container.textContent).not.toContain("Talk to sales");
  const demoLinks = [...view.container.querySelectorAll("a")].filter((link) => link.textContent.trim() === "Book a demo");
  expect(demoLinks).toHaveLength(1);
  expect(demoLinks[0].getAttribute("href")).toBe("/#contact");
  view.cleanup();
});

test("reserves Talk to sales for the custom plan", async () => {
  const customPlan = {
    id: "enterprise", name: "Enterprise", description: "For complex organizations",
    signup_mode: "contact", monthly_quote: null, annual_quote: null,
    ai_credits: null, location_limit: null, employee_limit: null, client_limit: null,
  };
  const view = await renderLanding({ plans: [paidPlan, customPlan], trial_enabled: false, payment_available: true });
  expect([...view.container.querySelectorAll("a")].filter((link) => link.textContent.trim() === "Talk to sales")).toHaveLength(1);
  expect([...view.container.querySelectorAll("a")].filter((link) => link.textContent.includes("Pay and register"))).toHaveLength(1);
  view.cleanup();
});

test("switches the product preview without hiding either accessible tab", async () => {
  const view = await renderLanding({ plans: [paidPlan], trial_enabled: false, payment_available: true });
  const tabs = [...view.container.querySelectorAll('[role="tab"]')];
  const business = tabs.find((tab) => tab.textContent.trim() === "Business");
  expect(business).not.toBeUndefined();
  expect(business.getAttribute("aria-selected")).toBe("false");
  await act(async () => {
    business.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 350));
  });
  expect(business.getAttribute("aria-selected")).toBe("true");
  expect(view.container.textContent).toContain("Business position");
  view.cleanup();
});

test("deep-links to a custom project enquiry without requiring an organization", async () => {
  const view = await renderLanding(
    { plans: [paidPlan], trial_enabled: false, payment_available: true },
    { initialEntry: "/?inquiry=client_project#contact" },
  );
  expect(view.container.textContent).toContain("Tell us what you want to build.");
  expect(view.container.textContent).toContain("Send project enquiry");
  const organization = view.container.querySelector('input[name="organization_name"]');
  expect(organization.required).toBe(false);
  expect(view.container.querySelector('input[name="inquiry_type"]').value).toBe("client_project");
  view.cleanup();
});

test("submits a custom project with its enquiry type and no organization", async () => {
  mocks.post.mockResolvedValue({ data: { received: true } });
  const view = await renderLanding(
    { plans: [paidPlan], trial_enabled: false, payment_available: true },
    { initialEntry: "/?inquiry=client_project#contact" },
  );
  const setInput = async (selector, value) => {
    const input = view.container.querySelector(selector);
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    await act(async () => {
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await Promise.resolve();
    });
  };
  await setInput('input[name="name"]', "Kamal Nath");
  await setInput('input[name="work_email"]', "kamal@example.com");
  const form = view.container.querySelector("#contact form");
  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(mocks.post).toHaveBeenCalledWith("/public/demo-requests", expect.objectContaining({
    inquiry_type: "client_project",
    name: "Kamal Nath",
    work_email: "kamal@example.com",
    organization_name: null,
    privacy_document_id: "privacy-1",
    privacy_acknowledged: true,
  }));
  view.cleanup();
});
