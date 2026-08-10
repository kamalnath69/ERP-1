import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import Reports from "./Reports";

jest.mock("@/contexts/BusinessContext", () => ({
  useBusiness: () => ({ locationId: "location-1" }),
}));

jest.mock("@/store/api/workspaceApi", () => ({
  useGetReportsQuery: () => ({
    data: { invoice_count: 2, billed_paise: 15000, collected_paise: 10000, outstanding_paise: 5000 },
    isFetching: false,
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  }),
}));

test("renders report filters and summary without stale callback references", () => {
  const html = renderToStaticMarkup(<MemoryRouter><Reports /></MemoryRouter>);
  expect(html).toContain("Reports");
  expect(html).toContain("Apply range");
  expect(html).toContain("Invoices");
});
