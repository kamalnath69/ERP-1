import { selectDegradedQueries } from "./DataHealthBanner";

describe("data health selection", () => {
  test("reports only degraded queries that are currently visible", () => {
    const state = {
      api: {
        subscriptions: { active: { subscription: {} } },
        queries: {
          active: { endpointName: "getSales", originalArgs: { locationId: "1" }, status: "rejected", data: [{ id: "sale-1" }] },
          inactive: { endpointName: "getReports", originalArgs: {}, status: "rejected" },
        },
      },
    };

    expect(selectDegradedQueries(state)).toEqual([
      { endpointName: "getSales", originalArgs: { locationId: "1" }, hasData: true },
    ]);
  });

  test("reports fulfilled partial workspaces", () => {
    const state = {
      api: {
        subscriptions: { workspace: { subscription: {} } },
        queries: {
          workspace: { endpointName: "getDashboardWorkspace", originalArgs: {}, status: "fulfilled", data: { _sync: { partial: true } } },
        },
      },
    };

    expect(selectDegradedQueries(state)).toHaveLength(1);
  });
});
