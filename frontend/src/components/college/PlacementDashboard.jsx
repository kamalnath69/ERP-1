import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight, Briefcase, Buildings, CalendarCheck, CheckCircle,
  GraduationCap, Sparkle, Student, Target, WarningCircle,
} from "@phosphor-icons/react";

import { assistantPreferences } from "@/components/ai/AssistantPersonalizationSheet";
import BusinessChart from "@/components/charts/BusinessChart";
import { EmptyState, ErrorState, PageShell, StatusBadge, Surface } from "@/components/system";
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

export default function PlacementDashboard({ embedded = false, onSection }) {
  const navigate = useNavigate();
  const { user, roles } = useAuth();
  const { context, organization } = useBusiness();
  const storageKey = `edvatiq.college.dashboard.filters.v1:${organization?.id || "workspace"}:${user?.id || "user"}`;
  const [filters, setFilters] = useState(() => restoreFilters(storageKey));

  useEffect(() => {
    try { window.localStorage.setItem(storageKey, JSON.stringify(filters)); } catch { /* Browsing can continue without persistence. */ }
  }, [filters, storageKey]);

  const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value && value !== "all"));
  const query = useGetCollegePlacementDashboardQuery(params);
  const data = query.data;
  const metricData = data?.metrics || {};
  const noStudents = !query.isLoading && metricData.participating_students === 0;
  const preferredName = assistantPreferences(context).preferred_name?.trim();
  const name = preferredName || user?.first_name || "there";
  const roleLine = placementRoleLine(roles);
  const Wrapper = embedded ? React.Fragment : PageShell;
  const wrapperProps = embedded ? {} : { className: "reveal pb-10" };

  if (query.isError && !data) {
    const error = <ErrorState title="Placement intelligence could not be loaded" description={query.error?.data?.detail} retry={query.refetch} />;
    return embedded ? error : <PageShell>{error}</PageShell>;
  }

  return <Wrapper {...wrapperProps}>
    <div className={cn("space-y-5", embedded && "px-4 py-5 sm:px-6 lg:px-8")}>
      <header className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="section-kicker">College placement intelligence</p>
          <h1 className="mt-1.5 text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">{timeGreeting()}, {name}.</h1>
          <p className="mt-2 text-sm text-muted-foreground sm:text-base">{roleLine}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => askAboutDashboard(navigate, data)}><Sparkle className="mr-2 text-accent" weight="fill" />Ask about this</Button>
          <Button onClick={() => navigate("/app/college")}><Briefcase className="mr-2" />Placement workspace</Button>
        </div>
      </header>

      <PlacementFilters filters={filters} setFilters={setFilters} data={data?.filters || {}} />

      {noStudents ? <EmptyState
        variant="page"
        alignment="left"
        icon={GraduationCap}
        title="Build the placement cohort"
        description="Bring students from your ERP or admit a student locally, then add the first academic or placement evidence."
        primaryAction={<Button onClick={() => navigate("/app/clients?new=1")}>Add a student</Button>}
        secondaryAction={<Button variant="outline" onClick={() => navigate("/app/college?section=integrations")}>Connect ERP</Button>}
      /> : <>
        <section className="grid gap-5 xl:grid-cols-12" aria-label="Placement position">
          <Surface className="overflow-hidden xl:col-span-4">
            <CompactHeading eyebrow="Today" title="Cohort position" />
            <div className="grid grid-cols-2 gap-px border-t bg-border">
              {metricDefinitions.map((definition) => <MetricCell key={definition.key} definition={definition} value={metricData[definition.key]} loading={query.isLoading} />)}
            </div>
          </Surface>
          <Surface className="overflow-hidden xl:col-span-4">
            <CompactHeading eyebrow="Readiness" title="Evidence distribution" copy={`${data?.coverage?.rankable || 0} of ${data?.coverage?.total || 0} students are rankable`} />
            <div className="px-2 pb-3">
              <BusinessChart data={data?.readiness_distribution || []} xKey="label" series={[{ key: "value", label: "Students" }]} type="donut" height={238} ariaLabel="Student readiness distribution" />
            </div>
          </Surface>
          <Surface className="overflow-hidden xl:col-span-4">
            <CompactHeading eyebrow="Recruitment" title="Placement funnel" copy={`${metricData.active_drives || 0} active drives / ${metricData.offers || 0} offers`} />
            <div className="px-3 pb-3">
              <BusinessChart data={(data?.placement_funnel || []).filter((row) => row.value > 0)} xKey="label" series={[{ key: "value", label: "Applications" }]} type="bar" height={238} ariaLabel="Placement application funnel" />
            </div>
          </Surface>
        </section>

        <section className="grid items-start gap-5 xl:grid-cols-12" aria-label="Placement evidence trends">
          <Surface className="overflow-hidden xl:col-span-7">
            <CompactHeading eyebrow="Academic evidence" title="Attendance and readiness trend" copy="Average attendance for the selected student scope." />
            <div className="px-3 pb-4 sm:px-5">
              <BusinessChart data={data?.attendance_trend || []} xKey="date" series={[{ key: "attendance", label: "Attendance %" }]} type="area" height={285} ariaLabel="Batch attendance trend" />
            </div>
          </Surface>
          <Surface className="overflow-hidden xl:col-span-5">
            <CompactHeading eyebrow="Outcomes" title="Department placement position" copy="Readiness and placements without an opaque rank." />
            <DepartmentTable rows={data?.department_comparison || []} />
          </Surface>
        </section>

        <section className="grid items-start gap-5 xl:grid-cols-12" aria-label="Placement priorities">
          <Surface className="overflow-hidden xl:col-span-4">
            <CompactHeading
              eyebrow="Deadlines"
              title="Active drives"
              copy="The next submission and drive milestones."
              action={<Button variant="ghost" size="sm" onClick={() => navigate("/app/college?section=drives")}>View all<ArrowRight /></Button>}
            />
            <DriveDeadlines rows={data?.active_drive_deadlines || []} navigate={navigate} />
          </Surface>
          <Surface className="overflow-hidden xl:col-span-4">
            <CompactHeading
              eyebrow="Support queue"
              title="Students needing attention"
              copy="Prioritized from current academic and placement evidence."
              action={<Button variant="ghost" size="sm" onClick={() => navigate("/app/college?section=readiness")}>Review<ArrowRight /></Button>}
            />
            <AttentionList rows={data?.attention || []} onOpen={(row) => navigate(`/app/clients/${row.client_id}`)} />
          </Surface>
          <Surface className="overflow-hidden xl:col-span-4">
            <CompactHeading eyebrow="Edvatiq intelligence" title="Placement brief" copy="Evidence-backed priorities for this selected scope." />
            <PlacementBrief rows={data?.brief || []} navigate={navigate} />
          </Surface>
        </section>
      </>}
    </div>
  </Wrapper>;
}

