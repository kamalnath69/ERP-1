import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { ROUTES, routeAvailable } from "@/app/routeManifest";
import { NoLocationPage, NotFoundPage, PermissionDeniedPage, PlanUnavailablePage } from "@/pages/SystemPages";
import { PageSkeleton } from "@/components/system";

export default function RouteGate({ routeKey, children }) {
  const { can, accessContext } = useAuth();
  const business = useBusiness();
  const location = useLocation();
  const route = ROUTES.find((item) => item.key === routeKey);
  if (business.loading && !business.context) return <PageSkeleton />;
  if (!route) return <NotFoundPage embedded />;
  const industry = business.organization?.industry;
  const policyNeutralRoutes = new Set(["access", "settings", "billing", "profile", "notifications"]);
  if (industry === "college" && accessContext && accessContext.status !== "active" && !policyNeutralRoutes.has(routeKey)) {
    return <PermissionDeniedPage
      embedded
      title="Your College access is awaiting review"
      description="An owner or Access Admin needs to confirm your responsibilities and data reach before student or placement records become available."
    />;
  }
  if (route.industries && !route.industries.includes(industry)) return <NotFoundPage embedded />;
  if (route.excludedIndustries?.includes(industry)) return <NotFoundPage embedded />;
  if (route.module && !business.hasModule(route.module)) return <PlanUnavailablePage embedded module={typeof route.label === "string" ? route.label : "This area"} />;
  if (industry === "college" && routeKey === "home" && !routeAvailable(route, { industry, can, hasModule: business.hasModule })) {
    const destination = can("college.attendance.view") ? "/app/college?section=attendance"
      : can("college.assessments.view") ? "/app/college?section=assessments"
        : can("college.placements.view") ? "/app/college"
          : can("college.students.view") ? "/app/clients"
            : can("college.clearance.view") ? "/app/college?section=clearance"
              : can("roles.manage") ? "/app/access"
                : null;
    if (destination) return <Navigate to={destination} replace />;
  }
  if (!routeAvailable(route, { industry, can, hasModule: business.hasModule })) return <PermissionDeniedPage embedded />;
  const noLocationAllowed = ["settings", "billing", "profile", "notifications"].includes(routeKey);
  if (!business.locations.length && !noLocationAllowed) return <NoLocationPage embedded />;
  if (business.error && !business.context) return <PlanUnavailablePage embedded title="Business information is unavailable" description={business.error} retry={business.refresh} />;
  return React.cloneElement(children, { key: location.pathname });
}
