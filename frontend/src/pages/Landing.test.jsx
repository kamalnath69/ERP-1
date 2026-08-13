import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import PublicSiteLayout from "@/components/public/PublicSiteLayout";
import Landing from "./Landing";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api", () => ({
  default: { get: mocks.get },
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

async function renderLanding(catalog, { legalReady = true } = {}) {
  mocks.get.mockImplementation((url) => {
    if (url === "/public/site") return Promise.resolve({ data: { brand: "Edvatiq", support_email: "sales@edvatiq.com", legal_ready: legalReady, legal_documents: { privacy: { id: "privacy-1" } } } });
    if (url === "/billing/public/plans") return typeof catalog === "function" ? catalog() : Promise.resolve({ data: catalog });
    throw new Error(`Unexpected GET ${url}`);
  });
  window.scrollTo = vi.fn();
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter><Routes><Route element={<PublicSiteLayout />}><Route index element={<Landing />} /></Route></Routes></MemoryRouter>);
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
  expect(view.container.textContent).toContain("Book a working session");
  expect(view.container.querySelector("#about")).not.toBeNull();
  expect(view.container.querySelector("#contact")).not.toBeNull();
  expect(view.container.querySelector("#contact form")).not.toBeNull();
  expect(view.container.querySelector('a[href^="mailto:sales@edvatiq.com"]')).not.toBeNull();
  const growthLink = [...view.container.querySelectorAll("a")].find((link) => link.textContent.includes("Pay and register"));
  expect(growthLink?.getAttribute("href")).toContain("plan=growth");
  expect(growthLink?.getAttribute("href")).toContain("interval=monthly");
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
