import React from "react";
import { ArrowLeft, Buildings, Lock, MapPin, Plug, WarningCircle } from "@phosphor-icons/react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { PageShell, Surface } from "@/components/system";
import { cn } from "@/lib/utils";

function SystemPage({ icon: Icon, eyebrow, title, description, actions, embedded }) {
  return <div className={cn("grid place-items-center", embedded ? "min-h-[65vh]" : "min-h-screen bg-background p-4")}>
    <Surface className="w-full max-w-2xl overflow-hidden p-7 text-center sm:p-12">
      <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-secondary text-muted-foreground"><Icon size={30} /></div>
      <div className="overline mt-7">{eyebrow}</div>
      <h1 className="mt-2 font-display text-3xl font-semibold sm:text-5xl">{title}</h1>
      <p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-muted-foreground sm:text-base">{description}</p>
      <div className="mt-7 flex flex-wrap justify-center gap-2">{actions}</div>
    </Surface>
  </div>;
}

export function PermissionDeniedPage({ embedded = false, title, description }) {
  const navigate = useNavigate();
  return <SystemPage embedded={embedded} icon={Lock} eyebrow="Access" title={title || "This area is not part of your role"} description={description || "Your account is working normally, but your current responsibilities or data scope do not include this screen."} actions={<Button onClick={() => navigate(-1)} variant="outline"><ArrowLeft className="mr-2" />Go back</Button>} />;
}

export function NotFoundPage({ embedded = false }) {
  return <SystemPage embedded={embedded} icon={WarningCircle} eyebrow="Not found" title="That page is not available" description="The link may be outdated, or the record may have been removed. No information was changed." actions={<Button asChild><Link to="/app">Return home</Link></Button>} />;
}

export function NoLocationPage({ embedded = false }) {
  return <SystemPage embedded={embedded} icon={MapPin} eyebrow="Location needed" title="Add a business location to continue" description="Operational records need a location before appointments, sales, stock, or industry workflows can be used." actions={<Button asChild><Link to="/app/settings?section=locations">Set up locations</Link></Button>} />;
}

export function PlanUnavailablePage({ embedded = false, module, title, description, retry }) {
  return <SystemPage embedded={embedded} icon={Buildings} eyebrow="Availability" title={title || `${module || "This feature"} is not enabled`} description={description || "Your current plan or business setup does not include this area. Existing records remain safe."} actions={<>{retry && <Button variant="outline" onClick={retry}>Try again</Button>}<Button asChild><Link to="/app/billing?section=plans">View plan</Link></Button></>} />;
}

export function OfflinePage({ embedded = false }) {
  return <SystemPage embedded={embedded} icon={Plug} eyebrow="Offline" title="Connection lost" description="Reconnect to load current business information. Unsaved forms should remain open until you decide what to do." actions={<Button onClick={() => window.location.reload()}>Try again</Button>} />;
}
