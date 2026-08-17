import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  ArrowClockwise, ArrowRight, Books, Briefcase, Buildings, CalendarCheck,
  ChartBar, CheckCircle, Code, Copy, Database, FileArrowUp, Funnel, GraduationCap,
  Key, ListChecks, MagnifyingGlass, Medal, Plus, ShieldCheck, Sparkle, Student,
  Target, Trash, UsersThree, WarningCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import SecondarySidebarLayout, {
  SecondarySidebarGroup, SecondarySidebarHeader, SecondarySidebarItem,
  SecondarySidebarNav, SecondarySidebarTrigger,
} from "@/components/layout/SecondarySidebarLayout";
import { useRegisterAIPageContext } from "@/components/ai/AIConversationProvider";
import BusinessChart from "@/components/charts/BusinessChart";
import AcademicStructurePanel from "@/components/college/AcademicStructurePanel";
import AcademicResourceCombobox from "@/components/college/AcademicResourceCombobox";
import AssessmentPatternsPanel from "@/components/college/AssessmentPatternsPanel";
import DataExchangePanel from "@/components/college/DataExchangePanel";
import { ValidatedActionDialog } from "@/components/forms/ValidatedActionDialog";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar,
  SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import {
  useCreateCollegeApplicationMutation, useCreateCollegeAttendanceMutation,
  useCreateCollegeCompanyMutation, useCreateCollegeIntegrationCredentialMutation,
  useCreateCollegeIntegrationMutation,
  useCreateCollegeOpportunityMutation, useGetCollegeAcademicEvidencePageQuery,
  useGetCollegeAcademicHierarchyQuery, useGetCollegeAcademicSummaryQuery,
  useGetCollegeApplicationsQuery, useGetCollegeAssessmentRegisterQuery,
  useGetCollegeAssessmentSchemesPageQuery,
  useGetCollegeAssessmentsPageQuery, useGetCollegeAttendanceRegisterQuery,
  useGetCollegeAttendanceSessionsPageQuery,
  useGetCollegeCohortsPageQuery, useGetCollegeOfferingsPageQuery,
  useGetCollegeCompaniesQuery,
  useGetCollegeIntegrationCredentialsQuery, useGetCollegeIntegrationsQuery,
  useGetCollegeInternshipClearancePageQuery,
  useGetCollegeLeaderboardsQuery, useGetCollegeOpportunitiesQuery,
  useGetCollegePipelineStagesQuery, useGetCollegeReadinessPolicyQuery,
  useGetCollegeStudentIntelligenceQuery,
  useMoveCollegeApplicationStageMutation,
  useQueueCollegeIntegrationSyncMutation, useRevokeCollegeIntegrationCredentialMutation,
  useRotateCollegeIntegrationCredentialMutation, useSaveCollegeAttendanceMutation,
  useCreateCollegeExamCycleMutation,
  useSaveCollegeScoresMutation,
  useUpdateCollegeIntegrationMutation,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import { PermissionDeniedPage } from "@/pages/SystemPages";
import {
  applyApiErrors, attendanceRecordSchema, attendanceSessionSchema,
  collegeApplicationSchema, collegeConnectorSchema,
  collegeDriveSchema, collegePushCredentialSchema,
  companySchema, FORM_OPTIONS, normalizeApiError,
} from "@/lib/validation";


const PLACEMENT_NAVIGATION = [
  { label: "Placement", items: [
    { id: "pipeline", label: "Pipeline", icon: Funnel, domain: "placements", permission: "college.placements.view" },
    { id: "drives", label: "Drives", icon: Briefcase, domain: "placements", permission: "college.placements.view" },
    { id: "applications", label: "Applications", icon: ListChecks, domain: "placements", permission: "college.placements.view" },
    { id: "companies", label: "Companies", icon: Buildings, domain: "placements", permission: "college.placements.view" },
  ] },
  { label: "Intelligence", items: [
    { id: "readiness", label: "Readiness & support", icon: Target, domain: "readiness", permission: "college.readiness.view" },
    { id: "coding", label: "Coding", icon: Code, domain: "coding", permission: "college.coding.view" },
    { id: "leaderboards", label: "Leaderboards", icon: Medal, domain: "readiness", permission: "college.readiness.view" },
  ] },
  { label: "Administration", items: [
    { id: "policy", label: "Readiness policy", icon: ShieldCheck, domain: "readiness", permission: "college.readiness.view" },
    { id: "clearance", label: "Internship clearance", icon: CheckCircle, domain: "clearance", permission: "college.clearance.view" },
  ] },
];

const ACADEMICS_NAVIGATION = [
  { label: "Academics", items: [
    { id: "overview", label: "Overview", icon: ChartBar, domains: ["academics", "attendance", "assessments", "data"], permissions: ["college.academics.view", "college.academics.manage", "college.attendance.view", "college.attendance.mark", "college.assessments.view", "college.assessments.record", "college.assessments.manage", "college.data.view", "college.imports.manage", "college.integrations.manage"] },
    { id: "structure", label: "Academic structure", icon: Buildings, domain: "academics", permission: "college.academics.view" },
    { id: "attendance", label: "Attendance", icon: CalendarCheck, domain: "attendance", permissions: ["college.attendance.view", "college.attendance.mark"] },
    { id: "results", label: "Results & evidence", icon: Books, domain: "assessments", permissions: ["college.assessments.view", "college.assessments.record", "college.assessments.manage"] },
    { id: "assessments", label: "Assessments", icon: GraduationCap, domain: "assessments", permissions: ["college.assessments.view", "college.assessments.record", "college.assessments.manage"] },
  ] },
  { label: "Data operations", items: [
    { id: "integrations", label: "ERP synchronization", icon: Database, domain: "data", permission: "college.integrations.manage" },
    { id: "exchange", label: "Data exchange", icon: FileArrowUp, domain: "data", permissions: ["college.data.view", "college.imports.manage"] },
  ] },
];

const SECTION_COPY = {
  pipeline: ["Placement pipeline", "Move every application forward with a clear, auditable next step."],
  drives: ["Placement drives", "Manage opportunities, deadlines, eligibility, and campus activity."],
  applications: ["Applications", "Review student progress across every active opportunity."],
  companies: ["Recruiting companies", "Maintain the employer relationships behind campus opportunities."],
  readiness: ["Readiness & support", "Find students who are ready, developing, or missing critical evidence."],
  coding: ["Coding intelligence", "Track verified problem-solving progress without making it the only success signal."],
  leaderboards: ["Evidence leaderboards", "Compare achievement and improvement with transparent evidence coverage."],
  overview: ["Academic overview", "Review the current academic period, evidence coverage, and work needing attention."],
  structure: ["Academic structure", "Manage the live departments, programs, graduation batches, terms, courses, and offerings used across College."],
  attendance: ["Attendance evidence", "Review imported history or record a local session when the ERP is unavailable."],
  results: ["Results & evidence", "Review verified term results, CGPA, backlogs, and publication coverage."],
  assessments: ["Assessment cycles", "Run academic, coding, aptitude, and placement evaluations from your College's configured patterns."],
  integrations: ["ERP synchronization", "Keep authoritative student and academic records connected through audited read-only pulls."],
  exchange: ["Data exchange", "Use college-aware manual, Excel, CSV, ERP pull, and API push schemas with review before commit."],
  policy: ["Readiness policy", "Understand how evidence is weighted and when a student becomes rankable."],
  clearance: ["Internship clearance", "Review only the clearance signal required for internship eligibility."],
};

const PLACEMENT_ALIASES = { placements: "pipeline", fees: "clearance" };
const ACADEMIC_ALIASES = { academics: "results", evidence: "results", imports: "exchange", batches: "structure", academics_structure: "structure" };
const ACADEMIC_LEGACY_SECTIONS = new Set(["academics", "evidence", "imports", "batches", "academics_structure", "structure", "attendance", "results", "assessments", "integrations", "exchange"]);
const ACADEMIC_SCOPE_KEYS = ["academic_year_id", "term_id", "department_id", "program_id", "cohort_id"];

function academicScopeParams(params) {
  const next = new URLSearchParams();
  ACADEMIC_SCOPE_KEYS.forEach((key) => {
    const value = params.get(key);
    if (value) next.set(key, value);
  });
  return next;
}

function academicScopeValues(params) {
  return {
    academicYearId: params.get("academic_year_id") || "",
    termId: params.get("term_id") || "",
    departmentId: params.get("department_id") || "",
    programId: params.get("program_id") || "",
    cohortId: params.get("cohort_id") || "",
  };
}

function permitted(item, can, accessContext) {
  const domains = item.domains || (item.domain ? [item.domain] : []);
  if (domains.length && accessContext?.domain_levels && !domains.some((domain) => {
    const level = accessContext.domain_levels[domain];
    return Boolean(level && level !== "none");
  })) return false;
  const permissions = item.permissions || (item.permission ? [item.permission, item.permission.replace(".view", ".manage")] : []);
  return !permissions.length || permissions.some((permission) => can(permission));
}

function academicRedirect(params, requested) {
  if (!ACADEMIC_LEGACY_SECTIONS.has(requested)) return null;
  const next = new URLSearchParams(params);
  let section = ACADEMIC_ALIASES[requested] || requested;
  if (section === "structure" && next.get("tab") === "assessment-patterns") {
    section = "assessments";
    next.delete("tab");
    next.set("view", "patterns");
  }
  if (section === "overview") next.delete("section"); else next.set("section", section);
  return `/app/academics${next.toString() ? `?${next}` : ""}`;
}

export default function CollegeWorkspace({ workspace = "placement" }) {
  const { can, accessContext } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const academics = workspace === "academics";
  const defaultSection = academics ? "overview" : "pipeline";
  const requested = params.get("section") || defaultSection;
  const redirectTo = !academics && requested === "overview" ? "/app"
    : !academics && requested === "students" ? `/app/clients${params.get("new") ? "?new=1" : ""}`
      : !academics ? academicRedirect(params, requested) : null;

  const navigationConfig = academics ? ACADEMICS_NAVIGATION : PLACEMENT_NAVIGATION;
  const aliases = academics ? ACADEMIC_ALIASES : PLACEMENT_ALIASES;
  const allSections = navigationConfig.flatMap((group) => group.items);
  const normalized = aliases[requested] || requested;
  const groups = navigationConfig.map((group) => ({
    ...group,
    items: group.items.filter((item) => permitted(item, can, accessContext)),
  })).filter((group) => group.items.length);
  const sections = groups.flatMap((group) => group.items);
  const recognized = allSections.some((item) => item.id === normalized);
  const denied = params.has("section") && recognized && !sections.some((item) => item.id === normalized);
  const active = denied ? normalized : sections.some((item) => item.id === normalized) ? normalized : sections[0]?.id || defaultSection;
  const activeSection = allSections.find((item) => item.id === active);
  const selectedScope = academicScopeValues(params);
  const contextDomain = active === "attendance" ? "attendance"
    : ["results", "assessments"].includes(active) ? "assessments" : "academics";

  useRegisterAIPageContext(academics ? academicScopeContext({
    ...selectedScope,
    domain: contextDomain,
  }) : null);

  useEffect(() => {
    if (redirectTo || denied) return;
    if (requested === active) return;
    const next = new URLSearchParams(params);
    if (active === defaultSection) next.delete("section"); else next.set("section", active);
    setParams(next, { replace: true });
  }, [active, defaultSection, denied, params, redirectTo, requested, setParams]);

  if (redirectTo) return <Navigate to={redirectTo} replace />;

  const changeSection = (section) => {
    const next = academics ? academicScopeParams(params) : new URLSearchParams();
    if (section !== defaultSection) next.set("section", section);
    setParams(next);
  };
  const navigation = (close) => <SecondarySidebarNav>
    {groups.map((group) => <SecondarySidebarGroup key={group.label} label={group.label}>
      {group.items.map((item) => <SecondarySidebarItem
        key={item.id}
        icon={item.icon}
        label={item.label}
        active={active === item.id}
        onClick={() => { changeSection(item.id); close?.(); }}
      />)}
    </SecondarySidebarGroup>)}
  </SecondarySidebarNav>;

  return <SecondarySidebarLayout
    ariaLabel={academics ? "College academics navigation" : "College placement navigation"}
    className="reveal bg-card"
    sidebarClassName="bg-surface-subtle/35"
    contentClassName="bg-background"
    mobileTitle={academics ? "College academics" : "College placement"}
    mobileDescription={academics ? "Structure, evidence, and data operations" : "Placement, readiness, and student success"}
    sidebar={<><SecondarySidebarHeader title={academics ? "Academic workspace" : "Placement workspace"} description={academics ? "Structure to evidence" : "Evidence to outcomes"} />{navigation()}</>}
    mobileSidebar={({ closeSidebar }) => navigation(closeSidebar)}
  >
    {({ openSidebar }) => <div className="min-w-0">
      <div className="flex items-center gap-3 border-b bg-card px-4 py-3 lg:hidden">
        <SecondarySidebarTrigger icon={activeSection?.icon} label={activeSection?.label || "College"} onClick={openSidebar} />
      </div>
      <main className="mx-auto w-full max-w-[1520px] space-y-5 p-4 sm:p-6 lg:p-8">
        <CollegeSectionHeader section={active} workspace={workspace} navigate={navigate} />
        {academics && ["attendance", "results", "assessments"].includes(active) && <AcademicScopeBar compact />}
        {denied
          ? <PermissionDeniedPage embedded title={`No access to ${activeSection?.label || "this academic section"}`} description="Your College access policy does not include this work area." />
          : <CollegeSection section={active} />}
      </main>
    </div>}
  </SecondarySidebarLayout>;
}

function CollegeSectionHeader({ section, workspace, navigate }) {
  const [title, description] = SECTION_COPY[section] || ["College placement", "Student success workspace"];
  const ask = encodeURIComponent(aiPrompt(section));
  return <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
    <div className="min-w-0"><p className="section-kicker">College / {workspace === "academics" ? "Academic operations" : "Placement intelligence"}</p><h1 className="mt-1.5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">{title}</h1><p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{description}</p></div>
    <Button variant="outline" onClick={() => navigate(`/app/ai?ask=${ask}`)}><Sparkle className="mr-2 text-accent" weight="fill" />Ask Edvatiq</Button>
  </header>;
}

function CollegeSection({ section }) {
  if (section === "pipeline") return <ApplicationsPanel pipeline />;
  if (section === "drives") return <DrivesPanel />;
  if (section === "applications") return <ApplicationsPanel />;
  if (section === "companies") return <CompaniesPanel />;
  if (section === "readiness") return <ReadinessPanel />;
  if (section === "coding") return <LeaderboardPanel initialBoard="coding" />;
  if (section === "leaderboards") return <LeaderboardPanel />;
  if (section === "overview") return <AcademicOverview />;
  if (section === "structure") return <AcademicStructurePanel />;
  if (section === "attendance") return <AttendancePanel />;
  if (section === "results") return <AcademicEvidencePanel />;
  if (section === "assessments") return <AssessmentsPanel />;
  if (section === "integrations") return <IntegrationsPanel />;
  if (section === "exchange") return <DataExchangePanel />;
  if (section === "policy") return <ReadinessPolicyPanel />;
  if (section === "clearance") return <ClearancePanel />;
  return null;
}

const ACADEMIC_METRICS = [
  { key: "students_in_scope", label: "Students in scope", icon: Student, format: (value) => Number(value).toLocaleString("en-IN") },
  { key: "average_attendance_percent", label: "Average attendance", icon: CalendarCheck, format: percent },
  { key: "results_coverage_percent", label: "Published result coverage", icon: Books, format: percent },
  { key: "active_assessments", label: "Active assessments", icon: GraduationCap, format: (value) => Number(value).toLocaleString("en-IN") },
];

function AcademicOverview() {
  const [params, setParams] = useSearchParams();
  const { academicYearId, termId, departmentId, programId, cohortId } = academicScopeValues(params);
  const query = useGetCollegeAcademicSummaryQuery({
    academicYearId, termId, departmentId, programId, cohortId,
  });
  const data = query.currentData;
  const loading = !data && (query.isLoading || query.isFetching);
  const metrics = ACADEMIC_METRICS.filter((item) => data?.metrics?.[item.key] != null);

  const openSection = (section) => {
    const next = academicScopeParams(params);
    next.set("section", section);
    setParams(next);
  };

  if (query.isError && !data) return <ErrorState title="Academic overview could not be loaded" description={query.error?.data?.detail || "Retry before using these academic totals."} retry={query.refetch} />;

  return <div className="space-y-5">
    <AcademicScopeBar data={data} />

    {loading ? <AcademicOverviewSkeleton /> : <>
      {metrics.length > 0 && <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Academic metrics">
        {metrics.map((item) => <AcademicMetric key={item.key} definition={item} value={data.metrics[item.key]} />)}
      </section>}

      <section className="grid items-start gap-5 xl:grid-cols-12">
        {data?.capabilities?.attendance && <Surface className="overflow-hidden xl:col-span-7">
          <OverviewHeading eyebrow="Attendance" title="Attendance trend" copy={data.attendance_trend?.length ? "Average authorized attendance evidence for this scope." : "No dated attendance snapshots are available for this scope."} />
          {data.attendance_trend?.length ? <div className="px-3 pb-4 sm:px-5"><BusinessChart data={data.attendance_trend} xKey="date" series={[{ key: "attendance_percent", label: "Attendance %" }]} type="area" height={280} ariaLabel="Academic attendance trend" /></div> : <EmptyState className="m-4" variant="inline" alignment="left" icon={CalendarCheck} title="No attendance trend yet" description="Synchronize attendance evidence or record a local session." />}
        </Surface>}
        {data?.capabilities?.results && <Surface className="overflow-hidden xl:col-span-5">
          <OverviewHeading eyebrow="Results" title="Publication coverage" copy="Students with published results in the selected period." />
          <CoveragePanel coverage={data.result_coverage} onOpen={() => openSection("results")} />
        </Surface>}
      </section>

      <section className="grid items-start gap-5 xl:grid-cols-12">
        {(data?.structure || data?.freshness) && <Surface className="overflow-hidden xl:col-span-5">
          <OverviewHeading eyebrow="Foundation" title="Structure and source health" copy="The academic foundation used by placement evidence and Edvatiq AI." />
          <AcademicHealth data={data} onOpen={openSection} />
        </Surface>}
        <Surface className={`${data?.structure || data?.freshness ? "xl:col-span-7" : "xl:col-span-12"} overflow-hidden`}>
          <OverviewHeading eyebrow="Priorities" title="Needs attention" copy="Only actionable gaps from your authorized academic scope." />
          <AcademicAttention rows={data?.attention || []} onOpen={openSection} />
        </Surface>
      </section>
    </>}
  </div>;
}

function AcademicScopeBar({ data, compact = false }) {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const { academicYearId, termId, departmentId, programId, cohortId } = academicScopeValues(params);
  const canBrowseStructure = can("college.academics.view") || can("college.academics.manage");
  const hierarchy = useGetCollegeAcademicHierarchyQuery(undefined, { skip: !canBrowseStructure });
  const academicYears = hierarchy.data?.academic_years || [];
  const updateScope = (key, value, clear = []) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    clear.forEach((item) => next.delete(item));
    next.delete("cursor");
    setParams(next, { replace: true });
  };
  const clearScope = () => {
    const next = new URLSearchParams(params);
    ACADEMIC_SCOPE_KEYS.forEach((key) => next.delete(key));
    next.delete("cursor");
    setParams(next, { replace: true });
  };
  if (!canBrowseStructure) return null;
  return <Surface className="overflow-hidden">
    {!compact && <div className="flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0">
        <div className="overline">Current academic scope</div>
        <h2 className="mt-1 text-xl font-semibold">{data?.scope?.term?.name || "Institution overview"}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{[data?.scope?.term?.academic_year || academicYearId, data?.scope?.term?.status ? sentence(data.scope.term.status) : null].filter(Boolean).join(" / ") || "Showing all authorized academic evidence"}</p>
      </div>
      {(academicYearId || termId || departmentId || programId || cohortId) && <Button variant="ghost" size="sm" onClick={clearScope}>Clear scope</Button>}
    </div>}
    <div className={`grid gap-3 bg-surface-subtle/25 p-4 sm:grid-cols-2 xl:grid-cols-5 sm:p-5 ${compact ? "" : "border-t"}`}>
      <Select value={academicYearId || "all"} onValueChange={(value) => updateScope("academic_year_id", value === "all" ? "" : value, ["term_id"])}>
        <SelectTrigger aria-label="Academic year"><SelectValue placeholder="Academic year" /></SelectTrigger>
        <SelectContent><SelectItem value="all">All academic years</SelectItem>{academicYears.map((year) => <SelectItem key={year} value={year}>{year}</SelectItem>)}</SelectContent>
      </Select>
      <AcademicResourceCombobox resource="terms" value={termId} onValueChange={(value) => updateScope("term_id", value)} filters={{ active: true, academic_year: academicYearId || undefined }} placeholder="Academic term" />
      <AcademicResourceCombobox resource="departments" value={departmentId} onValueChange={(value) => updateScope("department_id", value, ["program_id", "cohort_id"])} filters={{ active: true }} placeholder="Department" />
      <AcademicResourceCombobox resource="programs" value={programId} onValueChange={(value) => updateScope("program_id", value, ["cohort_id"])} filters={{ active: true, department_id: departmentId || undefined }} placeholder="Program" />
      <AcademicResourceCombobox resource="cohorts" value={cohortId} onValueChange={(value) => updateScope("cohort_id", value)} filters={{ active: true, department_id: departmentId || undefined, program_id: programId || undefined }} placeholder="Batch or section" />
    </div>
    {compact && (academicYearId || termId || departmentId || programId || cohortId) && <div className="flex justify-end border-t px-4 py-2"><Button variant="ghost" size="sm" onClick={clearScope}>Clear academic scope</Button></div>}
  </Surface>;
}

