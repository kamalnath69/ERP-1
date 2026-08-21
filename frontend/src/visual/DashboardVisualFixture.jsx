import React from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight, Briefcase, Buildings, CalendarCheck, CheckCircle,
  SlidersHorizontal, Sparkle, Student, Target, WarningCircle,
} from "@phosphor-icons/react";

import {
  DashboardBand, DashboardCanvas, DashboardLanes, DashboardPreviewCard,
  EmptyState, PageShell,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import "@/index.css";

const query = new URLSearchParams(window.location.search);
const kind = query.get("kind") === "business" ? "business" : "college";
const scenario = ["empty", "sparse", "dense", "long", "restricted"].includes(query.get("scenario"))
  ? query.get("scenario")
  : "dense";
const profile = query.get("profile") || (kind === "college" ? "leadership" : "operations");

const scenarioCount = { empty: 0, sparse: 1, dense: 4, long: 4, restricted: 2 }[scenario];
const longCopy = scenario === "long"
  ? "This intentionally long label verifies that translated or unusually descriptive ERP content wraps naturally without forcing neighboring cards to match its height."
  : null;

function MetricRibbon({ business = false }) {
  const labels = business
    ? ["Collected today", "Active clients", "Appointments", "Outstanding"]
    : ["Students in scope", "Placement ready", "Needs support", "Placed"];
  const values = scenario === "empty" ? [0, 0, 0, 0] : business ? ["₹82,450", 428, 36, "₹1.8L"] : [110, 34, 18, 27];
  return <DashboardBand as="section" className="surface-card overflow-hidden" aria-label="Summary metrics">
    <div className="dashboard-metric-grid gap-px bg-border">
      {labels.map((label, index) => <article key={label} className="min-h-28 bg-card p-4 sm:p-5">
        <div className="text-xs font-semibold leading-5 text-muted-foreground">{label}</div>
        <div className="mt-3 font-display text-3xl font-semibold tracking-[-0.05em]">{values[index]}</div>
      </article>)}
    </div>
  </DashboardBand>;
}

function FixtureFilters({ business = false }) {
  return <DashboardBand as="div">
    <div className="dashboard-filter-compact surface-card w-full items-center justify-between gap-3 p-3">
      <div><div className="overline">Current scope</div><div className="mt-1 text-sm font-semibold">{business ? "Main location / Last 30 days" : "All authorized students"}</div></div>
      <Button variant="outline"><SlidersHorizontal className="mr-2" />Filters</Button>
    </div>
    <div className="dashboard-filter-expanded surface-card gap-3 p-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))" }}>
      {(business ? ["Location", "Period", "Team"] : ["Academic year", "Graduation batch", "Department", "Program", "Cohort"]).map((label) => <div key={label} className="min-w-0 rounded-xl bg-secondary/65 px-3 py-2.5">
        <div className="overline">{label}</div><div className="mt-1 truncate text-sm font-semibold">All available</div>
      </div>)}
    </div>
  </DashboardBand>;
}

function SimpleTrend({ business = false }) {
  return <div className="relative border-t px-4 pb-4 pt-3 sm:px-5" style={{ height: "clamp(14rem, 54cqi, 18rem)" }}>
    <svg className="h-full w-full" viewBox="0 0 680 240" role="img" aria-label={business ? "Collections trend" : "Attendance trend"} preserveAspectRatio="none">
      {[45, 95, 145, 195].map((y) => <line key={y} x1="16" y1={y} x2="664" y2={y} stroke="hsl(var(--border))" strokeDasharray="5 6" />)}
      <path d="M18 188 C100 170 125 185 205 142 S335 160 410 104 S550 72 662 40 L662 222 L18 222 Z" fill="hsl(var(--chart-1) / .12)" />
      <path d="M18 188 C100 170 125 185 205 142 S335 160 410 104 S550 72 662 40" fill="none" stroke="hsl(var(--chart-1))" strokeWidth="4" strokeLinecap="round" />
    </svg>
  </div>;
}

