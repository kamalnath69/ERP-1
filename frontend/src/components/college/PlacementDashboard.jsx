import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight, Briefcase, Buildings, CalendarCheck, CheckCircle,
  GraduationCap, SlidersHorizontal, Sparkle, Student, Target, WarningCircle,
} from "@phosphor-icons/react";

import { assistantPreferences } from "@/components/ai/AssistantPersonalizationSheet";
import BusinessChart from "@/components/charts/BusinessChart";
import {
  DashboardBand, DashboardCanvas, DashboardLanes, DashboardPreviewCard,
  DashboardSkeleton, DrawerForm, EmptyState, ErrorState, PageShell, StatusBadge,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { useGetCollegePlacementDashboardQuery } from "@/features/college/collegeApi";
import { cn } from "@/lib/utils";

const metricDefinitions = [
  { key: "participating_students", label: "Students in scope", icon: Student },
  { key: "placement_ready", label: "Placement ready", icon: Target, tone: "success" },
  { key: "needs_support", label: "Needs support", icon: WarningCircle, tone: "warning" },
  { key: "placed_students", label: "Placed", icon: CheckCircle, tone: "accent" },
];

const DEFAULT_FILTERS = Object.freeze({
  academic_year: "all",
  graduation_year: "all",
  department_id: "all",
  program_id: "all",
  cohort_id: "all",
});

const PROFILE_LAYOUTS = Object.freeze({
  leadership: {
    primary: ["attendance", "departments", "attention"],
    supporting: ["readiness", "funnel", "brief", "drives"],
  },
  operations: {
    primary: ["attention", "drives", "funnel"],
    supporting: ["brief", "attendance", "readiness", "departments"],
  },
  academic_support: {
    primary: ["attention", "attendance", "departments"],
    supporting: ["brief", "readiness", "drives", "funnel"],
  },
  overview: {
    primary: ["attendance", "attention"],
    supporting: ["brief", "drives", "readiness", "funnel", "departments"],
  },
});

const LEADERSHIP_ROLES = new Set(["owner", "principal", "college-admin", "auditor"]);
const OPERATIONS_ROLES = new Set(["placement-head", "placement-coordinator", "college-manager"]);
const ACADEMIC_SUPPORT_ROLES = new Set(["hod", "class-advisor", "academic-admin", "faculty"]);

export default function PlacementDashboard({ embedded = false }) {
  const navigate = useNavigate();
  const { user, roles, permissions, accessContext } = useAuth();
  const { context, organization } = useBusiness();
  const accessVersion = accessContext?.access_version || 0;
  const storageKey = collegeDashboardFilterStorageKey(organization?.id, user?.id, accessVersion);
  const [filterState, setFilterState] = useState(() => ({ key: storageKey, values: restoreFilters(storageKey) }));
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const filters = dashboardFiltersForAccess(filterState, storageKey);

  useEffect(() => {
    setFilterState((current) => current.key === storageKey
      ? current
      : { key: storageKey, values: restoreFilters(storageKey) });
  }, [storageKey]);

  useEffect(() => {
    if (filterState.key !== storageKey) return;
    try { window.localStorage.setItem(storageKey, JSON.stringify(filterState.values)); } catch { /* Browsing can continue without persistence. */ }
  }, [filterState, storageKey]);

  const setFilters = (update) => setFilterState((current) => {
    const previous = current.key === storageKey ? current.values : DEFAULT_FILTERS;
    const values = typeof update === "function" ? update(previous) : update;
    return { key: storageKey, values };
  });

  const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value && value !== "all"));
  const query = useGetCollegePlacementDashboardQuery(params);
  const data = query.data;
  const metricData = data?.metrics || {};
  const noStudents = !query.isLoading && Number(data?.coverage?.total || 0) === 0;
  const preferredName = assistantPreferences(context).preferred_name?.trim();
  const name = preferredName || user?.first_name || "there";
  const profile = resolveCollegeDashboardProfile(roles, permissions);
  const capabilities = resolveCapabilities(data);
  const roleLine = placementRoleLine(profile, data?.access?.scope === "restricted");

  if (query.isLoading && !data) return <DashboardSkeleton embedded={embedded} className={embedded ? "px-4 py-5 sm:px-6 lg:px-8" : undefined} />;
  if (query.isError && !data) {
    const error = <ErrorState title="Placement intelligence could not be loaded" description={query.error?.data?.detail} retry={query.refetch} />;
    return embedded ? error : <PageShell>{error}</PageShell>;
  }

  const totals = {
    attention_students: data?.totals?.attention_students ?? groupAttentionRows(data?.attention).length,
    upcoming_drive_deadlines: data?.totals?.upcoming_drive_deadlines ?? data?.active_drive_deadlines?.length ?? 0,
    departments: data?.totals?.departments ?? data?.department_comparison?.length ?? 0,
  };
  const cards = buildCards({ data, metricData, totals, capabilities, navigate });
  const layout = collegeDashboardLayout(profile);
  const primary = layout.primary.map((id) => cards[id]).filter(Boolean);
  const supporting = layout.supporting.map((id) => cards[id]).filter(Boolean);
  const unavailable = unavailableCapabilityLabels(capabilities);

  const content = <DashboardCanvas className={cn(embedded && "px-4 py-5 sm:px-6 lg:px-8")} data-dashboard-profile={profile}>
    <DashboardBand as="header" className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <p className="section-kicker">College placement intelligence</p>
        <h1 className="mt-1.5 text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">{timeGreeting()}, {name}.</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground sm:text-base">{roleLine}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {query.isFetching && data && <span className="mr-1 text-xs text-muted-foreground" role="status">Updating dashboard...</span>}
        <Button variant="outline" onClick={() => askAboutDashboard(navigate, data)}><Sparkle className="mr-2 text-accent" weight="fill" />Ask about this</Button>
        <Button onClick={() => navigate("/app/college")}><Briefcase className="mr-2" />Placement workspace</Button>
      </div>
    </DashboardBand>

    <DashboardBand>
      <PlacementFilters
        filters={filters}
        setFilters={setFilters}
        data={data?.filters || {}}
        open={mobileFiltersOpen}
        onOpenChange={setMobileFiltersOpen}
      />
    </DashboardBand>

    {!!unavailable.length && <DashboardBand>
      <div className="flex items-start gap-3 rounded-xl border bg-surface-subtle/55 px-4 py-3 text-sm" role="note">
        <WarningCircle className="mt-0.5 shrink-0 text-muted-foreground" />
        <p><span className="font-semibold">Some evidence is not included.</span> {unavailable.join(", ")} data is outside your current access, so dependent cards are omitted rather than shown as empty.</p>
      </div>
    </DashboardBand>}

    {noStudents ? <EmptyState
      variant="page"
      alignment="left"
      icon={GraduationCap}
      title="Build the placement cohort"
      description="Bring students from your ERP or admit a student locally, then add the first academic or placement evidence."
      primaryAction={<Button onClick={() => navigate("/app/clients?new=1")}>Add a student</Button>}
      secondaryAction={<Button variant="outline" onClick={() => navigate("/app/academics?section=integrations")}>Connect ERP</Button>}
    /> : <>
      <DashboardBand className="surface-card overflow-hidden" aria-label="Placement position">
        <div className="dashboard-metric-grid gap-px bg-border">
          {metricDefinitions.map((definition) => <MetricCell key={definition.key} definition={definition} value={metricData[definition.key]} loading={query.isLoading} />)}
        </div>
      </DashboardBand>
      <DashboardLanes primary={primary} supporting={supporting} aria-label="Placement dashboard panels" />
    </>}
  </DashboardCanvas>;

  return embedded ? content : <PageShell className="reveal pb-10">{content}</PageShell>;
}