function PlacementFilters({ filters, setFilters, data }) {
  const change = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const programs = (data.programs || []).filter((row) => filters.department_id === "all" || row.department_id === filters.department_id);
  const cohorts = (data.cohorts || []).filter((row) => filters.program_id === "all" || row.program_id === filters.program_id);
  const academicYears = (data.academic_years || []).map((value) => ({ id: String(value), name: String(value) }));
  const graduationYears = (data.graduation_years || []).map((value) => ({ id: String(value), name: `Class of ${value}` }));
  return <div className="flex flex-col gap-2 rounded-xl border bg-card p-2 sm:flex-row sm:flex-wrap sm:items-center">
    <span className="px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Student scope</span>
    <FilterSelect value={filters.academic_year} onChange={(value) => change("academic_year", value)} placeholder="All academic years" rows={academicYears} />
    <FilterSelect value={filters.graduation_year} onChange={(value) => change("graduation_year", value)} placeholder="All graduation batches" rows={graduationYears} />
    <FilterSelect value={filters.department_id} onChange={(value) => setFilters((current) => ({ ...current, department_id: value, program_id: "all", cohort_id: "all" }))} placeholder="All departments" rows={data.departments || []} />
    <FilterSelect value={filters.program_id} onChange={(value) => setFilters((current) => ({ ...current, program_id: value, cohort_id: "all" }))} placeholder="All programs" rows={programs} />
    <FilterSelect value={filters.cohort_id} onChange={(value) => change("cohort_id", value)} placeholder="All cohorts" rows={cohorts} />
  </div>;
}