function ListCard({ eyebrow, title, description, rows, icon: Icon = Student, total = rows.length, actionHref, emptyCopy = "Nothing needs attention in this scope." }) {
  return <DashboardPreviewCard
    eyebrow={eyebrow}
    title={title}
    description={description}
    footer={total > rows.length && actionHref ? <><span className="text-xs text-muted-foreground">Showing {rows.length} of {total}</span><a href={actionHref} className="inline-flex items-center text-xs font-semibold text-primary">View all {total}<ArrowRight className="ml-1" /></a></> : null}
  >
    {rows.length ? <div className="divide-y border-t">{rows.map((row, index) => <a key={`${title}-${index}`} href={row.href || "#authorized-record"} className="flex min-h-16 items-start gap-3 px-4 py-3.5 transition-colors hover:bg-secondary/45 sm:px-5">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary text-muted-foreground"><Icon size={17} /></span>
      <span className="min-w-0 flex-1"><span className="block text-sm font-semibold leading-5">{row.title}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{row.detail}</span>{row.chips && <span className="mt-2 flex flex-wrap gap-1.5">{row.chips.map((chip) => <span key={chip} className="rounded-full border bg-secondary/65 px-2 py-0.5 text-[10px] font-medium">{chip}</span>)}</span>}</span>
      <ArrowRight className="mt-2 shrink-0 text-muted-foreground" />
    </a>)}</div> : <EmptyState variant="inline" alignment="left" icon={CheckCircle} title="All clear" description={emptyCopy} className="m-4" />}
  </DashboardPreviewCard>;
}

function DistributionCard({ title, labels, empty = false }) {
  return <DashboardPreviewCard eyebrow="Current position" title={title} description="Verified evidence in the selected authorized scope.">
    {empty ? <EmptyState variant="inline" alignment="left" icon={Target} title="Evidence is still building" description="This compact card will fill when verified records arrive." className="m-4" /> : <div className="space-y-4 border-t px-4 py-5 sm:px-5">{labels.map((label, index) => <div key={label}>
      <div className="flex justify-between gap-4 text-xs"><span className="font-semibold">{label}</span><span className="text-muted-foreground">{[42, 31, 19][index] || 8}</span></div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-primary" style={{ width: `${[84, 62, 38][index] || 20}%` }} /></div>
    </div>)}</div>}
  </DashboardPreviewCard>;
}

function rows(prefix, max, options = {}) {
  return Array.from({ length: Math.min(scenarioCount, max) }, (_, index) => ({
    title: `${prefix} ${index + 1}${longCopy && index === 0 ? " with an extended cross-department context" : ""}`,
    detail: longCopy && index < 2 ? longCopy : options.detail || "Current verified details for this authorized record.",
    chips: options.chips ? options.chips[index] || options.chips[0] : undefined,
    href: "#authorized-record",
  }));
}

function CollegeFixture() {
  const restricted = scenario === "restricted";
  const attentionRows = rows("Student", 4, { chips: [["Low attendance", "Resume incomplete"], ["Active backlog"], ["Coding stale"], ["Eligibility review"]] });
  const cards = {
    attendance: restricted ? null : <DashboardPreviewCard key="attendance" eyebrow="Academic evidence" title="Attendance trend" description="Average attendance across the authorized student population."><SimpleTrend /></DashboardPreviewCard>,
    departments: <ListCard key="departments" eyebrow="Outcomes" title="Department outcomes" description="Readiness and placement outcomes without opaque ranking." rows={rows("Department", 4, { detail: "26 students / 86.9% attendance / 8 placed" })} icon={Buildings} total={scenarioCount ? 7 : 0} actionHref="/app/reports" />,
    attention: <ListCard key="attention" eyebrow="Support queue" title="Students needing attention" description="Academic and placement signals grouped by student." rows={attentionRows} total={scenarioCount ? 11 : 0} actionHref="/app/college?section=readiness" />,
    readiness: restricted ? null : <DistributionCard key="readiness" title="Readiness distribution" labels={["Ready", "Developing", "Needs support"]} empty={!scenarioCount} />,
    funnel: <DistributionCard key="funnel" title="Placement funnel" labels={["Eligible", "Applied", "Selected"]} empty={!scenarioCount} />,
    brief: <ListCard key="brief" eyebrow="Edvatiq intelligence" title="Placement brief" description="Evidence-backed priorities for this selected scope." rows={rows("Priority", 3)} icon={Sparkle} />,
    drives: <ListCard key="drives" eyebrow="Deadlines" title="Active drives" description="The next submission and drive milestones." rows={rows("Placement drive", 3, { detail: "Closes 25 Aug / verified eligible students" })} icon={CalendarCheck} total={scenarioCount ? 6 : 0} actionHref="/app/college?section=drives" />,
  };
  const layouts = {
    leadership: { primary: ["attendance", "departments", "attention"], supporting: ["readiness", "funnel", "brief", "drives"] },
    operations: { primary: ["attention", "drives", "funnel"], supporting: ["brief", "attendance", "readiness", "departments"] },
    academic_support: { primary: ["attention", "attendance", "departments"], supporting: ["brief", "readiness", "drives", "funnel"] },
    overview: { primary: ["attendance", "attention"], supporting: ["brief", "drives", "readiness", "funnel", "departments"] },
  };
  const layout = layouts[profile] || layouts.overview;
  return <FixtureShell title="College placement intelligence" description="A role-aware view of student readiness, support work, and placement outcomes." profile={profile} restricted={restricted}>
    <FixtureFilters />
    <MetricRibbon />
    <DashboardLanes primary={layout.primary.map((id) => cards[id]).filter(Boolean)} supporting={layout.supporting.map((id) => cards[id]).filter(Boolean)} />
  </FixtureShell>;
}