function buildCards({ data, metricData, totals, capabilities, navigate }) {
  return {
    attendance: capabilities.attendance ? <AttendanceCard key="attendance" rows={data?.attendance_trend || []} /> : null,
    departments: <DepartmentCard key="departments" rows={data?.department_comparison || []} total={totals.departments} navigate={navigate} />,
    attention: <AttentionCard key="attention" rows={data?.attention || []} total={totals.attention_students} navigate={navigate} />,
    readiness: capabilities.readiness ? <ReadinessCard key="readiness" rows={data?.readiness_distribution || []} coverage={data?.coverage} /> : null,
    funnel: capabilities.placements ? <FunnelCard key="funnel" rows={data?.placement_funnel || []} metrics={metricData} /> : null,
    brief: capabilities.readiness && capabilities.placements ? <BriefCard key="brief" rows={data?.brief || []} navigate={navigate} /> : null,
    drives: capabilities.placements ? <DrivesCard key="drives" rows={data?.active_drive_deadlines || []} total={totals.upcoming_drive_deadlines} navigate={navigate} /> : null,
  };
}

function PlacementFilters({ filters, setFilters, data, open, onOpenChange }) {
  const programs = (data.programs || []).filter((row) => filters.department_id === "all" || row.department_id === filters.department_id);
  const cohorts = (data.cohorts || []).filter((row) => filters.program_id === "all" || row.program_id === filters.program_id);
  const academicYears = (data.academic_years || []).map((value) => ({ id: String(value), name: String(value) }));
  const graduationYears = (data.graduation_years || []).map((value) => ({ id: String(value), name: `Class of ${value}` }));
  const rows = { academicYears, graduationYears, programs, cohorts };
  const summary = filterSummary(filters, data, rows);
  const activeCount = Object.values(filters).filter((value) => value && value !== "all").length;

  return <>
    <div className="dashboard-filter-compact surface-card w-full items-center justify-between gap-3 p-3">
      <div className="min-w-0"><div className="overline">Student scope</div><div className="mt-1 truncate text-sm font-semibold">{summary}</div></div>
      <Button type="button" variant="outline" className="shrink-0" onClick={() => onOpenChange(true)}>
        <SlidersHorizontal className="mr-2" />Filters{activeCount > 0 && <span className="ml-2 rounded-full bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground">{activeCount}</span>}
      </Button>
    </div>
    <div
      className="dashboard-filter-expanded surface-card gap-3 p-3"
      style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 10.5rem), 1fr))" }}
    >
      <div className="col-span-full flex items-center justify-between gap-3 px-1"><span className="overline">Student scope</span>{activeCount > 0 && <button type="button" className="text-xs font-semibold text-primary hover:underline" onClick={() => setFilters({ ...DEFAULT_FILTERS })}>Clear filters</button>}</div>
      <FilterFields filters={filters} setFilters={setFilters} data={data} rows={rows} />
    </div>
    <DrawerForm open={open} onOpenChange={onOpenChange} title="Student scope" description="Choose the population used by every metric and dashboard card.">
      <div className="space-y-4"><FilterFields filters={filters} setFilters={setFilters} data={data} rows={rows} drawer /></div>
      <div className="mt-6 flex items-center justify-between gap-3 border-t pt-4">
        <Button variant="ghost" onClick={() => setFilters({ ...DEFAULT_FILTERS })}>Clear all</Button>
        <Button onClick={() => onOpenChange(false)}>Apply filters</Button>
      </div>
    </DrawerForm>
  </>;
}