function AcademicMetric({ definition, value }) {
  const Icon = definition.icon;
  return <Surface className="p-4 sm:p-5"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-medium text-muted-foreground">{definition.label}</p><p className="mt-3 text-3xl font-semibold tracking-[-0.04em]">{definition.format(value)}</p></div><span className="grid h-9 w-9 place-items-center rounded-xl bg-accent/10 text-accent"><Icon /></span></div></Surface>;
}

function OverviewHeading({ eyebrow, title, copy }) {
  return <div className="border-b p-4 sm:p-5"><div className="overline">{eyebrow}</div><h3 className="mt-1 font-semibold">{title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{copy}</p></div>;
}

function CoveragePanel({ coverage, onOpen }) {
  const value = coverage?.percent;
  if (value == null) return <EmptyState className="m-4" variant="inline" alignment="left" icon={Books} title="No result coverage yet" description="Published term results will appear here." />;
  return <div className="p-5"><div className="flex items-end justify-between gap-4"><div><div className="text-4xl font-semibold tracking-[-0.04em]">{percent(value)}</div><p className="mt-1 text-xs text-muted-foreground">{coverage.students_with_results} of {coverage.students_in_scope} students</p></div><Button variant="ghost" size="sm" onClick={onOpen}>Review results<ArrowRight className="ml-1.5" /></Button></div><div className="mt-5 h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.max(0, Math.min(100, Number(value)))}%` }} /></div></div>;
}

function AcademicHealth({ data, onOpen }) {
  const structure = data.structure;
  const freshness = data.freshness || {};
  const rows = [
    structure && { label: "Academic structure", value: structure.ready ? "Ready" : "Setup needed", detail: `${structure.departments} departments / ${structure.programs} programs / ${structure.cohorts} batches`, section: "structure", tone: structure.ready ? "active" : "warning" },
    data.capabilities?.integrations && { label: "ERP synchronization", value: freshness.stale_connectors ? `${freshness.stale_connectors} need attention` : freshness.connector_count ? "Current" : "Not connected", detail: freshness.last_erp_sync_at ? `Last sync ${relativeTime(freshness.last_erp_sync_at)}` : "No successful synchronization", section: "integrations", tone: freshness.stale_connectors ? "warning" : freshness.connector_count ? "active" : "pending" },
    data.capabilities?.exchange && { label: "Data Exchange", value: freshness.last_exchange_at ? "Active" : "No runs yet", detail: freshness.last_exchange_at ? `Last activity ${relativeTime(freshness.last_exchange_at)}` : "Templates and reviewed runs appear here", section: "exchange", tone: freshness.last_exchange_at ? "active" : "neutral" },
  ].filter(Boolean);
  return <div className="divide-y">{rows.map((row) => <button key={row.label} type="button" onClick={() => onOpen(row.section)} className="flex w-full items-center gap-3 p-4 text-left transition-colors hover:bg-surface-hover sm:px-5"><span className="min-w-0 flex-1"><span className="block text-sm font-medium">{row.label}</span><span className="mt-1 block text-xs text-muted-foreground">{row.detail}</span></span><StatusBadge status={row.tone} label={row.value} /><ArrowRight className="shrink-0 text-muted-foreground" /></button>)}{!rows.length && <EmptyState variant="inline" alignment="left" title="No foundation details available" description="Your access policy does not include structure or data operations." />}</div>;
}

function AcademicAttention({ rows, onOpen }) {
  if (!rows.length) return <EmptyState variant="inline" alignment="left" icon={CheckCircle} title="Academic evidence is in good shape" description="No immediate structure, coverage, or source-freshness issue needs action." />;
  return <div className="divide-y">{rows.map((row) => <button key={row.id} type="button" onClick={() => onOpen(row.section)} className="group flex w-full items-start gap-3 p-4 text-left transition-colors hover:bg-surface-hover sm:px-5"><span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent/10 text-accent"><WarningCircle /></span><span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{row.title}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{row.detail}</span></span><ArrowRight className="mt-2 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" /></button>)}</div>;
}

function AcademicOverviewSkeleton() {
  return <div className="space-y-5" aria-label="Loading academic overview"><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((item) => <Surface key={item} className="h-28 animate-pulse bg-surface-subtle" />)}</div><div className="grid gap-5 xl:grid-cols-12"><Surface className="h-80 animate-pulse bg-surface-subtle xl:col-span-7" /><Surface className="h-80 animate-pulse bg-surface-subtle xl:col-span-5" /></div></div>;
}

function usePagedData(query, paging) {
  const { accept } = paging;
  useEffect(() => { accept(query.data); }, [accept, query.data]);
  return paging.items;
}

function ListFooter({ query, paging, noun }) {
  return <CursorListFooter
    count={paging.items.length}
    noun={noun}
    hasMore={Boolean(query.data?.next_cursor)}
    loading={query.isFetching}
    error={query.isError && paging.items.length > 0}
    onLoadMore={() => paging.loadMore(query.data?.next_cursor)}
    onRetry={query.refetch}
  />;
}

function SearchField({ value, onChange, placeholder }) {
  return <div className="relative min-w-0 flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={value} onChange={(event) => onChange(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder={placeholder} /></div>;
}

function ApplicationsPanel({ pipeline = false }) {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [stage, setStage] = useState("all");
  const [drawer, setDrawer] = useState(false);
  const stages = useGetCollegePipelineStagesQuery();
  const key = JSON.stringify({ q, stage, pipeline });
  const paging = useCursorPagination(key);
  const query = useGetCollegeApplicationsQuery({ q, stage_id: stage === "all" ? undefined : stage, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const [moveStage, moveState] = useMoveCollegeApplicationStageMutation();
  const move = async (row, stageId) => {
    if (stageId === row.current_stage_id) return;
    try {
      await moveStage({ applicationId: row.id, stageId, version: row.version, reason: "Moved from placement pipeline" }).unwrap();
      toast.success("Application stage updated");
    } catch (error) { toast.error(error?.data?.detail || "Application could not be moved"); }
  };
  const columns = [
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.student.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.student.admission_number || row.student.roll_number}</div></div> },
    { key: "opportunity", label: "Opportunity", render: (row) => <div><div>{row.opportunity.title}</div><div className="mt-1 text-xs text-muted-foreground">{row.company.name}</div></div> },
    { key: "eligibility", label: "Eligibility", render: (row) => <StatusBadge status={eligibilityTone(row.eligibility_override_status || row.eligibility_status)} label={sentence(row.eligibility_override_status || row.eligibility_status)} /> },
    { key: "stage", label: "Stage", render: (row) => can("college.applications.manage") ? <Select value={row.current_stage_id || ""} onValueChange={(value) => move(row, value)} disabled={moveState.isLoading}><SelectTrigger className="h-9 min-w-40"><SelectValue /></SelectTrigger><SelectContent>{(stages.data?.items || []).filter((item) => item.is_enabled).map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select> : <StatusBadge status={row.stage?.slug} label={row.stage?.name || "Eligible"} /> },
    { key: "updated", label: "Updated", render: (row) => shortDate(row.updated_at) },
  ];
  return <Surface className="overflow-hidden">
    <PanelToolbar title={pipeline ? "Live pipeline" : "Application register"} action={can("college.applications.manage") && <Button size="sm" onClick={() => setDrawer(true)}><Plus className="mr-2" />New application</Button>} />
    <FilterBar className="rounded-none border-x-0 border-t"><SearchField value={search} onChange={setSearch} placeholder="Search student, company, or opportunity" /><Select value={stage} onValueChange={setStage}><SelectTrigger className="w-full sm:w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All stages</SelectItem>{(stages.data?.items || []).map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></FilterBar>
    <DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant="section" alignment="left" icon={Funnel} title="No applications in this view" description="Applications will appear after students are added to an active opportunity." />} />
    <ListFooter query={query} paging={paging} noun="applications" />
    <ApplicationDrawer open={drawer} onClose={() => setDrawer(false)} />
  </Surface>;
}

function DrivesPanel() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [status, setStatus] = useState("all");
  const drawer = params.get("new") === "1";
  const setDrawer = (open) => {
    const next = new URLSearchParams(params);
    if (open) next.set("new", "1"); else next.delete("new");
    setParams(next, { replace: true });
  };
  const paging = useCursorPagination(JSON.stringify({ q, status }));
  const query = useGetCollegeOpportunitiesQuery({ q, status: status === "all" ? undefined : status, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "drive", label: "Drive", render: (row) => <div><div className="font-semibold">{row.title}</div><div className="mt-1 text-xs text-muted-foreground">{row.company?.name} / {sentence(row.opportunity_type)}</div></div> },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "deadline", label: "Deadline", render: (row) => dateTime(row.deadline_at) },
    { key: "drive_at", label: "Drive date", render: (row) => dateTime(row.drive_at) },
    { key: "package", label: "Package", render: packageRange },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Opportunities and drives" action={can("college.opportunities.manage") && <Button size="sm" onClick={() => setDrawer(true)}><Plus className="mr-2" />New drive</Button>} /><FilterBar className="rounded-none border-x-0 border-t"><SearchField value={search} onChange={setSearch} placeholder="Search drive or company" /><Select value={status} onValueChange={setStatus}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All statuses</SelectItem>{["draft", "published", "active", "closed", "cancelled"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></FilterBar><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant="section" alignment="left" icon={Briefcase} title="No drives in this view" description="Create the first opportunity or clear the current filters." />} /><ListFooter query={query} paging={paging} noun="drives" /><DriveDrawer open={drawer} onClose={() => setDrawer(false)} /></Surface>;
}

function CompaniesPanel() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const drawer = params.get("new") === "1";
  const setDrawer = (open) => {
    const next = new URLSearchParams(params);
    if (open) next.set("new", "1"); else next.delete("new");
    setParams(next, { replace: true });
  };
  const paging = useCursorPagination(q);
  const query = useGetCollegeCompaniesQuery({ q, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "name", label: "Company", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.industry || "Industry not recorded"}</div></div> },
    { key: "contact", label: "Placement contact", render: (row) => row.contact_name || row.contact_email || "Not recorded" },
    { key: "website", label: "Website", render: (row) => row.website || "Not recorded" },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Employer network" action={can("college.companies.manage") && <Button size="sm" onClick={() => setDrawer(true)}><Plus className="mr-2" />Add company</Button>} /><FilterBar className="rounded-none border-x-0 border-t"><SearchField value={search} onChange={setSearch} placeholder="Search company" /></FilterBar><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant="section" alignment="left" icon={Buildings} title="No recruiting companies yet" description="Add an employer before creating its first opportunity." />} /><ListFooter query={query} paging={paging} noun="companies" /><CompanyDrawer open={drawer} onClose={() => setDrawer(false)} /></Surface>;
}