function BusinessFixture() {
  const restricted = scenario === "restricted";
  const analytics = [
    restricted ? null : <DashboardPreviewCard key="trend" eyebrow="Revenue" title="Collections trend" description="Captured payments across the selected period."><SimpleTrend business /></DashboardPreviewCard>,
    <DistributionCard key="mix" title="Payment mix" labels={["Paid", "Partial", "Outstanding"]} empty={!scenarioCount} />,
  ].filter(Boolean);
  const execution = [
    <ListCard key="work" eyebrow="Today" title="My work" description="Assigned operational work in priority order." rows={rows("Follow-up", 4)} icon={Briefcase} total={scenarioCount ? 9 : 0} actionHref="/app/calendar" />,
    <ListCard key="attention" eyebrow="Signals" title="Clients needing attention" description="Related signals stay compact rather than stretching adjacent cards." rows={rows("Client", 4, { chips: [["Renewal near"], ["Payment due"], ["Visit overdue"], ["Profile incomplete"]] })} total={scenarioCount ? 8 : 0} actionHref="/app/clients" />,
  ];
  const primary = profile === "leadership" ? analytics : execution;
  const supporting = profile === "leadership" ? execution : analytics;
  return <FixtureShell title="Business performance" description="Live operating context arranged for the work this role needs to do first." profile={profile} restricted={restricted}>
    <FixtureFilters business />
    <MetricRibbon business />
    <DashboardLanes primary={primary} supporting={supporting} />
  </FixtureShell>;
}

function FixtureShell({ title, description, profile: roleProfile, restricted, children }) {
  return <main data-testid="dashboard-fixture" className="min-h-screen bg-background px-4 py-5 text-foreground sm:px-6 lg:px-8">
    <PageShell>
      <DashboardCanvas data-dashboard-profile={roleProfile} data-scenario={scenario}>
        <DashboardBand as="header" className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div><div className="overline">Deterministic visual fixture / {roleProfile.replaceAll("_", " ")}</div><h1 className="mt-2 font-display text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">{title}</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p></div>
          <Button><Sparkle className="mr-2" />Ask Edvatiq</Button>
        </DashboardBand>
        {restricted && <DashboardBand as="div"><div role="note" className="flex gap-3 rounded-xl border bg-secondary/45 px-4 py-3 text-sm"><WarningCircle className="mt-0.5 shrink-0" /><span><strong>Some evidence is not included.</strong> Cards outside this role's authorized modules are omitted.</span></div></DashboardBand>}
        {children}
      </DashboardCanvas>
    </PageShell>
  </main>;
}

createRoot(document.getElementById("root")).render(kind === "business" ? <BusinessFixture /> : <CollegeFixture />);
