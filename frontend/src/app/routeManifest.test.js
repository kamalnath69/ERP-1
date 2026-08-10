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
  expect(routeLabel(byKey.calendar, "college")).toBe("Student schedule");
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
