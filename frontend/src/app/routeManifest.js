import {
  Bell, Books, CalendarBlank, ChartBar, CreditCard, Gear, House, Package,
  Receipt, ShieldCheck, Sparkle, Storefront, Users, UsersThree, Barbell,
  GraduationCap, Stethoscope, Scissors, Warehouse,
} from "@phosphor-icons/react";

const clientLabel = (industry, plural = true) => (
  industry === "clinic" ? (plural ? "Patients" : "Patient")
    : industry === "college" ? (plural ? "Students" : "Student")
      : (plural ? "Clients" : "Client")
);

export const ROUTES = [
  { key: "home", path: "/app", end: true, label: "Home", icon: House, permission: "dashboard.view", industryPermissions: { college: "college.placement_reports.view" }, group: "primary", mobile: 1, preload: "eager" },
  { key: "clients", path: "/app/clients", label: ({ industry }) => clientLabel(industry), singular: ({ industry }) => clientLabel(industry, false), icon: UsersThree, permission: "clients.view", module: "clients", group: "primary", mobile: 2, search: true, createPermission: "clients.manage" },
  { key: "calendar", path: "/app/calendar", label: "Calendar", icon: CalendarBlank, permission: "appointments.view", module: "appointments", group: "primary", mobile: 3, search: true, createPermission: "appointments.manage", excludedIndustries: ["college"] },
  { key: "gym", path: "/app/gym", label: "Gym", icon: Barbell, permission: "gym.dashboard.view", module: "gym", industries: ["gym"], group: "primary", mobile: 4 },
  { key: "salon", path: "/app/salon", label: "Salon", icon: Scissors, permission: "appointments.view", module: "salon", industries: ["salon"], group: "primary", mobile: 4 },
  { key: "clinic", path: "/app/clinic", label: "Clinic", icon: Stethoscope, permission: "clinic.view", module: "clinic", industries: ["clinic"], group: "primary", mobile: 4 },
  { key: "college", path: "/app/college", label: "Placement", icon: GraduationCap, permission: "college.view", module: "college", industries: ["college"], group: "primary", mobile: 4 },
  { key: "sales", path: "/app/sales", label: ({ industry }) => industry === "college" ? "Fee records" : "Sales", icon: Receipt, permission: "sales.view", module: "sales", group: "primary", mobile: 5, createPermission: "sales.manage", hideFromNavigationIndustries: ["college"] },
  { key: "catalog", path: "/app/catalog", label: "Catalog", icon: Package, permission: "catalog.view", module: "catalog", group: "more", search: true, createPermission: "catalog.manage", excludedIndustries: ["college"] },
  { key: "inventory", path: "/app/inventory", label: "Inventory", icon: Warehouse, permission: "inventory.view", module: "inventory", group: "more", excludedIndustries: ["college"] },
  { key: "team", path: "/app/team", label: ({ industry }) => industry === "college" ? "Faculty & staff" : "Team", icon: Users, permission: "employees.view", module: "employees", group: "more", search: true, createPermission: "employees.manage" },
  { key: "reports", path: "/app/reports", label: ({ industry }) => industry === "college" ? "Placement reports" : "Reports", icon: ChartBar, permission: "reports.view", industryPermissions: { college: "college.placement_reports.view" }, module: "reports", group: "more" },
  { key: "notifications", path: "/app/notifications", label: "Notifications", icon: Bell, permission: null, module: "notifications", group: "more" },
  { key: "documents", path: "/app/documents", label: "Documents", icon: Books, permission: "documents.view", module: "documents", group: "more" },
  { key: "ai", path: "/app/ai", label: "Edvatiq AI", icon: Sparkle, permission: "ai.use", module: "ai", group: "more", primaryIndustries: ["college"], layout: "secondary-fixed" },
  { key: "access", path: "/app/access", label: "Access", icon: ShieldCheck, permission: "roles.manage", group: "admin" },
  { key: "billing", path: "/app/billing", label: "Plan & billing", icon: CreditCard, permission: "billing.view", group: "admin" },
  { key: "settings", path: "/app/settings", label: "Settings", icon: Gear, permission: "settings.view", fallbackPermission: "settings.manage", group: "admin", layout: "secondary" },
  { key: "profile", path: "/app/me", label: "My profile", icon: Users, permission: null, group: "hidden" },
];

export function routeLabel(route, industry) {
  return typeof route.label === "function" ? route.label({ industry }) : route.label;
}

export function routeAvailable(route, { industry, can, hasModule }) {
  if (route.industries && !route.industries.includes(industry)) return false;
  if (route.excludedIndustries?.includes(industry)) return false;
  if (route.module && !hasModule(route.module)) return false;
  const permission = route.industryPermissions?.[industry] || route.permission;
  if (permission && !can(permission) && !(route.fallbackPermission && can(route.fallbackPermission))) return false;
  return true;
}

export function visibleRoutes(context) {
  return ROUTES.filter((route) => (
    route.group !== "hidden"
    && !route.hideFromNavigationIndustries?.includes(context.industry)
    && routeAvailable(route, context)
  )).map((route) => route.primaryIndustries?.includes(context.industry) ? { ...route, group: "primary" } : route);
}

export function routeForPath(pathname, industry) {
  const route = [...ROUTES]
    .sort((a, b) => b.path.length - a.path.length)
    .find((route) => route.end ? pathname === route.path : pathname === route.path || pathname.startsWith(`${route.path}/`));
  return route?.primaryIndustries?.includes(industry) ? { ...route, group: "primary" } : route;
}

export function destinationPath(destination, industry = "gym") {
  if (!destination) return null;
  if (destination.kind === "client") return `/app/clients/${destination.id}`;
  if (destination.kind === "employee") return `/app/team/${destination.id}`;
  if (destination.kind === "catalog") return `/app/catalog/${destination.id}`;
  const route = ROUTES.find((item) => item.key === destination.route);
  if (!route) return null;
  const params = new URLSearchParams();
  Object.entries(destination).forEach(([key, value]) => {
    if (key !== "route" && value != null) params.set(key, String(value));
  });
  const query = params.toString();
  return `${route.path}${query ? `?${query}` : ""}`;
}

export { clientLabel };
