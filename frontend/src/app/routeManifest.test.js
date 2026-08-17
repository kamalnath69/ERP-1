import { routeAvailable, routeLabel, visibleRoutes } from "./routeManifest";

const context = {
  industry: "college",
  can: () => true,
  hasModule: () => true,
};

test("exposes a placement-native College navigation", () => {
  const routes = visibleRoutes(context);
  const byKey = Object.fromEntries(routes.map((route) => [route.key, route]));

  expect(routeLabel(byKey.home, "college")).toBe("Home");
  expect(routeLabel(byKey.clients, "college")).toBe("Students");
  expect(byKey.calendar).toBeUndefined();
  expect(routeLabel(byKey.college, "college")).toBe("Placement");
  expect(routeLabel(byKey.team, "college")).toBe("Faculty & staff");
  expect(routeLabel(byKey.reports, "college")).toBe("Placement reports");
});

test("keeps generic commerce modules outside the College workspace", () => {
  const keys = visibleRoutes(context).map((route) => route.key);

  expect(keys).not.toContain("sales");
  expect(keys).not.toContain("catalog");
  expect(keys).not.toContain("inventory");
  expect(routeAvailable({ excludedIndustries: ["college"] }, context)).toBe(false);
});

test("requires the scoped College reporting permission for Home and reports", () => {
  const permissions = new Set(["dashboard.view", "reports.view"]);
  const routes = visibleRoutes({
    ...context,
    can: (permission) => permissions.has(permission),
  });
  const keys = routes.map((route) => route.key);

  expect(keys).not.toContain("home");
  expect(keys).not.toContain("reports");

  permissions.add("college.placement_reports.view");
  const authorizedKeys = visibleRoutes({
    ...context,
    can: (permission) => permissions.has(permission),
  }).map((route) => route.key);
  expect(authorizedKeys).toContain("home");
  expect(authorizedKeys).toContain("reports");
});

test("keeps Notifications routable while excluding it from sidebar navigation", () => {
  const notificationRoute = visibleRoutes(context).find((route) => route.key === "notifications");

  expect(notificationRoute).toBeDefined();
  expect(notificationRoute.hideFromSidebar).toBe(true);
  expect(routeAvailable(notificationRoute, context)).toBe(true);
});