function FilterSelect({ value, onChange, placeholder, rows }) {
  return <Select value={value} onValueChange={onChange}>
    <SelectTrigger className="h-9 w-full border-0 bg-secondary/70 shadow-none sm:w-44"><SelectValue /></SelectTrigger>
    <SelectContent><SelectItem value="all">{placeholder}</SelectItem>{rows.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent>
  </Select>;
}

function CompactHeading({ eyebrow, title, copy, action }) {
  return <div className="flex min-h-[76px] items-start justify-between gap-3 px-4 py-4 sm:px-5">
    <div className="min-w-0"><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{eyebrow}</p><h2 className="mt-1 text-base font-semibold tracking-[-0.02em]">{title}</h2>{copy && <p className="mt-1 truncate text-xs text-muted-foreground">{copy}</p>}</div>
    {action}
  </div>;
}

function MetricCell({ definition, value, loading }) {
  const Icon = definition.icon;
  return <article className="min-h-[116px] bg-card p-4">
    <div className="flex items-start justify-between gap-2"><span className="text-xs font-semibold leading-5 text-muted-foreground">{definition.label}</span><span className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-secondary text-muted-foreground", definition.tone === "success" && "bg-success/10 text-success", definition.tone === "warning" && "bg-warning/10 text-warning", definition.tone === "accent" && "bg-primary/10 text-primary")}><Icon size={15} /></span></div>
    <div className="mt-3 text-3xl font-semibold tracking-[-0.05em]">{loading && value == null ? "-" : Number(value || 0).toLocaleString("en-IN")}</div>
  </article>;
}

function DepartmentTable({ rows }) {
  if (!rows.length) return <EmptyState variant="inline" icon={Buildings} title="No comparison yet" description="Department outcomes appear as evidence is synchronized." className="m-4" />;
  return <div className="divide-y border-t">{rows.slice(0, 6).map((row) => <div key={row.department_id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3.5 sm:px-5">
    <div className="min-w-0"><div className="truncate text-sm font-semibold">{row.department}</div><div className="mt-1 text-xs text-muted-foreground">{row.students} students / {row.attendance == null ? "Attendance pending" : `${row.attendance}% attendance`}</div></div>
    <div className="text-right"><div className="text-sm font-semibold">{row.placed} placed</div><div className="mt-1 text-xs text-muted-foreground">{row.ready} ready</div></div>
  </div>)}</div>;
}

function DriveDeadlines({ rows, navigate }) {
  if (!rows.length) return <EmptyState variant="inline" icon={CalendarCheck} title="No upcoming drive deadlines" description="New published drives will appear here." className="m-4" />;
  return <div className="divide-y border-t">{rows.slice(0, 5).map((row) => <button key={row.id} type="button" onClick={() => navigate(row.action_url)} className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-secondary/45 sm:px-5">
    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary text-muted-foreground"><CalendarCheck size={17} /></span>
    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.title}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{row.company} / {deadlineLabel(row)}</span></span>
    <span className="text-xs font-medium text-muted-foreground">{row.application_count}</span>
  </button>)}</div>;
}

function AttentionList({ rows, onOpen }) {
  if (!rows.length) return <EmptyState variant="inline" icon={CheckCircle} title="No urgent evidence gaps" description="The selected cohort has no current readiness warnings." className="m-4" />;
  return <div className="divide-y border-t">{rows.slice(0, 5).map((row, index) => <button key={`${row.student_id}:${row.reason}:${index}`} type="button" onClick={() => onOpen(row)} className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-secondary/45 sm:px-5">
    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold">{row.name?.slice(0, 1)}</span>
    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.name}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{row.reason}</span></span>
    {row.reason === "Low attendance" ? <StatusBadge status="warning" label={`${row.value}%`} /> : <ArrowRight className="shrink-0 text-muted-foreground" />}
  </button>)}</div>;
}

function PlacementBrief({ rows, navigate }) {
  if (!rows.length) return <EmptyState variant="inline" icon={CheckCircle} title="The selected scope is on track" description="Edvatiq found no high-priority placement exceptions." className="m-4" />;
  return <div className="divide-y border-t">{rows.map((row) => <article key={row.key} className="px-4 py-3.5 sm:px-5">
    <div className="flex items-start gap-3"><span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full bg-muted-foreground", row.tone === "warning" && "bg-warning", row.tone === "accent" && "bg-accent")} /><div className="min-w-0"><h3 className="text-sm font-semibold leading-5">{row.title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{row.detail}</p><button type="button" className="mt-2 text-xs font-semibold text-primary hover:underline" onClick={() => navigate(row.action_url)}>{row.action_label}<ArrowRight className="ml-1 inline" /></button></div></div>
  </article>)}</div>;
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

function placementRoleLine(roles = []) {
  const names = roles.map((role) => `${role.slug || ""} ${role.name || ""}`.toLowerCase()).join(" ");
  if (names.includes("principal") || names.includes("owner")) return "Here is the placement position across your institution and where leadership attention matters today.";
  if (names.includes("hod") || names.includes("department")) return "Here is where your department's placement cohort needs attention today.";
  if (names.includes("coordinator")) return "Here are the students, drives, and follow-ups that need your attention today.";
  return "Here is where your placement cohort needs attention today.";
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