function ReadinessPanel() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [band, setBand] = useState("all");
  const paging = useCursorPagination(JSON.stringify({ q, band }));
  const query = useGetCollegeStudentIntelligenceQuery({ q, readiness_band: band === "all" ? undefined : band, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number} / {row.cohort?.name}</div></div> },
    { key: "readiness", label: "Readiness", render: (row) => <div><StatusBadge status={readinessTone(row.readiness_band)} label={sentence(row.readiness_band)} />{row.readiness?.score != null && <div className="mt-1 text-xs text-muted-foreground">{row.readiness.score}% score / {row.readiness.coverage_percent}% evidence</div>}</div> },
    { key: "academics", label: "Academic evidence", render: (row) => `CGPA ${row.cgpa ?? "-"} / Attendance ${row.attendance_percent == null ? "-" : `${row.attendance_percent}%`}` },
    { key: "coding", label: "Coding", render: (row) => row.coding_total == null ? "Not connected" : `${row.coding_total} solved` },
    { key: "support", label: "Profile", render: (row) => <StatusBadge status={["reviewed", "approved"].includes(row.resume_status) ? "active" : "pending"} label={sentence(row.resume_status)} /> },
    { key: "open", label: "", render: () => <ArrowRight /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Student readiness register" /><FilterBar className="rounded-none border-x-0 border-t"><SearchField value={search} onChange={setSearch} placeholder="Search student or admission number" /><Select value={band} onValueChange={setBand}><SelectTrigger className="w-full sm:w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All readiness bands</SelectItem>{["ready", "developing", "needs_support", "insufficient_evidence"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></FilterBar><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} onRowClick={(row) => navigate(`/app/clients/${row.client_id}`)} empty={<EmptyState variant="section" alignment="left" icon={Target} title="No students match this readiness view" description="Clear the filters or synchronize academic evidence." />} /><ListFooter query={query} paging={paging} noun="students" /></Surface>;
}

function LeaderboardPanel({ initialBoard = "readiness" }) {
  const navigate = useNavigate();
  const [board, setBoard] = useState(initialBoard);
  const [windowDays, setWindowDays] = useState(30);
  const query = useGetCollegeLeaderboardsQuery({ window_days: windowDays, limit: 25 });
  const rows = query.data?.[board] || [];
  const columns = [{ key: "rank", label: "Rank", render: (row) => `#${row.rank}` }, { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number}</div></div> }, ...leaderboardColumns(board)];
  return <Surface className="overflow-hidden"><PanelToolbar title={initialBoard === "coding" ? "Coding progress" : "Evidence leaderboards"} /><div className="flex flex-col gap-3 border-t p-3 sm:flex-row sm:items-center sm:justify-between">{initialBoard !== "coding" && <SegmentControl value={board} onChange={setBoard} items={["readiness", "coding", "academics", "improvement"].map((value) => ({ value, label: sentence(value) }))} />}{board === "improvement" && <SegmentControl value={windowDays} onChange={setWindowDays} items={[30, 90].map((value) => ({ value, label: `${value} days` }))} />}</div><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading} onRowClick={(row) => navigate(`/app/clients/${row.client_id}`)} empty={<EmptyState variant="section" alignment="left" icon={Medal} title="No rankable evidence yet" description="Students remain visible after they meet the configured evidence threshold." />} /></Surface>;
}

function AttendancePanel() {
  const { can } = useAuth();
  const [params] = useSearchParams();
  const scope = academicScopeValues(params);
  const [drawer, setDrawer] = useState(false);
  const [register, setRegister] = useState(null);
  const paging = useCursorPagination(JSON.stringify({ resource: "attendance-sessions", ...scope }));
  const query = useGetCollegeAttendanceSessionsPageQuery({ ...scope, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "course", label: "Course", render: (row) => <div><div className="font-semibold">{row.course_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.course_code} / {row.cohort_name}</div></div> },
    { key: "held", label: "Held on", render: (row) => shortDate(row.held_on) },
    { key: "topic", label: "Topic", render: (row) => row.topic || "Not recorded" },
    { key: "coverage", label: "Recorded", render: (row) => `${row.record_count} students` },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "open", label: "", render: () => <ArrowRight /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Attendance sessions" action={can("college.attendance.mark") && <Button size="sm" onClick={() => setDrawer(true)}><Plus className="mr-2" />New local session</Button>} />{query.isError && !rows.length ? <div className="border-t p-4"><ErrorState title="Attendance sessions could not be loaded" description={query.error?.data?.detail || "Retry this academic scope without losing your filters."} retry={query.refetch} /></div> : <><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} onRowClick={setRegister} empty={<EmptyState variant="section" alignment="left" icon={CalendarCheck} title="No attendance evidence in this scope" description="ERP attendance snapshots are preferred; use a local session only when needed." />} /><ListFooter query={query} paging={paging} noun="sessions" /></>}<AttendanceSessionDrawer open={drawer} onClose={() => setDrawer(false)} /><AttendanceRegisterDrawer session={register} onClose={() => setRegister(null)} /></Surface>;
}

function AcademicEvidencePanel() {
  const [params] = useSearchParams();
  const scope = academicScopeValues(params);
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const paging = useCursorPagination(JSON.stringify({ kind: "term_results", q, ...scope }));
  const query = useGetCollegeAcademicEvidencePageQuery({ kind: "term_results", q, ...scope, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "student", label: "Student", render: studentEvidenceCell },
    { key: "semester", label: "Semester", render: (row) => row.semester },
    { key: "sgpa", label: "SGPA", render: (row) => row.sgpa ?? "-" },
    { key: "cgpa", label: "CGPA", render: (row) => row.cgpa ?? "-" },
    { key: "backlogs", label: "Active backlogs", render: (row) => row.active_backlogs ?? "Not recorded" },
    { key: "source", label: "Source", render: (row) => <StatusBadge status="neutral" label={sentence(row.source_type || "local")} /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Published term results" /><FilterBar className="rounded-none border-x-0 border-t"><SearchField value={search} onChange={setSearch} placeholder="Search student or admission number" /></FilterBar>{query.isError && !rows.length ? <div className="border-t p-4"><ErrorState title="Published results could not be loaded" description={query.error?.data?.detail || "Retry this academic scope without losing your filters."} retry={query.refetch} /></div> : <><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant={q ? "filtered" : "section"} alignment="left" icon={Books} title={q ? "No students match this search" : "No published results in this scope"} description={q ? "Clear the student search to return to all authorized results." : "Synchronize results from the College ERP or import a reviewed term-result file."} primaryAction={q ? <Button variant="outline" size="sm" onClick={() => setSearch("")}>Clear search</Button> : undefined} />} /><ListFooter query={query} paging={paging} noun="result records" /></>}</Surface>;
}

function AssessmentsPanel() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "patterns" ? "patterns" : "cycles";
  const [cycleDrawer, setCycleDrawer] = useState(false);
  const [register, setRegister] = useState(null);
  const scope = academicScopeValues(params);
  const paging = useCursorPagination(JSON.stringify({ resource: "assessments", ...scope }));
  const query = useGetCollegeAssessmentsPageQuery(
    { ...scope, cursor: paging.cursor, limit: 25 },
    { skip: view === "patterns" },
  );
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "title", label: "Assessment", render: (row) => <div><div className="font-semibold">{row.title}</div><div className="mt-1 text-xs text-muted-foreground">{row.cycle_code || sentence(row.assessment_type)} / {row.course_name || sentence(row.scheme_snapshot?.domain || "cohort assessment")}</div></div> },
    { key: "cohort", label: "Batch", render: (row) => row.cohort_name || "Not available" },
    { key: "due", label: "Due", render: (row) => shortDate(row.due_on) },
    { key: "scores", label: "Scores", render: (row) => row.score_count },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "open", label: "", render: () => <ArrowRight /> },
  ];
  const chooseView = (value) => {
    const next = new URLSearchParams(params);
    if (value === "cycles") next.delete("view"); else next.set("view", value);
    setParams(next, { replace: true });
  };
  return <div className="space-y-5">
    <Surface className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
      <SegmentControl value={view} onChange={chooseView} items={[{ value: "cycles", label: "Exam cycles & registers" }, { value: "patterns", label: "Assessment patterns" }]} />
      <p className="px-1 text-xs text-muted-foreground">Patterns define institution-specific fields; cycles create the working registers.</p>
    </Surface>
    {view === "patterns" ? <AssessmentPatternsPanel /> : <Surface className="overflow-hidden"><PanelToolbar title="Institution-configured assessments" action={can("college.assessments.manage") && <Button size="sm" onClick={() => setCycleDrawer(true)}><Plus className="mr-2" />New exam cycle</Button>} />{query.isError && !rows.length ? <div className="border-t p-4"><ErrorState title="Assessment cycles could not be loaded" description={query.error?.data?.detail || "Retry this academic scope without losing your filters."} retry={query.refetch} /></div> : <><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} onRowClick={setRegister} empty={<EmptyState variant="section" alignment="left" icon={GraduationCap} title="No assessment cycles in this scope" description="Configure an assessment pattern, then create a cycle for the required courses or cohorts." primaryAction={(can("college.assessments.manage") || can("college.academics.manage")) ? <Button variant="outline" onClick={() => chooseView("patterns")}>Configure patterns</Button> : undefined} />} /><ListFooter query={query} paging={paging} noun="assessments" /></>}<ExamCycleDrawer open={cycleDrawer} onClose={() => setCycleDrawer(false)} /><DynamicAssessmentRegisterDrawer assessment={register} onClose={() => setRegister(null)} /></Surface>}
  </div>;
}

