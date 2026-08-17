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
  if (industry === "college" && routeKey === "home" && !routeAvailable(route, { industry, can, hasModule: business.hasModule, accessContext })) {
    const domainEnabled = (domain) => !accessContext?.domain_levels || Boolean(accessContext.domain_levels[domain] && accessContext.domain_levels[domain] !== "none");
    const destination = domainEnabled("attendance") && (can("college.attendance.view") || can("college.attendance.mark")) ? "/app/academics?section=attendance"
      : domainEnabled("assessments") && (can("college.assessments.view") || can("college.assessments.record") || can("college.assessments.manage")) ? "/app/academics?section=assessments"
        : domainEnabled("academics") && (can("college.academics.view") || can("college.academics.manage")) ? "/app/academics"
          : domainEnabled("data") && can("college.integrations.manage") ? "/app/academics?section=integrations"
            : domainEnabled("data") && (can("college.data.view") || can("college.imports.manage")) ? "/app/academics?section=exchange"
              : domainEnabled("placements") && (can("college.placements.view") || can("college.opportunities.manage") || can("college.companies.manage") || can("college.applications.manage")) ? "/app/college"
                : domainEnabled("readiness") && (can("college.readiness.view") || can("college.readiness.policy.manage")) ? "/app/college?section=readiness"
                  : domainEnabled("coding") && can("college.coding.view") ? "/app/college?section=coding"
                    : domainEnabled("clearance") && can("college.clearance.view") ? "/app/college?section=clearance"
                      : domainEnabled("students") && can("college.students.view") ? "/app/clients"
                        : can("roles.manage") ? "/app/access"
                          : null;
    if (destination) return <Navigate to={destination} replace />;
  }
  if (!routeAvailable(route, { industry, can, hasModule: business.hasModule, accessContext })) return <PermissionDeniedPage embedded />;
  const noLocationAllowed = ["settings", "billing", "profile", "notifications"].includes(routeKey);
  if (!business.locations.length && !noLocationAllowed) return <NoLocationPage embedded />;
  if (business.error && !business.context) return <PlanUnavailablePage embedded title="Business information is unavailable" description={business.error} retry={business.refresh} />;
  return React.cloneElement(children, { key: location.pathname });
}
