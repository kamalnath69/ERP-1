import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import Billing from "./Billing";

let canManage = true;

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    organization: { plan: "starter", industry: "gym" },
    user: { first_name: "Kamal", email: "kamal@example.com" },
    refreshMe: vi.fn(),
    can: (permission) => permission !== "billing.manage" || canManage,
  }),
}));

vi.mock("@/store/api/billingApi", () => {
  const invoices = Array.from({ length: 6 }, (_, index) => ({
    id: `invoice-${index + 1}`,
    invoice_number: `EDV-202608-${index + 1}`,
    description: index === 5 ? "Hidden sixth invoice" : `Invoice purchase ${index + 1}`,
    purchase_type: index === 1 ? "wallet_pack" : "plan",
    billing_interval: "monthly",
    amount_paise: 117882,
    tax_paise: 17982,
    status: "paid",
    created_at: `2026-08-0${index + 1}T00:00:00Z`,
  }));

  const overview = {
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
      {
        id: "enterprise", name: "Enterprise", description: "Custom rollout and limits", purchasable: false,
        entitlements: {}, features: [], ai_credits: 0,
      },
    ],
    subscription: {
      plan: "starter", status: "active", billing_interval: "monthly", version: 2,
      current_period_end: "2026-08-31T00:00:00Z", razorpay_subscription_id: "sub-1",
    },
    scheduled_change: null,
    payment: { configured: true, mode: "test", recurring_supported: true },
    wallet: {
      wallet: {
        balance_credits: 420, available_credits: 420, reserved_credits: 0,
        cycle_grant_credits: 500, cycle_end: "2026-08-31T00:00:00Z",
      },
      packs: [{
        id: "pack-1", name: "Quick top-up", credits: 500, expires_at: "2027-08-04T00:00:00Z",
        quote: { total_paise: 58882, tax_paise: 8982, tax_enabled: true, gst_rate_bps: 1800 },
      }],
    },
    invoices: invoices.slice(0, 5),
    invoice_summary: { total: invoices.length, paid: invoices.length, amount_paise: 707292 },
  };

  return {
    useGetBillingOverviewQuery: () => ({
      data: overview,
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    }),
    useGetBillingInvoicesQuery: () => ({
      currentData: {
        items: invoices.slice(0, 5),
        next_cursor: "next-page",
        has_more: true,
        summary: { total: invoices.length, paid: invoices.length, amount_paise: 707292 },
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    }),
    usePreviewPlanCheckoutMutation: () => [vi.fn()],
    useCreatePlanCheckoutMutation: () => [vi.fn()],
    useCreatePackCheckoutMutation: () => [vi.fn()],
    useVerifyBillingPaymentMutation: () => [vi.fn()],
    useMockPayInvoiceMutation: () => [vi.fn()],
    useSchedulePlanChangeMutation: () => [vi.fn()],
    useCancelPlanMutation: () => [vi.fn()],
    useRemoveScheduledPlanChangeMutation: () => [vi.fn()],
  };
});

function renderBilling(path = "/app/billing?section=subscription") {
  return renderToStaticMarkup(<MemoryRouter initialEntries={[path]}><Billing /></MemoryRouter>);
}

beforeEach(() => {
  canManage = true;
});

test("opens a focused subscription overview by default", () => {
  const html = renderBilling("/app/billing");

  expect(html).toContain("Subscription");
  expect(html).toContain("Current subscription");
  expect(html).toContain("Latest payment");
  expect(html).not.toContain("Choose the right capacity");
  expect(html).not.toContain("Invoices and payments");
});

test("opens plans as a separate URL-backed section", () => {
  const html = renderBilling("/app/billing?section=plans");

  expect(html).toContain("Choose the right capacity");
  expect(html).toContain("Starter");
  expect(html).toContain("Growth");
  expect(html).toContain("Talk to sales");
  expect(html).toContain("Compare all features");
  expect(html).not.toContain("Invoices and payments");
});

test("shows filtered, cursor-ready invoice records only in invoices", () => {
  const html = renderBilling("/app/billing?section=invoices");

  expect(html).toContain("Invoices and payments");
  expect(html).toContain("EDV-202608-1");
  expect(html).toContain('aria-label="Purchase type"');
  expect(html).toContain('aria-label="Invoice status"');
  expect(html).toContain("Load more");
  expect(html).not.toContain("Hidden sixth invoice");
  expect(html).not.toContain("Choose the right capacity");
});

test("maps legacy wallet anchors to the AI credits section", () => {
  const html = renderBilling("/app/billing#ai-wallet");

  expect(html).toContain("Available balance");
  expect(html).toContain("One-time top-ups");
  expect(html).toContain("Quick top-up");
});

test("keeps billing data visible but hides purchase controls for read-only users", () => {
  canManage = false;
  const html = renderBilling("/app/billing?section=plans");

  expect(html).toContain("Starter");
  expect(html).toContain("View only");
  expect(html).not.toContain("Choose plan");
});