function FilterFields({ filters, setFilters, data, rows, drawer = false }) {
  const change = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  return <>
    <FilterSelect id={`academic-year-${drawer ? "drawer" : "inline"}`} label="Academic year" value={filters.academic_year} onChange={(value) => change("academic_year", value)} placeholder="All academic years" rows={rows.academicYears} />
    <FilterSelect id={`graduation-year-${drawer ? "drawer" : "inline"}`} label="Graduation batch" value={filters.graduation_year} onChange={(value) => change("graduation_year", value)} placeholder="All graduation batches" rows={rows.graduationYears} />
    <FilterSelect id={`department-${drawer ? "drawer" : "inline"}`} label="Department" value={filters.department_id} onChange={(value) => setFilters((current) => ({ ...current, department_id: value, program_id: "all", cohort_id: "all" }))} placeholder="All departments" rows={data.departments || []} />
    <FilterSelect id={`program-${drawer ? "drawer" : "inline"}`} label="Program" value={filters.program_id} onChange={(value) => setFilters((current) => ({ ...current, program_id: value, cohort_id: "all" }))} placeholder="All programs" rows={rows.programs} />
    <FilterSelect id={`cohort-${drawer ? "drawer" : "inline"}`} label="Cohort" value={filters.cohort_id} onChange={(value) => change("cohort_id", value)} placeholder="All cohorts" rows={rows.cohorts} />
  </>;
}

