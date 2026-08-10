import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import Billing from "./Billing";

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    organization: { plan: "starter" },
    user: { first_name: "Kamal", email: "kamal@example.com" },
    refreshMe: jest.fn(),
  }),
}));

jest.mock("@/store/api/billingApi", () => {
  const invoices = Array.from({ length: 6 }, (_, index) => ({
    id: `invoice-${index + 1}`,
    invoice_number: `EDV-202608-${index + 1}`,
    description: index === 5 ? "Hidden sixth invoice" : `Invoice purchase ${index + 1}`,
    purchase_type: "plan",
    billing_interval: "monthly",
    amount_paise: 117882,
    tax_paise: 17982,
    status: "paid",
    created_at: `2026-08-0${index + 1}T00:00:00Z`,
  }));

  return {
  useGetBillingOverviewQuery: () => ({
    data: {
      plans: [
        {
          id: "trial", name: "Trial", description: "Try the workspace", purchasable: false,
          monthly_price_paise: 0, annual_price_paise: 0, monthly_quote: { total_paise: 0 },
          annual_quote: { total_paise: 0 }, entitlements: {}, features: [], ai_credits: 100,
        },
        {
          id: "starter", name: "Starter", description: "For a focused team", purchasable: true,
          monthly_price_paise: 99900, annual_price_paise: 999000, tax_enabled: true,
          gst_rate_bps: 1800, monthly_quote: { total_paise: 117882 }, annual_quote: { total_paise: 1178820 },
          entitlements: { "module.ai": true }, features: [], ai_credits: 500,
          employee_limit: 5, client_limit: 500, location_limit: 1, ai_tier: "basic",
        },
        {
          id: "growth", name: "Growth", description: "For growing operations", purchasable: true, recommended: true,
          monthly_price_paise: 249900, annual_price_paise: 2499000, tax_enabled: true,
          gst_rate_bps: 1800, monthly_quote: { total_paise: 294882 }, annual_quote: { total_paise: 2948820 },
          entitlements: { "module.ai": true, "documents.knowledge": true }, features: [], ai_credits: 2500,
          employee_limit: 15, client_limit: 2000, location_limit: 3, ai_tier: "advanced",
        },
      ],
      subscription: {
        plan: "starter", status: "active", current_period_end: "2026-08-31T00:00:00Z",
      },
      scheduled_change: null,
      payment: { configured: true, mode: "test" },
      wallet: {
        wallet: { balance_credits: 420, available_credits: 420, cycle_grant_credits: 500, cycle_end: "2026-08-31T00:00:00Z" },
        packs: [{
          id: "pack-1", name: "Quick top-up", credits: 500, expires_at: "2027-08-04T00:00:00Z",
          quote: { total_paise: 58882, tax_paise: 8982, tax_enabled: true, gst_rate_bps: 1800 },
        }],
      },
      invoices: invoices.slice(0, 5),
      invoice_summary: { total: invoices.length, paid: invoices.length },
    },
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: jest.fn(),
  }),
  useGetBillingInvoicesQuery: () => ({
    data: {
      items: invoices.slice(0, 5),
      next_cursor: "next-page",
      has_more: true,
      summary: { total: invoices.length, paid: invoices.length },
    },
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: jest.fn(),
  }),
  usePreviewPlanCheckoutMutation: () => [jest.fn()],
  useCreatePlanCheckoutMutation: () => [jest.fn()],
  useCreatePackCheckoutMutation: () => [jest.fn()],
  useVerifyBillingPaymentMutation: () => [jest.fn()],
  useMockPayInvoiceMutation: () => [jest.fn()],
  useSchedulePlanChangeMutation: () => [jest.fn()],
  };
});

test("keeps wallet recharge and billing history visible before plan comparison", () => {
  const html = renderToStaticMarkup(<Billing />);

  expect(html).toContain('href="#ai-wallet"');
  expect(html).toContain('href="#billing-history"');
  expect(html.indexOf("AI wallet recharge")).toBeLessThan(html.indexOf("Choose the capacity your team needs"));
  expect(html.indexOf("Invoices and payments")).toBeLessThan(html.indexOf("Choose the capacity your team needs"));
  expect(html).toContain("Quick top-up");
  expect(html).toContain("EDV-202608-1");
  expect(html).toContain("Load more");
  expect(html).not.toContain("Hidden sixth invoice");
  expect(html).not.toContain("<table");
});
