import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { BusinessProvider, useBusiness } from "./BusinessContext";

jest.mock("react-redux", () => ({
  useDispatch: () => jest.fn(),
  useSelector: () => "campus-1",
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1", is_super_admin: false } }),
}));

jest.mock("@/store/api/baseApi", () => ({
  useGetQuery: () => ({
    data: {
      data: {
        organization: { id: "college-1", name: "Demo College", industry: "college", enabled_modules: ["college"] },
        locations: [{ id: "campus-1", name: "Main Campus" }],
        preferences: {},
        entitlements: { values: {} },
      },
    },
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: jest.fn(),
  }),
}));

function ContextProbe() {
  const business = useBusiness();
  return <div>{business.industry}:{business.organization.industry}:{business.location.name}</div>;
}

test("exposes the organization industry to shared College-aware pages", () => {
  const html = renderToStaticMarkup(<BusinessProvider><ContextProbe /></BusinessProvider>);

  expect(html).toContain("college:college:Main Campus");
});