function FilterSelect({ id, label, value, onChange, placeholder, rows }) {
  return <div className="min-w-0">
    <label htmlFor={id} className="mb-1.5 block px-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{label}</label>
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} aria-label={label} className="h-10 w-full border-0 bg-secondary/70 shadow-none"><SelectValue /></SelectTrigger>
      <SelectContent><SelectItem value="all">{placeholder}</SelectItem>{rows.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent>
    </Select>
  </div>;
}

function MetricCell({ definition, value, loading }) {
  const Icon = definition.icon;
  return <article className="min-h-28 bg-card p-4 sm:p-5">
    <div className="flex items-start justify-between gap-2"><span className="text-xs font-semibold leading-5 text-muted-foreground">{definition.label}</span><span className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-secondary text-muted-foreground", definition.tone === "success" && "bg-success/10 text-success", definition.tone === "warning" && "bg-warning/10 text-warning", definition.tone === "accent" && "bg-primary/10 text-primary")}><Icon size={15} /></span></div>
    <div className="mt-3 font-display text-3xl font-semibold tracking-[-0.05em]">{loading && value == null ? "-" : Number(value || 0).toLocaleString("en-IN")}</div>
  </article>;
}

function AttendanceCard({ rows }) {
  return <DashboardPreviewCard eyebrow="Academic evidence" title="Attendance trend" description="Average attendance across the currently authorized student scope.">
    <ChartContent rows={rows} icon={GraduationCap} emptyTitle="No attendance trend yet" emptyDescription="Attendance history will appear after snapshots are synchronized.">
      <BusinessChart data={rows} xKey="date" series={[{ key: "attendance", label: "Attendance %" }]} type="area" height="clamp(14rem, 54cqi, 18rem)" ariaLabel="Batch attendance trend" />
    </ChartContent>
  </DashboardPreviewCard>;
}

function ReadinessCard({ rows, coverage }) {
  return <DashboardPreviewCard eyebrow="Readiness" title="Evidence distribution" description={`${coverage?.rankable || 0} of ${coverage?.total || 0} students have enough evidence for readiness comparison.`}>
    <ChartContent rows={rows} icon={Target} emptyTitle="No readiness evidence yet" emptyDescription="Verified readiness evidence will build this distribution.">
      <BusinessChart data={rows} xKey="label" series={[{ key: "value", label: "Students" }]} type="donut" height="clamp(14rem, 54cqi, 18rem)" ariaLabel="Student readiness distribution" />
    </ChartContent>
  </DashboardPreviewCard>;
}

function FunnelCard({ rows, metrics }) {
  const populated = rows.filter((row) => Number(row.value || 0) > 0);
  return <DashboardPreviewCard eyebrow="Recruitment" title="Placement funnel" description={`${metrics.active_drives || 0} active drives and ${metrics.offers || 0} recorded offers.`}>
    <ChartContent rows={populated} icon={Briefcase} emptyTitle="No active placement funnel" emptyDescription="Applications will appear as students enter placement drives.">
      <BusinessChart data={populated} xKey="label" series={[{ key: "value", label: "Applications" }]} type="bar" height="clamp(14rem, 54cqi, 18rem)" ariaLabel="Placement application funnel" />
    </ChartContent>
  </DashboardPreviewCard>;
}

