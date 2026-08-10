import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

import Landing from "./Landing";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api", () => ({
  default: { get: mocks.get },
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

async function renderLanding(catalog) {
  mocks.get.mockResolvedValueOnce({ data: catalog });
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter><Landing /></MemoryRouter>);
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

test("shows live paid pricing and paid-onboarding guidance when Trial is disabled", async () => {
  const view = await renderLanding({ plans: [paidPlan], trial_enabled: false, payment_available: true });
  expect(view.container.textContent).toContain("Paid onboarding is active");
  expect(view.container.textContent).toContain("Growth");
  expect(view.container.textContent).toContain("Choose Growth");
  expect(view.container.textContent).not.toContain("30-day trial");
  expect(view.container.textContent).toContain("Book a working session");
  expect(view.container.querySelector("#contact")).not.toBeNull();
  expect(view.container.querySelector('a[href^="mailto:sales@edvatiq.com"]')).not.toBeNull();
  const growthLink = [...view.container.querySelectorAll("a")].find((link) => link.textContent.includes("Choose Growth"));
  expect(growthLink?.getAttribute("href")).toContain("plan=growth");
  expect(growthLink?.getAttribute("href")).toContain("interval=monthly");
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
