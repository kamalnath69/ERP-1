import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import Dashboard from "./Dashboard";

jest.mock("react-redux", () => ({
  useDispatch: () => jest.fn(),
  useSelector: (selector) => selector({ preferences: { dashboardLayouts: {} } }),
  useStore: () => ({ dispatch: jest.fn(), getState: () => ({ preferences: { dashboardLayouts: {} } }), subscribe: jest.fn() }),
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { first_name: "Kamal" } }),
}));

jest.mock("@/contexts/BusinessContext", () => ({
  useBusiness: () => ({
    organization: { name: "Pulse Fitness", industry: "gym" },
    locationId: "location-1",
    location: { name: "Main Studio" },
  }),
}));

jest.mock("@/store/api/workspaceApi", () => ({
  useGetDashboardWorkspaceQuery: () => ({
    data: {
      industry: "gym",
      roles: ["owner"],
      source: { generated_at: new Date().toISOString() },
      quick_actions: [
        { id: "new_client", label: "Add client", destination: { route: "clients" } },
        { id: "new_sale", label: "New sale", destination: { route: "sales" } },
      ],
      metrics: [
        { id: "collections_today", label: "Collected today", value: 50000, format: "money", destination: { route: "sales" } },
        { id: "collections_period", label: "Collections", value: 220000, format: "money", comparison: { change_percent: 10 } },
        { id: "revenue_period", label: "Invoiced revenue", value: 300000, format: "money" },
        { id: "outstanding", label: "Outstanding", value: 80000, format: "money", tone: "warning" },
        { id: "active_clients", label: "Active clients", value: 42 },
        { id: "checkins_today", label: "Check-ins today", value: 9 },
        { id: "renewals_due", label: "Renewals due", value: 3, tone: "warning" },
      ],
      widgets: [
        { id: "my_work", kind: "work_queue", title: "My work", subtitle: "Assigned work", data: [], empty: { title: "All caught up", message: "No work" } },
        {
          id: "client_attention", kind: "attention", title: "Clients needing attention", subtitle: "Current signals",
          data: [{ id: "signal-1", state: "watch", title: "Renewal is near", reason: "Expires soon", client: { name: "Aarav" } }],
        },
        { id: "collections_trend", kind: "line_chart", title: "Collections trend", subtitle: "Captured payments", format: "money", data: [{ date: "2026-08-04", value_paise: 50000 }] },
        { id: "sales_status_mix", kind: "donut_chart", title: "Sales payment mix", subtitle: "Invoiced value by payment status", format: "money", x_key: "label", series: [{ key: "value_paise", label: "Value" }], data: [{ label: "Paid", value_paise: 200000 }] },
        { id: "client_growth", kind: "bar_chart", title: "New-client growth", subtitle: "Clients added", data: [{ date: "2026-08-04", value: 2 }] },
      ],
    },
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: jest.fn(),
  }),
  useSaveMyPreferenceMutation: () => [jest.fn()],
}));

test("uses a compact metric ribbon before the balanced analytics grid", () => {
  const html = renderToStaticMarkup(<MemoryRouter><Dashboard /></MemoryRouter>);

  expect(html).not.toContain("Quick actions");
  expect(html).not.toContain("Live business data");
  expect(html).not.toContain("Updated just now");
  expect(html.indexOf("7 days")).toBeLessThan(html.indexOf("Sales payment mix"));
  expect(html).toContain("lg:items-start");
  expect((html.match(/data-dashboard-metric=/g) || [])).toHaveLength(4);
  expect(html).toContain('aria-label="Key business metrics"');
  expect(html).toContain("grid-cols-2");
  expect(html.indexOf("Collections trend")).toBeLessThan(html.indexOf("Sales payment mix"));
  expect(html.indexOf("Sales payment mix")).toBeLessThan(html.indexOf("New-client growth"));
  expect(html).toContain("Collections trend");
  expect(html).toContain("Sales payment mix");
  expect(html).toContain("New-client growth");
  expect(html).toContain("Operational snapshot");
  expect(html).not.toContain("The four numbers worth seeing first");
  expect(html).not.toContain("Movement, mix, and growth");
  expect(html).not.toContain("Three complementary views");
  expect(html).toContain("items-stretch");
  expect(html).toContain("auto-rows-fr");
  expect(html).not.toContain("Â");
});