function ChartContent({ rows, children, icon, emptyTitle, emptyDescription }) {
  return <div className="border-t px-3 pb-4 pt-2 sm:px-5">{rows.length ? children : <EmptyState variant="inline" icon={icon} title={emptyTitle} description={emptyDescription} className="my-2 border-0 bg-transparent" />}</div>;
}

function DepartmentCard({ rows, total, navigate }) {
  const preview = rows.slice(0, 4);
  return <DashboardPreviewCard
    eyebrow="Outcomes"
    title={total === 1 ? "Department position" : "Department outcomes"}
    description="Readiness and placement outcomes without an opaque rank."
    footer={total > preview.length ? <PreviewFooter shown={preview.length} total={total} label="departments" onClick={() => navigate("/app/reports")} /> : null}
  >
    <DepartmentList rows={preview} />
  </DashboardPreviewCard>;
}

function DepartmentList({ rows }) {
  if (!rows.length) return <EmptyState variant="inline" icon={Buildings} title="No department comparison yet" description="Department outcomes appear as evidence is synchronized." className="m-4" />;
  return <div className="divide-y border-t">{rows.map((row) => <div key={row.department_id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3.5 sm:px-5">
    <div className="min-w-0"><div className="truncate text-sm font-semibold">{row.department}</div><div className="mt-1 text-xs leading-5 text-muted-foreground">{row.students} students / {row.attendance == null ? "Attendance pending" : `${row.attendance}% attendance`}</div></div>
    <div className="text-right"><div className="text-sm font-semibold">{row.placed} placed</div><div className="mt-1 text-xs text-muted-foreground">{row.ready} ready</div></div>
  </div>)}</div>;
}

function DrivesCard({ rows, total, navigate }) {
  const preview = rows.slice(0, 3);
  return <DashboardPreviewCard
    eyebrow="Deadlines"
    title="Active drives"
    description="The next submission and drive milestones."
    footer={total > preview.length ? <PreviewFooter shown={preview.length} total={total} label="drives" onClick={() => navigate("/app/college?section=drives")} /> : null}
  >
    <DriveDeadlines rows={preview} navigate={navigate} />
  </DashboardPreviewCard>;
}

function DriveDeadlines({ rows, navigate }) {
  if (!rows.length) return <EmptyState variant="inline" icon={CalendarCheck} title="No upcoming drive deadlines" description="New published drives will appear here." className="m-4" />;
  return <div className="divide-y border-t">{rows.map((row) => {
    const Row = row.action_url ? "button" : "div";
    return <Row key={row.id} type={row.action_url ? "button" : undefined} onClick={row.action_url ? () => navigate(row.action_url) : undefined} className={cn("flex min-h-16 w-full items-center gap-3 px-4 py-3.5 text-left sm:px-5", row.action_url && "transition-colors hover:bg-secondary/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring")}>
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary text-muted-foreground"><CalendarCheck size={17} /></span>
      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.title}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{row.company} / {deadlineLabel(row)}</span></span>
      <span className="shrink-0 text-xs font-medium text-muted-foreground">{row.application_count}</span>
    </Row>;
  })}</div>;
}

export function AttentionCard({ rows, total, navigate }) {
  const grouped = useMemo(() => groupAttentionRows(rows), [rows]);
  const preview = grouped.slice(0, 4);
  return <DashboardPreviewCard
    eyebrow="Support queue"
    title="Students needing attention"
    description="Current academic and placement signals, grouped by student."
    footer={total > preview.length ? <PreviewFooter shown={preview.length} total={total} label="students" onClick={() => navigate("/app/college?section=readiness")} /> : null}
  >
    <AttentionList rows={preview} navigate={navigate} />
  </DashboardPreviewCard>;
}

