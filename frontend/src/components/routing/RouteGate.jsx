import React from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { ROUTES, routeAvailable } from "@/app/routeManifest";
import { NoLocationPage, NotFoundPage, PermissionDeniedPage, PlanUnavailablePage } from "@/pages/SystemPages";
import { PageSkeleton } from "@/components/system";

export default function RouteGate({ routeKey, children }) {
  const { can } = useAuth();
  const business = useBusiness();
  const location = useLocation();
  const route = ROUTES.find((item) => item.key === routeKey);
  if (business.loading && !business.context) return <PageSkeleton />;
  if (!route) return <NotFoundPage embedded />;
  const industry = business.organization?.industry;
  if (route.industries && !route.industries.includes(industry)) return <NotFoundPage embedded />;
  if (route.excludedIndustries?.includes(industry)) return <NotFoundPage embedded />;
  if (route.module && !business.hasModule(route.module)) return <PlanUnavailablePage embedded module={typeof route.label === "string" ? route.label : "This area"} />;
  if (!routeAvailable(route, { industry, can, hasModule: business.hasModule })) return <PermissionDeniedPage embedded />;
  const noLocationAllowed = ["settings", "billing", "profile", "notifications"].includes(routeKey);
  if (!business.locations.length && !noLocationAllowed) return <NoLocationPage embedded />;
  if (business.error && !business.context) return <PlanUnavailablePage embedded title="Business information is unavailable" description={business.error} retry={business.refresh} />;
  return React.cloneElement(children, { key: location.pathname });
}