function IntegrationsPanel() {
  const [mode, setMode] = useState("pull");
  const [pullDrawer, setPullDrawer] = useState(null);
  const [credentialDrawer, setCredentialDrawer] = useState(false);
  const [secret, setSecret] = useState(null);
  const [rotateTarget, setRotateTarget] = useState(null);
  const [revokeTarget, setRevokeTarget] = useState(null);
  const [syncing, setSyncing] = useState(null);
  const pullQuery = useGetCollegeIntegrationsQuery(undefined, { skip: mode !== "pull" });
  const credentialQuery = useGetCollegeIntegrationCredentialsQuery(undefined, { skip: mode !== "push" });
  const [sync, syncState] = useQueueCollegeIntegrationSyncMutation();
  const [rotate] = useRotateCollegeIntegrationCredentialMutation();
  const [revoke] = useRevokeCollegeIntegrationCredentialMutation();
  const run = async (id) => {
    setSyncing(id);
    const connector = (pullQuery.data?.items || []).find((item) => item.id === id);
    try { await sync({ connectorId: id, resourceTypes: connector?.resource_types || [], idempotencyKey: crypto.randomUUID() }).unwrap(); toast.success("ERP synchronization queued"); }
    catch (error) { toast.error(error?.data?.detail || "Synchronization could not be queued"); }
    finally { setSyncing(null); }
  };
  const rotateCredential = async (values) => {
    const result = await rotate({ credentialId: rotateTarget.id, version: rotateTarget.version, expiresAt: new Date(values.expires_at).toISOString() }).unwrap();
    setSecret({ name: result.name, value: result.secret, rotated: true });
    toast.success("Push credential rotated");
  };
  const revokeCredential = async () => {
    await revoke({ credentialId: revokeTarget.id, version: revokeTarget.version }).unwrap();
    toast.success("Push credential revoked");
  };
  return <div className="space-y-5">
    <OwnershipNotice />
    <div className="flex items-center justify-between gap-3"><SegmentControl value={mode} onChange={setMode} items={[{ value: "pull", label: "ERP pulls" }, { value: "push", label: "ERP push API" }]} /><Button asChild variant="ghost" size="sm"><Link target="_blank" to={mode === "pull" ? "/docs/erp-pull" : "/docs/erp-push"}>Integration guide <ArrowRight className="ml-1.5" /></Link></Button></div>
    {mode === "pull" ? <Surface className="overflow-hidden">
      <PanelToolbar title="Connected College ERP" action={<Button size="sm" onClick={() => setPullDrawer({})}><Plus className="mr-2" />Connect ERP</Button>} />
      <div className="divide-y border-t">{(pullQuery.data?.items || []).map((row) => <div key={row.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary"><Database /></span><span className="min-w-0 flex-1"><span className="block font-semibold">{row.name}</span><span className="mt-1 block text-xs text-muted-foreground">{row.last_sync_at ? `Last sync ${dateTime(row.last_sync_at)}` : "No successful sync yet"} / {row.resource_types?.length || 0} configured resources</span></span><StatusBadge status={row.status} /><div className="flex gap-2"><Button variant="ghost" size="sm" onClick={() => setPullDrawer(row)}>Edit</Button><Button variant="outline" size="sm" onClick={() => run(row.id)} loading={syncing === row.id && syncState.isLoading} loadingText="Queuing..." disabled={!row.api_key_configured || !row.resource_types?.length}>Sync now</Button></div></div>)}
        {!pullQuery.isLoading && !pullQuery.data?.items?.length && <EmptyState variant="section" alignment="left" icon={Database} title="No ERP pull connected" description="Connect a credential-protected read-only HTTPS source, or continue with reviewed CSV imports." primaryAction={<Button variant="outline" onClick={() => setPullDrawer({})}>Connect ERP</Button>} className="m-4" />}
      </div>
      <ConnectorDrawer open={Boolean(pullDrawer)} connector={pullDrawer?.id ? pullDrawer : null} onClose={() => setPullDrawer(null)} />
    </Surface> : <Surface className="overflow-hidden">
      <PanelToolbar title="Organization-scoped push credentials" action={<Button size="sm" onClick={() => setCredentialDrawer(true)}><Key className="mr-2" />Create credential</Button>} />
      <div className="border-t bg-secondary/20 px-4 py-3 text-xs leading-5 text-muted-foreground sm:px-5">Secrets are shown once, stored only as hashes, limited to selected resources, and subject to expiry, revocation, idempotency, and audited rate limits.</div>
      <div className="divide-y">{(credentialQuery.data?.items || []).map((row) => <div key={row.id} className="flex flex-col gap-3 p-4 sm:p-5 lg:flex-row lg:items-center">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary"><Key /></span>
        <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{row.name}</span><StatusBadge status={row.status} /><code className="rounded bg-secondary px-1.5 py-0.5 text-[10px]">{row.key_prefix}</code></div><p className="mt-1 text-xs text-muted-foreground">{row.scopes.map(sentence).join(", ")} / expires {dateTime(row.expires_at)}{row.last_used_at ? ` / last used ${dateTime(row.last_used_at)}` : " / never used"}</p></div>
        {row.status === "active" && <div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => setRotateTarget(row)}><ArrowClockwise className="mr-1.5" />Rotate</Button><Button variant="outline" size="sm" onClick={() => setRevokeTarget(row)}><Trash className="mr-1.5" />Revoke</Button></div>}
      </div>)}
        {!credentialQuery.isLoading && !credentialQuery.data?.items?.length && <EmptyState variant="section" alignment="left" icon={Key} title="No push credentials" description="Create a short-lived, resource-scoped credential when your College ERP needs to send authoritative evidence to Edvatiq." primaryAction={<Button variant="outline" onClick={() => setCredentialDrawer(true)}>Create credential</Button>} className="m-4" />}
      </div>
      <CredentialDrawer open={credentialDrawer} onClose={() => setCredentialDrawer(false)} onCreated={(result) => { setCredentialDrawer(false); setSecret({ name: result.name, value: result.secret, rotated: false }); }} />
    </Surface>}
    <SecretDialog secret={secret} onClose={() => setSecret(null)} />
    <ValidatedActionDialog open={Boolean(rotateTarget)} onOpenChange={(open) => { if (!open) setRotateTarget(null); }} resetKey={rotateTarget?.id} title="Rotate ERP push credential" description={rotateTarget ? `Replace the secret for ${rotateTarget.name}.` : ""} impact="The current secret stops working immediately. Copy the replacement once and update the ERP before its next request." schema={collegePushCredentialSchema.pick({ expires_at: true })} defaultValues={{ expires_at: credentialExpiryValue(rotateTarget?.expires_at) }} fields={[{ name: "expires_at", label: "New expiry", type: "datetime-local" }]} submitLabel="Rotate credential" loadingText="Rotating..." onSubmit={rotateCredential} />
    <ValidatedActionDialog open={Boolean(revokeTarget)} onOpenChange={(open) => { if (!open) setRevokeTarget(null); }} resetKey={revokeTarget?.id} title="Revoke ERP push credential" description={revokeTarget ? `Stop ${revokeTarget.name} from sending any further evidence.` : ""} impact="Revocation is immediate and cannot be reversed. Historical import runs and audit evidence remain available." schema={collegePushCredentialSchema.pick({}).strict()} defaultValues={{}} fields={[]} submitLabel="Revoke credential" loadingText="Revoking..." variant="destructive" onSubmit={revokeCredential} />
  </div>;
}

function ReadinessPolicyPanel() {
  const query = useGetCollegeReadinessPolicyQuery();
  if (query.isError) return <ErrorState title="Readiness policy could not be loaded" retry={query.refetch} />;
  const policy = query.data;
  const weights = policy?.weights || {};
  return <div className="grid items-start gap-5 xl:grid-cols-12"><Surface className="overflow-hidden xl:col-span-8"><PanelToolbar title={policy?.name || "Placement readiness"} /><div className="grid gap-px border-t bg-border sm:grid-cols-2">{Object.entries(weights).map(([key, value]) => <div key={key} className="bg-card p-4"><div className="flex items-center justify-between gap-3"><span className="text-sm font-medium">{sentence(key)}</span><strong>{value}%</strong></div><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-primary" style={{ width: `${value}%` }} /></div></div>)}</div></Surface><Surface className="p-5 xl:col-span-4"><h2 className="font-semibold">Evidence threshold</h2><div className="mt-5 text-4xl font-semibold">{policy?.minimum_coverage_percent ?? 60}%</div><p className="mt-2 text-sm leading-6 text-muted-foreground">Students below this evidence coverage remain visible but are not ranked. Missing evidence never becomes a zero score.</p></Surface></div>;
}

function ClearancePanel() {
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [clearance, setClearance] = useState("all");
  const paging = useCursorPagination(JSON.stringify({ q, clearance }));
  const query = useGetCollegeInternshipClearancePageQuery({ q, clearance, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.student_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number} / {row.roll_number || "No roll number"}</div></div> },
    { key: "program", label: "Program & batch", render: (row) => <div><div>{row.program_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.cohort_name}</div></div> },
    { key: "clearance", label: "Internship clearance", render: (row) => <StatusBadge status={clearanceTone(row.clearance_status)} label={clearanceLabel(row.clearance_status)} /> },
    { key: "freshness", label: "Verified", render: (row) => row.source_updated_at ? dateTime(row.source_updated_at) : "Needs ERP review" },
  ];
  return <div className="space-y-5"><Surface className="p-4 text-sm leading-6 text-muted-foreground"><strong className="text-foreground">Clearance is an eligibility signal, not a billing workflow.</strong> Placement staff see only whether the authoritative College record permits internship participation.</Surface><Surface className="overflow-hidden"><PanelToolbar title="Internship eligibility clearance" /><FilterBar className="rounded-none border-x-0 border-t"><SearchField value={search} onChange={setSearch} placeholder="Search student or admission number" /><Select value={clearance} onValueChange={setClearance}><SelectTrigger className="w-full sm:w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All clearance states</SelectItem><SelectItem value="cleared">Cleared</SelectItem><SelectItem value="pending">Pending</SelectItem><SelectItem value="needs_review">Needs review</SelectItem></SelectContent></Select></FilterBar><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant="section" alignment="left" icon={CheckCircle} title="No students match this clearance view" description="Clear the filters or refresh authoritative ERP evidence." />} /><ListFooter query={query} paging={paging} noun="students" /></Surface></div>;
}

function AttendanceRegisterDrawer({ session, onClose }) {
  const [search, setSearch] = useState("");
  const [changes, setChanges] = useState({});
  const [rowErrors, setRowErrors] = useState({});
  const [formError, setFormError] = useState("");
  const submitLock = useRef(false);
  const q = useDeferredValue(search.trim());
  const paging = useCursorPagination(JSON.stringify({ id: session?.id, q }));
  const query = useGetCollegeAttendanceRegisterQuery({ sessionId: session?.id, q, cursor: paging.cursor, limit: 50 }, { skip: !session?.id });
  const rows = usePagedData(query, paging);
  const [save, saveState] = useSaveCollegeAttendanceMutation();
  useEffect(() => { if (!session) { setSearch(""); setChanges({}); setRowErrors({}); setFormError(""); } }, [session]);
  const submit = async () => {
    const records = Object.entries(changes).map(([student_profile_id, value]) => ({ student_profile_id, status: value.status, note: value.note || null }));
    if (!records.length) return;
    const errors = {};
    records.forEach((record) => {
      const parsed = attendanceRecordSchema.safeParse(record);
      if (!parsed.success) errors[record.student_profile_id] = parsed.error.issues[0]?.message || "Invalid attendance value";
    });
    setRowErrors(errors);
    if (Object.keys(errors).length || submitLock.current) return;
    submitLock.current = true;
    setFormError("");
    try { await save({ sessionId: session.id, records }).unwrap(); toast.success("Attendance changes saved"); setChanges({}); setRowErrors({}); paging.reset(); query.refetch(); }
    catch (error) { setFormError(normalizeApiError(error, "Attendance could not be saved").message); }
    finally { submitLock.current = false; }
  };
  return <DrawerForm open={Boolean(session)} onOpenChange={(open) => { if (!open && !saveState.isLoading) onClose(); }} title={session ? `Attendance / ${session.course_name}` : "Attendance register"} description={query.data?.summary ? `${query.data.summary.recorded} recorded / ${query.data.summary.unrecorded} remaining` : "Paged student register"}><div className="space-y-4"><SearchField value={search} onChange={setSearch} placeholder="Search student" /><div className="divide-y rounded-xl border">{rows.map((row) => { const value = changes[row.student_profile_id] || row; const error = rowErrors[row.student_profile_id]; return <div key={row.student_profile_id} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center"><div className="min-w-0 flex-1"><div className="font-semibold">{row.student_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number} / {row.roll_number || "No roll number"}</div>{error && <p role="alert" className="mt-1 text-xs font-medium text-destructive">{error}</p>}</div><Select value={value.status} onValueChange={(status) => { setChanges((current) => ({ ...current, [row.student_profile_id]: { ...value, status } })); setRowErrors((current) => ({ ...current, [row.student_profile_id]: undefined })); }}><SelectTrigger className="sm:w-40" aria-invalid={Boolean(error)}><SelectValue /></SelectTrigger><SelectContent>{["unrecorded", "present", "absent", "late", "excused"].map((status) => <SelectItem key={status} value={status} disabled={status === "unrecorded"}>{sentence(status)}</SelectItem>)}</SelectContent></Select></div>; })}</div><ListFooter query={query} paging={paging} noun="students" />{formError && <div role="alert" className="rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">{formError}</div>}<div className="sticky bottom-0 flex flex-col gap-2 border-t bg-card/95 pt-4 backdrop-blur sm:flex-row sm:items-center sm:justify-between"><span className="text-xs text-muted-foreground">{Object.keys(changes).length} unsaved change(s)</span><Button onClick={submit} disabled={!Object.keys(changes).length} loading={saveState.isLoading} loadingText="Saving...">Save attendance</Button></div></div></DrawerForm>;
}

const examCycleSchema = z.object({
  scheme_id: z.string().min(1, "Select an assessment pattern"),
  scheme_component_id: z.string().optional(),
  term_id: z.string().optional(),
  name: z.string().trim().min(2, "Enter a cycle name").max(180),
  code: z.string().trim().min(2, "Enter a cycle code").max(60),
  held_on: z.string().optional(),
  due_on: z.string().optional(),
}).superRefine((value, context) => {
  if (value.held_on && value.due_on && value.due_on < value.held_on) {
    context.addIssue({ code: "custom", path: ["due_on"], message: "Due date cannot be before the assessment date" });
  }
});

function ExamCycleDrawer({ open, onClose }) {
  const schemes = useGetCollegeAssessmentSchemesPageQuery({ limit: 100 }, { skip: !open });
  const activeSchemes = (schemes.data?.items || []).filter((item) => ["active", "frozen"].includes(item.status));
  const [create, mutation] = useCreateCollegeExamCycleMutation();
  const [targets, setTargets] = useState([]);
  const form = useForm({ resolver: zodResolver(examCycleSchema), defaultValues: examCycleDefaults, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, setValue, watch } = form;
  const schemeId = watch("scheme_id");
  const componentId = watch("scheme_component_id");
  const selectedScheme = activeSchemes.find((item) => item.id === schemeId);
  const academic = selectedScheme?.domain === "academic";
  useEffect(() => {
    if (open) { reset(examCycleDefaults); setTargets([]); }
  }, [open, reset]);
  useEffect(() => {
    setValue("scheme_component_id", "", { shouldValidate: true });
    setValue("term_id", "", { shouldValidate: true });
    setTargets([]);
  }, [schemeId, setValue]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    if (academic && !values.scheme_component_id) {
      setError("scheme_component_id", { type: "manual", message: "Select the configured academic component" });
      return;
    }
    if (!targets.length) {
      setError("root.server", { type: "manual", message: `Select at least one ${academic ? "course offering" : "batch or section"}` });
      return;
    }
    try {
      await create({
        scheme_id: values.scheme_id,
        scheme_component_id: values.scheme_component_id || null,
        term_id: values.term_id || null,
        name: values.name,
        code: values.code,
        held_on: values.held_on || null,
        due_on: values.due_on || null,
        offering_ids: academic ? targets.map((item) => item.id) : [],
        cohort_ids: academic ? [] : targets.map((item) => item.id),
      }).unwrap();
      toast.success(`${targets.length} assessment register${targets.length === 1 ? "" : "s"} created from the selected pattern`);
      reset(examCycleDefaults);
      setTargets([]);
      onClose();
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Exam cycle could not be created" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  const pending = formState.isSubmitting || mutation.isLoading;
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Create exam or assessment cycle" description="The selected pattern revision defines every register field, template column, validation rule, and calculation.">
    <Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
      <FormField control={control} name="scheme_id" render={({ field }) => <FormItem><FormLabel>Assessment pattern</FormLabel><Select value={field.value || ""} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue placeholder="Choose an active pattern" /></SelectTrigger></FormControl><SelectContent>{activeSchemes.map((row) => <SelectItem key={row.id} value={row.id}>{row.name} / revision {row.version_number} / {sentence(row.domain)}</SelectItem>)}</SelectContent></Select><FormDescription>Used versions become immutable so historical marks never change calculation rules.</FormDescription><FormMessage /></FormItem>} />
      {!schemes.isLoading && !activeSchemes.length && <div className="rounded-xl border border-warning/30 bg-warning-soft p-4"><div className="font-semibold">No active assessment pattern</div><p className="mt-1 text-xs leading-5 text-muted-foreground">Create and activate a pattern before opening a cycle.</p><Button asChild className="mt-3" size="sm" variant="outline"><Link to="/app/academics?section=assessments&view=patterns">Open assessment patterns</Link></Button></div>}
      {selectedScheme && <Surface className="border bg-surface-subtle/30 p-4 shadow-none"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={selectedScheme.status} /><span className="text-sm font-medium">{selectedScheme.code}</span><span className="text-xs text-muted-foreground">revision {selectedScheme.version_number} / {sentence(selectedScheme.calculation_method)}</span></div><p className="mt-2 text-xs leading-5 text-muted-foreground">{selectedScheme.components.map((item) => item.name).join(", ")}</p></Surface>}
      {academic && <FormField control={control} name="scheme_component_id" render={({ field }) => <FormItem><FormLabel>Configured component</FormLabel><Select value={field.value || ""} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue placeholder="Choose the exam component" /></SelectTrigger></FormControl><SelectContent>{(selectedScheme?.components || []).map((row) => <SelectItem key={row.id} value={row.id}>{row.name}{row.max_marks != null ? ` / ${row.max_marks} max` : ""}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />}
      {academic && <CollegeAcademicReferenceField control={control} name="term_id" label="Academic term (optional)" resource="terms" enabled={open && Boolean(selectedScheme)} filters={{ active: true }} />}
      <div className="grid gap-4 sm:grid-cols-2"><CollegeFormField control={control} name="name" label="Cycle name"><Input /></CollegeFormField><CollegeFormField control={control} name="code" label="Cycle code"><Input /></CollegeFormField><CollegeFormField control={control} name="held_on" label="Held on"><Input type="date" /></CollegeFormField><CollegeFormField control={control} name="due_on" label="Due on"><Input type="date" /></CollegeFormField></div>
      {selectedScheme && <MultiAcademicTargetPicker resource={academic ? "offerings" : "cohorts"} selected={targets} onChange={setTargets} />}
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" className="w-full" disabled={!formState.isValid || !selectedScheme || !targets.length || (academic && !componentId)} loading={pending} loadingText="Creating registers...">Create cycle and {targets.length || 0} register{targets.length === 1 ? "" : "s"}</Button>
    </form></Form>
  </DrawerForm>;
}

function MultiAcademicTargetPicker({ resource, selected, onChange }) {
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const paging = useCursorPagination(`cycle-targets:${resource}:${q}`);
  const args = { q: q || undefined, cursor: paging.cursor || undefined, limit: 25, active: true };
  const offerings = useGetCollegeOfferingsPageQuery(args, { skip: resource !== "offerings" });
  const cohorts = useGetCollegeCohortsPageQuery(args, { skip: resource !== "cohorts" });
  const query = resource === "offerings" ? offerings : cohorts;
  const { accept } = paging;
  useEffect(() => { accept(query.data); }, [accept, query.data]);
  const selectedIds = new Set(selected.map((item) => item.id));
  const toggle = (item, checked) => onChange(checked ? [...selected, item] : selected.filter((current) => current.id !== item.id));
  return <div className="rounded-2xl border">
    <div className="border-b p-4"><FormLabel>{resource === "offerings" ? "Course offerings" : "Batches and sections"}</FormLabel><p className="mt-1 text-xs text-muted-foreground">Select one or more targets. Each target receives its own paged register.</p><Input className="mt-3" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${resource}`} /></div>
    <div className="max-h-72 divide-y overflow-y-auto">{paging.items.map((item) => {
      const label = resource === "offerings" ? (item.display_name || item.course_name || item.course_code) : (item.display_name || item.name);
      const detail = resource === "offerings" ? (item.display_meta || `${item.course_code || "Course"} / ${item.cohort_name || "Batch"}`) : (item.display_meta || `${item.code} / Class of ${item.graduation_year}`);
      return <label key={item.id} className="flex cursor-pointer items-start gap-3 p-3 transition-colors hover:bg-surface-hover"><Checkbox checked={selectedIds.has(item.id)} onCheckedChange={(checked) => toggle(item, checked === true)} /><span className="min-w-0"><span className="block text-sm font-medium">{label}</span><span className="mt-0.5 block text-xs text-muted-foreground">{detail}</span></span></label>;
    })}
      {!query.isLoading && !paging.items.length && <div className="p-4 text-sm text-muted-foreground">No matching {resource}.</div>}
    </div>
    <CursorListFooter count={paging.items.length} noun={resource} hasMore={Boolean(query.data?.next_cursor)} loading={query.isFetching} error={query.isError && paging.items.length > 0} onLoadMore={() => paging.loadMore(query.data?.next_cursor)} onRetry={query.refetch} />
    {selected.length > 0 && <div className="border-t bg-surface-subtle/35 px-4 py-3 text-xs font-medium">{selected.length} selected</div>}
  </div>;
}

function DynamicAssessmentRegisterDrawer({ assessment, onClose }) {
  const [search, setSearch] = useState("");
  const [changes, setChanges] = useState({});
  const [rowErrors, setRowErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [pendingMode, setPendingMode] = useState(null);
  const submitLock = useRef(false);
  const q = useDeferredValue(search.trim());
  const paging = useCursorPagination(JSON.stringify({ id: assessment?.id, q }));
  const query = useGetCollegeAssessmentRegisterQuery({ assessmentId: assessment?.id, q, cursor: paging.cursor, limit: 50 }, { skip: !assessment?.id });
  const rows = usePagedData(query, paging);
  const [save, saveState] = useSaveCollegeScoresMutation();
  const loadedAssessment = query.data?.assessment || assessment;
  const configuredDefinitions = loadedAssessment?.metric_schema || [];
  const definitions = configuredDefinitions.length ? configuredDefinitions : [{
    code: "marks_awarded", name: "Score", metric_type: "number", max_marks: loadedAssessment?.max_marks,
    is_required: false,
  }];
  const isConfigured = configuredDefinitions.length > 0;
  const published = loadedAssessment?.status === "published";
  useEffect(() => {
    if (!assessment) {
      setSearch(""); setChanges({}); setRowErrors({}); setFormError(""); setCorrectionReason("");
    }
  }, [assessment]);

  const valueFor = (row) => {
    if (changes[row.student_profile_id]) return changes[row.student_profile_id];
    const metrics = { ...(row.metrics || {}) };
    if (!isConfigured && row.marks_awarded != null) metrics.marks_awarded = row.marks_awarded;
    if (isConfigured && definitions.length === 1 && row.marks_awarded != null && metrics[definitions[0].code] == null) metrics[definitions[0].code] = row.marks_awarded;
    return { ...row, metrics };
  };
  const changeMetric = (row, definition, raw) => {
    const current = valueFor(row);
    const nextMetrics = { ...(current.metrics || {}), [definition.code]: raw };
    setChanges((values) => ({ ...values, [row.student_profile_id]: { ...current, metrics: nextMetrics } }));
    setRowErrors((values) => ({ ...values, [row.student_profile_id]: undefined }));
  };
  const submit = async (publishScores = false) => {
    const errors = {};
    const scores = Object.values(changes).map((value) => {
      const metrics = {};
      for (const definition of definitions) {
        const raw = value.metrics?.[definition.code];
        const validation = validateDynamicMetric(definition, raw);
        if (validation) errors[value.student_profile_id] = validation;
        else if (raw !== "" && raw != null) metrics[definition.code] = normalizeDynamicMetric(definition, raw);
      }
      return {
        student_profile_id: value.student_profile_id,
        version: value.version || null,
        marks_awarded: isConfigured ? null : (metrics.marks_awarded ?? null),
        grade: value.grade || null,
        feedback: value.feedback || null,
        metrics: isConfigured ? metrics : {},
      };
    });
    if (published && correctionReason.trim().length < 3) setFormError("Explain why these published marks are being corrected.");
    else setFormError("");
    setRowErrors(errors);
    if (Object.keys(errors).length || !scores.length || submitLock.current || (published && correctionReason.trim().length < 3)) return;
    submitLock.current = true;
    setPendingMode(publishScores ? "publish" : "draft");
    try {
      await save({ assessmentId: assessment.id, scores, publish: publishScores, correctionReason: correctionReason.trim() || null }).unwrap();
      toast.success(published ? "Published results corrected with an audit entry" : publishScores ? "Results published" : "Results saved");
      setChanges({}); setRowErrors({}); setCorrectionReason(""); paging.reset(); query.refetch();
    } catch (error) { setFormError(normalizeApiError(error, "Results could not be saved").message); }
    finally { submitLock.current = false; setPendingMode(null); }
  };
  const dirtyCount = Object.keys(changes).length;
  return <DrawerForm open={Boolean(assessment)} onOpenChange={(open) => { if (!open && !saveState.isLoading) onClose(); }} title={assessment?.title || "Assessment register"} description={query.data?.summary ? `${query.data.summary.scored} scored / ${query.data.summary.unscored} remaining` : "Paged student register generated from the configured pattern"}>
    <div className="space-y-4">
      {isConfigured && <Surface className="border bg-surface-subtle/30 p-4 shadow-none"><div className="flex flex-wrap items-center gap-2"><StatusBadge status="active" label={`${definitions.length} configured field${definitions.length === 1 ? "" : "s"}`} />{assessment?.scheme_snapshot?.scheme_code && <span className="text-xs text-muted-foreground">{assessment.scheme_snapshot.scheme_code} / revision {assessment.scheme_snapshot.scheme_version}</span>}</div><p className="mt-2 text-xs leading-5 text-muted-foreground">{definitions.map((item) => `${item.name}${item.max_marks != null ? ` / ${item.max_marks}` : ""}`).join("; ")}</p></Surface>}
      <SearchField value={search} onChange={setSearch} placeholder="Search student" />
      {query.isError && !rows.length ? <ErrorState title="Assessment register could not be loaded" retry={query.refetch} /> : <div className="divide-y rounded-xl border">{rows.map((row) => {
        const value = valueFor(row);
        const error = rowErrors[row.student_profile_id];
        return <div key={row.student_profile_id} className="space-y-3 p-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"><div><div className="font-semibold">{row.student_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number}{row.roll_number ? ` / ${row.roll_number}` : ""}</div></div>{row.calculated_score != null && <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium">Calculated {row.calculated_score}</span>}</div>
          <div className="grid gap-3 sm:grid-cols-2">{definitions.map((definition) => <DynamicMetricInput key={definition.code} definition={definition} studentName={row.student_name} value={value.metrics?.[definition.code] ?? ""} onChange={(next) => changeMetric(row, definition, next)} invalid={Boolean(error)} />)}</div>
          {error && <p role="alert" className="text-xs font-medium text-destructive">{error}</p>}
        </div>;
      })}</div>}
      <ListFooter query={query} paging={paging} noun="students" />
      {published && <div className="rounded-xl border border-warning/30 bg-warning-soft p-4"><Label htmlFor="published-correction-reason">Correction reason</Label><Textarea id="published-correction-reason" className="mt-2 bg-card" value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} rows={3} placeholder="Required because these results are already published" /><p className="mt-2 text-xs leading-5 text-muted-foreground">The before and after values, reason, and responsible staff member are retained in the audit log.</p></div>}
      {formError && <div role="alert" className="rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">{formError}</div>}
      <div className="sticky bottom-0 flex flex-col gap-2 border-t bg-card/95 pt-4 backdrop-blur sm:flex-row sm:items-center sm:justify-between"><span className="text-xs text-muted-foreground">{dirtyCount} unsaved change(s)</span><div className="flex gap-2"><Button variant="outline" onClick={() => submit(false)} disabled={!dirtyCount || Boolean(pendingMode) || (published && correctionReason.trim().length < 3)} loading={pendingMode === "draft"} loadingText="Saving...">{published ? "Save corrections" : "Save draft"}</Button>{!published && <Button onClick={() => submit(true)} disabled={!dirtyCount || Boolean(pendingMode)} loading={pendingMode === "publish"} loadingText="Publishing...">Publish</Button>}</div></div>
    </div>
  </DrawerForm>;
}

function DynamicMetricInput({ definition, studentName, value, onChange, invalid }) {
  const label = `${definition.name}${definition.max_marks != null ? ` / ${definition.max_marks}` : ""}${definition.is_required ? " *" : ""}`;
  if (definition.metric_type === "boolean") return <div className="space-y-1.5"><Label>{label}</Label><Select value={value === "" || value == null ? "unset" : String(value)} onValueChange={(next) => onChange(next === "unset" ? "" : next === "true")}><SelectTrigger aria-invalid={invalid}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="unset">Not recorded</SelectItem><SelectItem value="true">Yes</SelectItem><SelectItem value="false">No</SelectItem></SelectContent></Select></div>;
  const numeric = ["number", "percentage", "integer", "rank", "count"].includes(definition.metric_type);
  return <div className="space-y-1.5"><Label htmlFor={`${definition.code}-${studentName}`}>{label}</Label><Input id={`${definition.code}-${studentName}`} type={numeric ? "number" : "text"} inputMode={numeric ? "decimal" : undefined} min={numeric ? 0 : undefined} max={definition.max_marks ?? undefined} step={["integer", "rank", "count"].includes(definition.metric_type) ? 1 : "any"} maxLength={numeric ? undefined : 140} aria-invalid={invalid} value={value} onChange={(event) => onChange(event.target.value)} placeholder={sentence(definition.metric_type)} /></div>;
}

function validateDynamicMetric(definition, raw) {
  if (raw === "" || raw == null) return definition.is_required ? `${definition.name} is required` : null;
  if (["number", "percentage", "integer", "rank", "count"].includes(definition.metric_type)) {
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) return `${definition.name} must be a valid non-negative number`;
    if (["integer", "rank", "count"].includes(definition.metric_type) && !Number.isInteger(value)) return `${definition.name} must be a whole number`;
    if (definition.max_marks != null && value > Number(definition.max_marks)) return `${definition.name} cannot exceed ${definition.max_marks}`;
  }
  return null;
}

function normalizeDynamicMetric(definition, raw) {
  if (definition.metric_type === "boolean") return Boolean(raw);
  if (["number", "percentage", "integer", "rank", "count"].includes(definition.metric_type)) return Number(raw);
  return String(raw).trim();
}

function CompanyDrawer({ open, onClose }) {
  const [create, state] = useCreateCollegeCompanyMutation();
  const form = useForm({ resolver: zodResolver(companySchema), defaultValues: companyDefaults, ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (open) reset(companyDefaults); }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try { await create(values).unwrap(); toast.success("Company added"); reset(companyDefaults); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "Company could not be added" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Add recruiting company" description="Create the employer once, then connect opportunities and outcomes."><Form {...form}><form noValidate onSubmit={submit} className="space-y-4"><CollegeFormField control={control} name="name" label="Company name"><Input autoFocus /></CollegeFormField><div className="grid gap-4 sm:grid-cols-2"><CollegeFormField control={control} name="industry" label="Industry"><Input /></CollegeFormField><CollegeFormField control={control} name="website" label="Website"><Input type="url" /></CollegeFormField><CollegeFormField control={control} name="contact_name" label="Contact name"><Input /></CollegeFormField><CollegeFormField control={control} name="contact_email" label="Contact email"><Input type="email" /></CollegeFormField><CollegeFormField control={control} name="contact_phone" label="Contact phone"><Input inputMode="tel" /></CollegeFormField></div><CollegeFormField control={control} name="notes" label="Internal note"><Textarea rows={3} /></CollegeFormField><FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" loading={pending} loadingText="Adding...">Add company</Button></form></Form></DrawerForm>;
}

function DriveDrawer({ open, onClose }) {
  const [companySearch, setCompanySearch] = useState("");
  const companies = useGetCollegeCompaniesQuery({ q: companySearch, limit: 25 }, { skip: !open });
  const [create, state] = useCreateCollegeOpportunityMutation();
  const form = useForm({ resolver: zodResolver(collegeDriveSchema), defaultValues: driveDefaults, ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (open) { reset(driveDefaults); setCompanySearch(""); } }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try { await create(values).unwrap(); toast.success("Placement drive created"); reset(driveDefaults); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "Drive could not be created" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Create placement drive" description="Set only the evidence rules this opportunity genuinely requires."><Form {...form}><form noValidate onSubmit={submit} className="space-y-5">
    <div className="space-y-2"><label className="text-sm font-medium" htmlFor="company-search">Find company</label><Input id="company-search" value={companySearch} onChange={(event) => setCompanySearch(event.target.value)} placeholder="Search employer" /></div>
    <FormField control={control} name="company_id" render={({ field }) => <FormItem><FormLabel>Company</FormLabel><Select value={field.value} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue placeholder="Choose company" /></SelectTrigger></FormControl><SelectContent>{(companies.data?.items || []).map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />
    <CollegeFormField control={control} name="title" label="Opportunity title"><Input /></CollegeFormField>
    <div className="grid gap-4 sm:grid-cols-2">
      <CollegeSelectField control={control} name="opportunity_type" label="Type" values={["campus_drive", "internship", "off_campus", "apprenticeship"]} />
      <CollegeSelectField control={control} name="status" label="Status" values={["draft", "published", "active"]} />
      <CollegeFormField control={control} name="deadline_at" label="Application deadline"><Input type="datetime-local" /></CollegeFormField>
      <CollegeFormField control={control} name="drive_at" label="Drive date"><Input type="datetime-local" /></CollegeFormField>
      <CollegeFormField control={control} name="work_location" label="Work location"><Input /></CollegeFormField>
      <CollegeFormField control={control} name="employment_type" label="Employment type"><Input /></CollegeFormField>
      <CollegeFormField control={control} name="package_min" label="Minimum package (INR)"><Input inputMode="decimal" /></CollegeFormField>
      <CollegeFormField control={control} name="package_max" label="Maximum package (INR)"><Input inputMode="decimal" /></CollegeFormField>
    </div>
    <div className="border-t pt-4"><h3 className="text-sm font-semibold">Eligibility evidence</h3><div className="mt-3 grid gap-4 sm:grid-cols-2"><CollegeFormField control={control} name="minimum_cgpa" label="Minimum CGPA"><Input inputMode="decimal" /></CollegeFormField><CollegeFormField control={control} name="maximum_active_backlogs" label="Maximum active backlogs"><Input inputMode="numeric" /></CollegeFormField><CollegeFormField control={control} name="minimum_attendance" label="Minimum attendance %"><Input inputMode="decimal" /></CollegeFormField><CollegeFormField control={control} name="minimum_solved" label="Minimum solved problems"><Input inputMode="numeric" /></CollegeFormField></div></div>
    <FormRootError error={formState.errors.root?.server} />
    <Button type="submit" className="w-full" loading={pending} loadingText="Creating...">Create drive</Button>
  </form></Form></DrawerForm>;
}

function LegacyDriveDrawer({ open, onClose }) {
  const [companySearch, setCompanySearch] = useState("");
  const companies = useGetCollegeCompaniesQuery({ q: companySearch, limit: 25 }, { skip: !open });
  const [form, setForm] = useState({ company_id: "", title: "", opportunity_type: "campus_drive", status: "active", deadline_at: "", drive_at: "", work_location: "", employment_type: "", package_min: "", package_max: "", minimum_cgpa: "", maximum_active_backlogs: "", minimum_attendance: "", minimum_solved: "" });
  const [create, state] = useCreateCollegeOpportunityMutation();
  const submit = async (event) => {
    event.preventDefault();
    const eligibility_rules = {};
    ["minimum_cgpa", "maximum_active_backlogs", "minimum_attendance", "minimum_solved"].forEach((key) => { if (form[key] !== "") eligibility_rules[key] = Number(form[key]); });
    try { await create({ ...nulls(form), package_min_paise: form.package_min ? Number(form.package_min) * 100 : null, package_max_paise: form.package_max ? Number(form.package_max) * 100 : null, deadline_at: datePayload(form.deadline_at), drive_at: datePayload(form.drive_at), eligibility_rules, rounds: [] }).unwrap(); toast.success("Placement drive created"); onClose(); }
    catch (error) { toast.error(error?.data?.detail || "Drive could not be created"); }
  };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title="Create placement drive" description="Set only the evidence rules this opportunity genuinely requires."><form onSubmit={submit} className="space-y-5"><Field label="Find company"><Input value={companySearch} onChange={(event) => setCompanySearch(event.target.value)} placeholder="Search employer" /></Field><Field label="Company"><ReferenceSelect value={form.company_id} onChange={(value) => setForm({ ...form, company_id: value })} rows={companies.data?.items || []} placeholder="Choose company" /></Field><Field label="Opportunity title"><Input required value={form.title} onChange={field(setForm, "title")} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Type"><SimpleSelect value={form.opportunity_type} onChange={(value) => setForm({ ...form, opportunity_type: value })} values={["campus_drive", "internship", "off_campus", "apprenticeship"]} /></Field><Field label="Status"><SimpleSelect value={form.status} onChange={(value) => setForm({ ...form, status: value })} values={["draft", "published", "active"]} /></Field><Field label="Application deadline"><Input type="datetime-local" value={form.deadline_at} onChange={field(setForm, "deadline_at")} /></Field><Field label="Drive date"><Input type="datetime-local" value={form.drive_at} onChange={field(setForm, "drive_at")} /></Field><Field label="Minimum package (INR)"><Input type="number" min="0" value={form.package_min} onChange={field(setForm, "package_min")} /></Field><Field label="Maximum package (INR)"><Input type="number" min="0" value={form.package_max} onChange={field(setForm, "package_max")} /></Field></div><div className="border-t pt-4"><h3 className="text-sm font-semibold">Eligibility evidence</h3><div className="mt-3 grid gap-4 sm:grid-cols-2"><Field label="Minimum CGPA"><Input type="number" step=".01" min="0" max="10" value={form.minimum_cgpa} onChange={field(setForm, "minimum_cgpa")} /></Field><Field label="Maximum active backlogs"><Input type="number" min="0" value={form.maximum_active_backlogs} onChange={field(setForm, "maximum_active_backlogs")} /></Field><Field label="Minimum attendance %"><Input type="number" min="0" max="100" value={form.minimum_attendance} onChange={field(setForm, "minimum_attendance")} /></Field><Field label="Minimum solved problems"><Input type="number" min="0" value={form.minimum_solved} onChange={field(setForm, "minimum_solved")} /></Field></div></div><Button className="w-full" disabled={state.isLoading || !form.company_id}>{state.isLoading ? "Creating..." : "Create drive"}</Button></form></DrawerForm>;
}

function ApplicationDrawer({ open, onClose }) {
  const [studentSearch, setStudentSearch] = useState("");
  const [driveSearch, setDriveSearch] = useState("");
  const students = useGetCollegeStudentIntelligenceQuery({ q: studentSearch, limit: 25 }, { skip: !open });
  const drives = useGetCollegeOpportunitiesQuery({ q: driveSearch, status: "active", limit: 25 }, { skip: !open });
  const [create, state] = useCreateCollegeApplicationMutation();
  const form = useForm({ resolver: zodResolver(collegeApplicationSchema), defaultValues: applicationDefaults, ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (open) { reset(applicationDefaults); setStudentSearch(""); setDriveSearch(""); } }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try { await create(values).unwrap(); toast.success("Application created"); reset(applicationDefaults); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "Application could not be created" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Add student to opportunity" description="Eligibility is recalculated from current evidence before the application is created."><Form {...form}><form noValidate onSubmit={submit} className="space-y-4"><div className="space-y-2"><label className="text-sm font-medium" htmlFor="drive-search">Find opportunity</label><Input id="drive-search" value={driveSearch} onChange={(event) => setDriveSearch(event.target.value)} /></div><CollegeReferenceField control={control} name="opportunity_id" label="Opportunity" rows={drives.data?.items || []} getLabel={(row) => `${row.title} / ${row.company?.name}`} placeholder="Choose opportunity" /><div className="space-y-2"><label className="text-sm font-medium" htmlFor="student-search">Find student</label><Input id="student-search" value={studentSearch} onChange={(event) => setStudentSearch(event.target.value)} /></div><CollegeReferenceField control={control} name="student_profile_id" label="Student" rows={students.data?.items || []} getLabel={(row) => `${row.name} / ${row.admission_number}`} placeholder="Choose student" /><CollegeFormField control={control} name="notes" label="Internal note"><Textarea rows={3} /></CollegeFormField><FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" loading={pending} loadingText="Checking eligibility...">Create application</Button></form></Form></DrawerForm>;
}

function AttendanceSessionDrawer({ open, onClose }) {
  const [create, state] = useCreateCollegeAttendanceMutation();
  const form = useForm({ resolver: zodResolver(attendanceSessionSchema), defaultValues: attendanceSessionDefaults(), ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (open) reset(attendanceSessionDefaults()); }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try { await create({ ...values, starts_at: values.starts_at || null, ends_at: values.ends_at || null, records: [] }).unwrap(); toast.success("Attendance session created"); reset(attendanceSessionDefaults()); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "Session could not be created" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Create local attendance session" description="Use only when authoritative ERP attendance is unavailable."><Form {...form}><form noValidate onSubmit={submit} className="space-y-4"><CollegeAcademicReferenceField control={control} name="offering_id" label="Course offering" resource="offerings" enabled={open} filters={{ status: "active" }} /><div className="grid gap-4 sm:grid-cols-2"><CollegeFormField control={control} name="held_on" label="Held on"><Input type="date" /></CollegeFormField><CollegeFormField control={control} name="topic" label="Topic"><Input /></CollegeFormField><CollegeFormField control={control} name="starts_at" label="Starts"><Input type="time" /></CollegeFormField><CollegeFormField control={control} name="ends_at" label="Ends"><Input type="time" /></CollegeFormField></div><FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" loading={pending} loadingText="Creating..." disabled={!formState.isValid}>Create session</Button></form></Form></DrawerForm>;
}

function ConnectorDrawer({ open, connector, onClose }) {
  const [create, state] = useCreateCollegeIntegrationMutation();
  const [update, updateState] = useUpdateCollegeIntegrationMutation();
  const form = useForm({ resolver: zodResolver(collegeConnectorSchema), defaultValues: connectorDefaults(), ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError, watch } = form;
  const authMode = watch("auth_mode");
  const paginationMode = watch("pagination_mode");
  useEffect(() => { if (open) reset(connectorDefaults(connector)); }, [connector, open, reset]);
  const pending = formState.isSubmitting || state.isLoading || updateState.isLoading;
  const submit = handleSubmit(async (values) => {
    const overrides = values.mapping_json ? JSON.parse(values.mapping_json) : {};
    const sourceMappings = overrides.resources || overrides;
    const resources = Object.fromEntries(values.resources.map((resource) => [resource, {
      path: `/${resource.replaceAll("_", "-")}`,
      root_path: "data",
      ...(sourceMappings[resource] || {}),
    }]));
    const pagination = values.pagination_mode === "none" ? {} : {
      mode: values.pagination_mode,
      cursor_param: values.cursor_param || "cursor",
      updated_since_param: values.updated_since_param || "updated_since",
      next_url_path: values.next_url_path || undefined,
      cursor_path: values.cursor_path || undefined,
    };
    const payload = {
      name: values.name,
      base_url: values.base_url,
      auth_mode: values.auth_mode,
      auth_header: values.auth_header || null,
      api_key: values.api_key,
      sync_interval_hours: values.sync_interval_hours,
      mapping: { resources },
      pagination,
    };
    try { await (connector ? update({ connectorId: connector.id, ...payload }) : create(payload)).unwrap(); toast.success(`ERP connector ${connector ? "updated" : "saved"}`); reset(connectorDefaults()); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "ERP connector could not be saved" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title={connector ? "Edit College ERP" : "Connect College ERP"} description="Configure a scoped, credential-protected read-only HTTPS source."><Form {...form}><form noValidate onSubmit={submit} className="space-y-5">
    <div className="grid gap-4 sm:grid-cols-2"><CollegeFormField control={control} name="name" label="Connection name"><Input /></CollegeFormField><CollegeFormField control={control} name="base_url" label="HTTPS base URL"><Input type="url" /></CollegeFormField></div>
    <div className="grid gap-4 sm:grid-cols-2"><CollegeSelectField control={control} name="auth_mode" label="Authentication" values={["bearer", "header"]} />{authMode === "header" && <CollegeFormField control={control} name="auth_header" label="Header name"><Input /></CollegeFormField>}<CollegeFormField control={control} name="sync_interval_hours" label="Sync interval (hours)"><Input inputMode="numeric" /></CollegeFormField></div>
    <CollegeFormField control={control} name="api_key" label={connector ? "Replace API key (optional)" : "API key"} description={connector ? "Leave blank to keep the existing encrypted key." : "Stored securely and never returned to the browser."}><Input type="password" autoComplete="off" /></CollegeFormField>
    <FormField control={control} name="resources" render={({ field }) => <FormItem><FormLabel>Authoritative resources</FormLabel><FormDescription>Choose only data this ERP actually provides. Unselected endpoints are never called.</FormDescription><div className="grid gap-2 sm:grid-cols-2">{PUSH_RESOURCES.map((resource) => {
      const checked = field.value?.includes(resource);
      return <label key={resource} className="flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors hover:bg-secondary/40"><Checkbox checked={checked} onCheckedChange={(next) => field.onChange(next ? [...(field.value || []), resource] : (field.value || []).filter((item) => item !== resource))} /><span><span className="block text-sm font-medium">{sentence(resource)}</span><span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{pushScopeDescription(resource)}</span></span></label>;
    })}</div><FormMessage /></FormItem>} />
    <Surface className="space-y-4 bg-secondary/20 p-4 shadow-none"><div><div className="text-sm font-semibold">Pagination</div><p className="mt-1 text-xs leading-5 text-muted-foreground">Match the ERP’s real paging contract. Leave disabled for bounded endpoints.</p></div><CollegeSelectField control={control} name="pagination_mode" label="Paging method" values={["none", "cursor", "updated_since"]} />{paginationMode !== "none" && <div className="grid gap-4 sm:grid-cols-2"><CollegeFormField control={control} name="cursor_param" label="Cursor parameter"><Input placeholder="cursor" /></CollegeFormField><CollegeFormField control={control} name="updated_since_param" label="Updated-since parameter"><Input placeholder="updated_since" /></CollegeFormField><CollegeFormField control={control} name="next_url_path" label="Next URL response path"><Input placeholder="meta.next" /></CollegeFormField><CollegeFormField control={control} name="cursor_path" label="Next cursor response path"><Input placeholder="meta.next_cursor" /></CollegeFormField></div>}</Surface>
    <FormField control={control} name="mapping_json" render={({ field }) => <FormItem><FormLabel>Advanced resource mapping (optional)</FormLabel><FormDescription>JSON keys are selected resource names. Map source paths to canonical fields; assessment marks may send a dynamic metrics object or map institution metric codes under <code>metrics</code>.</FormDescription><FormControl><Textarea {...field} className="min-h-40 font-mono text-xs" spellCheck={false} placeholder={'{\n  "assessment_marks": {\n    "path": "/assessment-results",\n    "root_path": "data",\n    "fields": { "metrics": "scores" },\n    "metrics": { "YOUR_METRIC_CODE": "scores.custom_field" }\n  }\n}'} /></FormControl><FormMessage /></FormItem>} />
    <FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" disabled={!formState.isValid} loading={pending} loadingText="Saving...">{connector ? "Save connector changes" : "Save connector"}</Button>
  </form></Form></DrawerForm>;
}

const PUSH_RESOURCES = ["departments", "programs", "terms", "cohorts", "courses", "students", "term_results", "attendance", "skills", "exam_cycles", "assessment_marks", "internship_clearance"];

function CredentialDrawer({ open, onClose, onCreated }) {
  const [create, state] = useCreateCollegeIntegrationCredentialMutation();
  const form = useForm({ resolver: zodResolver(collegePushCredentialSchema), defaultValues: { name: "", scopes: ["students"], expires_at: credentialExpiryValue() }, ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (open) reset({ name: "", scopes: ["students"], expires_at: credentialExpiryValue() }); }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try {
      const result = await create({ name: values.name, scopes: values.scopes, expires_at: new Date(values.expires_at).toISOString() }).unwrap();
      toast.success("Push credential created");
      reset();
      onCreated(result);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Push credential could not be created" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Create ERP push credential" description="Choose only the authoritative evidence this ERP is allowed to send.">
    <Form {...form}><form noValidate onSubmit={submit} className="space-y-5">
      <CollegeFormField control={control} name="name" label="Credential name" description="Use a recognizable system or environment name."><Input autoComplete="off" /></CollegeFormField>
      <FormField control={control} name="scopes" render={({ field }) => <FormItem><FormLabel>Resource scopes</FormLabel><div className="grid gap-2 sm:grid-cols-2">{PUSH_RESOURCES.map((resource) => {
        const checked = field.value?.includes(resource);
        return <label key={resource} className="flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors hover:bg-secondary/40"><Checkbox checked={checked} onCheckedChange={(next) => field.onChange(next ? [...(field.value || []), resource] : (field.value || []).filter((item) => item !== resource))} /><span><span className="block text-sm font-medium">{sentence(resource)}</span><span className="mt-0.5 block text-xs text-muted-foreground">{pushScopeDescription(resource)}</span></span></label>;
      })}</div><FormMessage /></FormItem>} />
      <CollegeFormField control={control} name="expires_at" label="Credential expiry" description="Maximum lifetime is two years. Shorter credentials reduce integration risk."><Input type="datetime-local" /></CollegeFormField>
      <Surface className="flex items-start gap-3 bg-secondary/35 p-4"><ShieldCheck className="mt-0.5 shrink-0" /><p className="text-xs leading-5 text-muted-foreground">The secret appears once after creation. Edvatiq stores only its cryptographic hash and never includes the full value in logs or later responses.</p></Surface>
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" className="w-full" loading={pending} loadingText="Creating...">Create and reveal secret</Button>
    </form></Form>
  </DrawerForm>;
}

function SecretDialog({ secret, onClose }) {
  const copy = async () => {
    try { await navigator.clipboard.writeText(secret.value); toast.success("Credential copied"); }
    catch { toast.error("Copy failed. Select the credential manually"); }
  };
  return <Dialog open={Boolean(secret)} onOpenChange={(open) => { if (!open) onClose(); }}><DialogContent className="sm:max-w-2xl"><DialogHeader><DialogTitle>{secret?.rotated ? "Replacement credential" : "ERP push credential created"}</DialogTitle><DialogDescription>This is the only time the complete secret will be displayed.</DialogDescription></DialogHeader>{secret && <div className="space-y-4"><div className="rounded-xl border border-warning/30 bg-warning-soft p-4 text-sm"><strong>Store it now.</strong> Closing this dialog permanently hides the secret. Create or rotate the credential if it is lost.</div><div><div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{secret.name}</div><div className="mt-2 flex items-start gap-2"><code className="min-w-0 flex-1 break-all rounded-xl bg-foreground p-4 text-xs leading-6 text-background">{secret.value}</code><Button variant="outline" size="icon" onClick={copy} aria-label="Copy credential"><Copy /></Button></div></div><div className="flex justify-end"><Button onClick={onClose}>I have stored it</Button></div></div>}</DialogContent></Dialog>;
}

function CollegeFormField({ control, name, label, description, children }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl>{description && <FormDescription>{description}</FormDescription>}<FormMessage /></FormItem>} />;
}

function CollegeSelectField({ control, name, label, values }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><Select value={field.value} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl><SelectContent>{values.map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />;
}

function CollegeReferenceField({ control, name, label, rows, getLabel = (row) => row.name, placeholder }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><Select value={field.value} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue placeholder={placeholder} /></SelectTrigger></FormControl><SelectContent>{rows.map((row) => <SelectItem key={row.id} value={row.id}>{getLabel(row)}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />;
}

function CollegeAcademicReferenceField({ control, name, label, resource, enabled, filters }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl><AcademicResourceCombobox resource={resource} value={field.value || ""} onValueChange={field.onChange} enabled={enabled} filters={filters} placeholder={`Choose ${label.toLowerCase()}`} /></FormControl><FormMessage /></FormItem>} />;
}

const companyDefaults = { name: "", industry: "", website: "", contact_name: "", contact_email: "", contact_phone: "", notes: "" };
const driveDefaults = { company_id: "", title: "", opportunity_type: "campus_drive", status: "active", deadline_at: "", drive_at: "", work_location: "", employment_type: "", package_min: "", package_max: "", minimum_cgpa: "", maximum_active_backlogs: "", minimum_attendance: "", minimum_solved: "" };
const applicationDefaults = { opportunity_id: "", student_profile_id: "", notes: "" };
const examCycleDefaults = { scheme_id: "", scheme_component_id: "", term_id: "", name: "", code: "", held_on: "", due_on: "" };
function connectorDefaults(connector) {
  const mapping = connector?.mapping?.resources || connector?.mapping || {};
  const pagination = connector?.pagination || {};
  return {
    name: connector?.name || "", base_url: connector?.base_url || "",
    auth_mode: connector?.auth_mode || "bearer", auth_header: connector?.auth_header || "",
    api_key: "", has_existing_key: Boolean(connector?.api_key_configured),
    sync_interval_hours: String(connector?.sync_interval_hours || 6),
    resources: connector?.resource_types?.length ? connector.resource_types : ["students", "term_results", "attendance"],
    mapping_json: connector ? JSON.stringify(mapping, null, 2) : "",
    pagination_mode: pagination.mode || "none", cursor_param: pagination.cursor_param || "cursor",
    updated_since_param: pagination.updated_since_param || "updated_since",
    next_url_path: pagination.next_url_path || "", cursor_path: pagination.cursor_path || "",
  };
}
function attendanceSessionDefaults() { return { offering_id: "", held_on: isoToday(), starts_at: "", ends_at: "", topic: "" }; }

function OwnershipNotice() { return <Surface className="flex items-start gap-3 p-4"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Database /></span><div><div className="text-sm font-semibold">Your College ERP remains authoritative</div><p className="mt-1 text-xs leading-5 text-muted-foreground">Edvatiq validates academic evidence, adds placement intelligence, and never deletes local records because they disappear from a source response.</p></div></Surface>; }
function PanelToolbar({ title, action }) { return <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5"><h2 className="font-semibold">{title}</h2>{action}</div>; }
function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function ReferenceSelect({ value, onChange, rows, placeholder, label = (row) => row.name }) { return <Select value={value} onValueChange={onChange}><SelectTrigger><SelectValue placeholder={placeholder} /></SelectTrigger><SelectContent>{rows.map((row) => <SelectItem key={row.id} value={row.id}>{label(row)}</SelectItem>)}</SelectContent></Select>; }
function SimpleSelect({ value, onChange, values }) { return <Select value={value} onValueChange={onChange}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{values.map((item) => <SelectItem key={item} value={item}>{sentence(item)}</SelectItem>)}</SelectContent></Select>; }
function field(setter, key) { return (event) => setter((current) => ({ ...current, [key]: event.target.value })); }
function nulls(value) { return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, item === "" ? null : item])); }
function datePayload(value) { return value ? new Date(value).toISOString() : null; }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function percent(value) { return `${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 1 })}%`; }
function shortDate(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "Not scheduled"; }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)) : "Not scheduled"; }
function relativeTime(value) {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "not available";
  const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60000));
  if (minutes < 60) return minutes <= 1 ? "just now" : `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
function academicScopeContext({ departmentId, programId, cohortId, domain = "academics" }) {
  if (!departmentId && !programId && !cohortId) return null;
  return {
    kind: "college_scope",
    id: cohortId ? `cohort:${cohortId}` : programId ? `program:${programId}` : `department:${departmentId}`,
    label: "Selected academic scope",
    domain,
    department_id: departmentId || undefined,
    program_id: programId || undefined,
    cohort_id: cohortId || undefined,
  };
}
function isoToday() { return new Date().toISOString().slice(0, 10); }
function credentialExpiryValue(value) {
  let date = value ? new Date(value) : new Date(Date.now() + 90 * 24 * 60 * 60 * 1000);
  if (Number.isNaN(date.getTime()) || date.getTime() <= Date.now() + 5 * 60 * 1000) date = new Date(Date.now() + 90 * 24 * 60 * 60 * 1000);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60 * 1000);
  return local.toISOString().slice(0, 16);
}
function pushScopeDescription(resource) {
  const descriptions = {
    departments: "Department names and institution-defined codes",
    programs: "Programs linked by department code",
    terms: "Academic years and teaching periods",
    cohorts: "Graduation batches and normalized sections",
    courses: "Courses linked by department code",
    students: "Identity and cohort records",
    term_results: "Academic term outcomes",
    attendance: "Course or term attendance evidence",
    skills: "Verified student skills",
    exam_cycles: "Configured exam cycles linked to an immutable pattern version",
    assessment_marks: "Cycle-bound metrics using the College's frozen assessment pattern",
    internship_clearance: "Cleared, pending, or needs review only",
  };
  return descriptions[resource];
}
function money(value) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value || 0) / 100); }
function packageRange(row) { if (!row.package_min_paise && !row.package_max_paise) return "Not disclosed"; return row.package_min_paise === row.package_max_paise ? money(row.package_min_paise) : `${money(row.package_min_paise)} - ${money(row.package_max_paise)}`; }
function studentEvidenceCell(row) { return <div><div className="font-semibold">{row.student_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number} / {row.cohort_name}</div></div>; }
function readinessTone(value) { return value === "ready" ? "active" : value === "needs_support" ? "warning" : value === "developing" ? "scheduled" : "pending"; }
function eligibilityTone(value) { return value === "eligible" ? "active" : value === "ineligible" ? "warning" : "pending"; }
function clearanceTone(value) { return value === "cleared" ? "active" : value === "pending" ? "warning" : "pending"; }
function clearanceLabel(value) { return value === "cleared" ? "Cleared" : value === "pending" ? "Action needed" : "Needs review"; }
function leaderboardColumns(board) {
  if (board === "coding") return [{ key: "solved", label: "Solved", render: (row) => row.total_solved ?? "-" }, { key: "rating", label: "Contest rating", render: (row) => row.contest_rating ?? "-" }, { key: "fresh", label: "Updated", render: (row) => shortDate(row.captured_at) }];
  if (board === "academics") return [{ key: "cgpa", label: "CGPA", render: (row) => row.cgpa ?? "-" }, { key: "backlogs", label: "Backlogs", render: (row) => row.active_backlogs ?? "-" }];
  if (board === "improvement") return [{ key: "solved", label: "Solved change", render: (row) => row.solved_change == null ? "-" : `+${row.solved_change}` }, { key: "readiness", label: "Readiness change", render: (row) => row.readiness_change == null ? "-" : `${row.readiness_change > 0 ? "+" : ""}${row.readiness_change}` }];
  return [{ key: "score", label: "Score", render: (row) => row.score == null ? "-" : `${row.score}%` }, { key: "coverage", label: "Evidence", render: (row) => `${row.coverage_percent}%` }, { key: "band", label: "Band", render: (row) => <StatusBadge status={readinessTone(row.band)} label={row.rankable ? sentence(row.band) : "Insufficient evidence"} /> }];
}
function aiPrompt(section) {
  const prompts = {
    pipeline: "Summarize the placement pipeline and show the applications that need a next action.",
    drives: "Which active placement drives need attention, and why?",
    applications: "Find stalled applications and explain the evidence behind each recommendation.",
    companies: "Summarize placement outcomes by recruiting company.",
    readiness: "Which students need placement support, based on current evidence?",
    coding: "Compare recent coding improvement without ignoring academic and profile evidence.",
    leaderboards: "Explain the current evidence leaderboards and any coverage limitations.",
    structure: "Explain our academic structure and identify any missing setup needed for student and placement workflows.",
    attendance: "Show students whose attendance may affect placement eligibility.",
    overview: "Summarize this academic scope, its evidence coverage, and the most important next actions.",
    results: "Find missing or stale published results that affect academic and placement decisions.",
    assessments: "Summarize assessment performance and students who need intervention.",
    integrations: "What College evidence is stale or missing from ERP synchronization?",
    exchange: "Review recent Data Exchange health and unresolved validation issues.",
    policy: "Explain the readiness policy in plain language and show how missing evidence is handled.",
    clearance: "Show internship candidates whose clearance needs review.",
  };
  return prompts[section] || "Summarize the current College placement position.";
}