function AttentionList({ rows, navigate }) {
  if (!rows.length) return <EmptyState variant="inline" icon={CheckCircle} title="No urgent evidence gaps" description="The selected cohort has no current readiness warnings." className="m-4" />;
  return <div className="divide-y border-t">{rows.map((row) => {
    const Row = row.client_id ? "button" : "div";
    return <Row key={row.key} type={row.client_id ? "button" : undefined} onClick={row.client_id ? () => navigate(`/app/clients/${row.client_id}`) : undefined} className={cn("flex min-h-20 w-full items-start gap-3 px-4 py-3.5 text-left sm:px-5", row.client_id && "transition-colors hover:bg-secondary/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring")}>
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold">{row.name?.slice(0, 1)}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{row.name}</span>
        {row.admission_number && <span className="mt-0.5 block text-[10px] font-medium text-muted-foreground">{row.admission_number}</span>}
        <span className="mt-2 flex flex-wrap gap-1.5">{row.issues.slice(0, 2).map((issue) => <span key={issue.reason} className="rounded-full border bg-secondary/65 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">{issue.reason}</span>)}{row.issues.length > 2 && <span className="rounded-full border px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">+{row.issues.length - 2}</span>}</span>
      </span>
      {row.lowAttendance != null ? <StatusBadge status="warning" label={`${row.lowAttendance}%`} /> : row.client_id ? <ArrowRight className="mt-2 shrink-0 text-muted-foreground" /> : null}
    </Row>;
  })}</div>;
}

function BriefCard({ rows, navigate }) {
  return <DashboardPreviewCard eyebrow="Edvatiq intelligence" title="Placement brief" description="Evidence-backed priorities for this selected scope.">
    <PlacementBrief rows={rows.slice(0, 3)} navigate={navigate} />
  </DashboardPreviewCard>;
}

function PlacementBrief({ rows, navigate }) {
  if (!rows.length) return <EmptyState variant="inline" icon={CheckCircle} title="The selected scope is on track" description="Edvatiq found no high-priority placement exceptions." className="m-4" />;
  return <div className="divide-y border-t">{rows.map((row) => <article key={row.key} className="px-4 py-3.5 sm:px-5">
    <div className="flex items-start gap-3"><span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full bg-muted-foreground", row.tone === "warning" && "bg-warning", row.tone === "accent" && "bg-accent")} /><div className="min-w-0"><h3 className="text-sm font-semibold leading-5">{row.title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{row.detail}</p>{row.action_url && <button type="button" className="mt-2 inline-flex items-center text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => navigate(row.action_url)}>{row.action_label}<ArrowRight className="ml-1" /></button>}</div></div>
  </article>)}</div>;
}

function PreviewFooter({ shown, total, label, onClick }) {
  if (!onClick || total <= shown) return null;
  return <><span className="text-xs text-muted-foreground">Showing {shown} of {total}</span><Button variant="ghost" size="sm" onClick={onClick}>View all {label}<ArrowRight /></Button></>;
}

export function groupAttentionRows(rows = []) {
  const groups = new Map();
  (rows || []).forEach((row, index) => {
    const key = row.student_id || row.client_id || `${row.name || "student"}:${index}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        student_id: row.student_id,
        client_id: row.client_id,
        name: row.name || "Student",
        admission_number: row.admission_number,
        issues: [],
        lowAttendance: null,
      });
    }
    const group = groups.get(key);
    if (row.reason && !group.issues.some((issue) => issue.reason === row.reason)) group.issues.push({ reason: row.reason, value: row.value });
    if (row.reason === "Low attendance" && row.value != null) group.lowAttendance = row.value;
  });
  return [...groups.values()];
}

export function resolveCollegeDashboardProfile(roles = [], permissions = []) {
  const normalizeRole = (role) => String(role || "").trim().toLowerCase().replaceAll("_", "-").replaceAll(" ", "-");
  const roleKeys = new Set(roles.flatMap((role) => typeof role === "string"
    ? [normalizeRole(role)]
    : [normalizeRole(role?.system_key), normalizeRole(role?.slug)]).filter(Boolean));
  if ([...roleKeys].some((role) => LEADERSHIP_ROLES.has(role))) return "leadership";
  if ([...roleKeys].some((role) => OPERATIONS_ROLES.has(role))) return "operations";
  if ([...roleKeys].some((role) => ACADEMIC_SUPPORT_ROLES.has(role))) return "academic_support";
  const permissionSet = new Set(permissions || []);
  if (permissionSet.has("college.applications.manage") || permissionSet.has("college.opportunities.manage")) return "operations";
  if (permissionSet.has("college.attendance.mark") || permissionSet.has("college.assessments.record")) return "academic_support";
  return "overview";
}

export function collegeDashboardLayout(profile) {
  return PROFILE_LAYOUTS[profile] || PROFILE_LAYOUTS.overview;
}

export function collegeDashboardFilterStorageKey(organizationId, userId, accessVersion) {
  return `edvatiq.college.dashboard.filters:${organizationId || "workspace"}:${userId || "user"}:${accessVersion || 0}`;
}

export function dashboardFiltersForAccess(filterState, storageKey) {
  return filterState?.key === storageKey ? filterState.values : DEFAULT_FILTERS;
}

function resolveCapabilities(data) {
  const supplied = data?.access?.capabilities || {};
  return {
    attendance: supplied.attendance ?? true,
    assessments: supplied.assessments ?? true,
    coding: supplied.coding ?? true,
    readiness: supplied.readiness ?? true,
    placements: supplied.placements ?? true,
  };
}

function unavailableCapabilityLabels(capabilities) {
  const labels = { attendance: "Attendance", assessments: "Assessment", coding: "Coding", readiness: "Readiness", placements: "Placement" };
  return Object.entries(capabilities).filter(([, available]) => !available).map(([key]) => labels[key]);
}

function filterSummary(filters, data, rows) {
  const selected = [];
  const find = (collection, id) => collection.find((row) => String(row.id) === String(id))?.name;
  if (filters.academic_year !== "all") selected.push(find(rows.academicYears, filters.academic_year) || filters.academic_year);
  if (filters.graduation_year !== "all") selected.push(find(rows.graduationYears, filters.graduation_year) || `Class of ${filters.graduation_year}`);
  if (filters.department_id !== "all") selected.push(find(data.departments || [], filters.department_id));
  if (filters.program_id !== "all") selected.push(find(data.programs || [], filters.program_id));
  if (filters.cohort_id !== "all") selected.push(find(data.cohorts || [], filters.cohort_id));
  return selected.filter(Boolean).join(" / ") || "All authorized students";
}

function restoreFilters(key) {
  try { return { ...DEFAULT_FILTERS, ...JSON.parse(window.localStorage.getItem(key) || "{}") }; } catch { return { ...DEFAULT_FILTERS }; }
}

function timeGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function placementRoleLine(profile, restricted) {
  const copy = {
    leadership: "Here is the placement position across the institution and where leadership attention matters today.",
    operations: "Here are the students, drives, and follow-ups that need placement-team attention today.",
    academic_support: "Here is where the students in your academic responsibility need support today.",
    overview: "Here is the current placement position and the next work that needs attention.",
  }[profile];
  return restricted ? `${copy} Every result is limited to your authorized student scope.` : copy;
}

function deadlineLabel(row) {
  const value = row.deadline_at || row.drive_at;
  if (!value) return "Schedule pending";
  return `${row.deadline_at ? "Closes" : "Drive"} ${new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(value))}`;
}

function askAboutDashboard(navigate, data) {
  const prompt = data?.brief?.length
    ? `Explain these placement priorities and show the supporting records: ${data.brief.map((row) => row.title).join("; ")}`
    : "Summarize this placement cohort using current readiness, academic evidence, drives, and application outcomes.";
  navigate(`/app/ai?ask=${encodeURIComponent(prompt)}`);
}
