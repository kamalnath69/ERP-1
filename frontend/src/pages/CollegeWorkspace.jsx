import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import {
  Archive, ArrowRight, Books, Briefcase, Buildings, CalendarCheck, ChartBar,
  CheckCircle, Code, Database, FileArrowUp, Funnel, GraduationCap, ListChecks,
  MagnifyingGlass, Medal, Plus, ShieldCheck, Sparkle, Student, Target, UsersThree,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import SecondarySidebarLayout, {
  SecondarySidebarGroup, SecondarySidebarHeader, SecondarySidebarItem,
  SecondarySidebarNav, SecondarySidebarTrigger,
} from "@/components/layout/SecondarySidebarLayout";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar,
  SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import {
  useCommitCollegeImportMutation, useCreateCollegeApplicationMutation,
  useCreateCollegeAssessmentMutation, useCreateCollegeAttendanceMutation,
  useCreateCollegeCompanyMutation, useCreateCollegeIntegrationMutation,
  useCreateCollegeOpportunityMutation, useGetCollegeAcademicEvidencePageQuery,
  useGetCollegeApplicationsQuery, useGetCollegeAssessmentRegisterQuery,
  useGetCollegeAssessmentsPageQuery, useGetCollegeAttendanceRegisterQuery,
  useGetCollegeAttendanceSessionsPageQuery, useGetCollegeCohortsPageQuery,
  useGetCollegeCompaniesQuery, useGetCollegeImportsQuery,
  useGetCollegeIntegrationsQuery, useGetCollegeInternshipClearancePageQuery,
  useGetCollegeLeaderboardsQuery, useGetCollegeOpportunitiesQuery,
  useGetCollegePipelineStagesQuery, useGetCollegeReadinessPolicyQuery,
  useGetCollegeReferencesQuery, useGetCollegeStudentIntelligenceQuery,
  useMoveCollegeApplicationStageMutation, usePreviewCollegeCsvImportMutation,
  useQueueCollegeIntegrationSyncMutation, useSaveCollegeAttendanceMutation,
  useSaveCollegeScoresMutation,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import {
  applyApiErrors, assessmentScoreSchema, attendanceRecordSchema, attendanceSessionSchema,
  collegeApplicationSchema, collegeAssessmentSchema, collegeConnectorSchema, collegeDriveSchema,
  companySchema, FORM_OPTIONS, normalizeApiError,
} from "@/lib/validation";


const NAVIGATION = [
  { label: "Placement", items: [
    { id: "pipeline", label: "Pipeline", icon: Funnel, permission: "college.placements.view" },
    { id: "drives", label: "Drives", icon: Briefcase, permission: "college.placements.view" },
    { id: "applications", label: "Applications", icon: ListChecks, permission: "college.placements.view" },
    { id: "companies", label: "Companies", icon: Buildings, permission: "college.placements.view" },
  ] },
  { label: "Intelligence", items: [
    { id: "readiness", label: "Readiness & support", icon: Target, permission: "college.readiness.view" },
    { id: "coding", label: "Coding", icon: Code, permission: "college.coding.view" },
    { id: "leaderboards", label: "Leaderboards", icon: Medal, permission: "college.readiness.view" },
  ] },
  { label: "Academic evidence", items: [
    { id: "batches", label: "Batches", icon: UsersThree, permission: "college.students.view" },
    { id: "attendance", label: "Attendance", icon: CalendarCheck, permission: "college.attendance.view" },
    { id: "evidence", label: "Results & evidence", icon: Books, permission: "college.academics.view" },
    { id: "assessments", label: "Assessments", icon: GraduationCap, permission: "college.assessments.view" },
  ] },
  { label: "Data", items: [
    { id: "integrations", label: "ERP synchronization", icon: Database, permission: "college.integrations.manage" },
    { id: "imports", label: "Imports", icon: FileArrowUp, permission: "college.imports.manage" },
  ] },
  { label: "Administration", items: [
    { id: "policy", label: "Readiness policy", icon: ShieldCheck, permission: "college.readiness.view" },
    { id: "clearance", label: "Internship clearance", icon: CheckCircle, permission: "college.fees.view" },
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
  batches: ["Graduation batches", "Review cohort size and academic placement scope without loading every student."],
  attendance: ["Attendance evidence", "Review imported history or record a local session when the ERP is unavailable."],
  evidence: ["Academic evidence", "Use verified results and attendance as placement evidence, not a second student ERP."],
  assessments: ["Placement assessments", "Record aptitude, technical, and placement-specific evaluation evidence."],
  integrations: ["ERP synchronization", "Keep authoritative student and academic records connected through audited read-only pulls."],
  imports: ["Data imports", "Validate and review academic evidence before it enters placement intelligence."],
  policy: ["Readiness policy", "Understand how evidence is weighted and when a student becomes rankable."],
  clearance: ["Internship clearance", "Review only the clearance signal required for internship eligibility."],
};

const LEGACY_SECTIONS = {
  placements: "pipeline", academics: "evidence", coding: "coding",
  leaderboards: "leaderboards", batches: "batches", imports: "imports", fees: "clearance",
};

export default function CollegeWorkspace() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requested = params.get("section") || "pipeline";
  const redirectTo = requested === "overview"
    ? "/app"
    : requested === "students"
      ? `/app/clients${params.get("new") ? "?new=1" : ""}`
      : null;

  const groups = NAVIGATION.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.permission || can(item.permission) || can(item.permission.replace(".view", ".manage"))),
  })).filter((group) => group.items.length);
  const sections = groups.flatMap((group) => group.items);
  const normalized = LEGACY_SECTIONS[requested] || requested;
  const active = sections.some((item) => item.id === normalized) ? normalized : sections[0]?.id || "pipeline";
  const activeSection = sections.find((item) => item.id === active);

  useEffect(() => {
    if (redirectTo) return;
    if (requested === active) return;
    const next = new URLSearchParams(params);
    if (active === "pipeline") next.delete("section"); else next.set("section", active);
    setParams(next, { replace: true });
  }, [active, params, redirectTo, requested, setParams]);

  if (redirectTo) return <Navigate to={redirectTo} replace />;

  const changeSection = (section) => {
    const next = new URLSearchParams();
    if (section !== "pipeline") next.set("section", section);
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
    ariaLabel="College placement navigation"
    className="reveal bg-card"
    sidebarClassName="bg-surface-subtle/35"
    contentClassName="bg-background"
    mobileTitle="College placement"
    mobileDescription="Placement, evidence, and student success"
    sidebar={<><SecondarySidebarHeader title="Placement workspace" description="Evidence to outcomes" />{navigation()}</>}
    mobileSidebar={({ closeSidebar }) => navigation(closeSidebar)}
  >
    {({ openSidebar }) => <div className="min-w-0">
      <div className="flex items-center gap-3 border-b bg-card px-4 py-3 lg:hidden">
        <SecondarySidebarTrigger icon={activeSection?.icon} label={activeSection?.label || "College"} onClick={openSidebar} />
      </div>
      <main className="mx-auto w-full max-w-[1520px] space-y-5 p-4 sm:p-6 lg:p-8">
        <CollegeSectionHeader section={active} navigate={navigate} />
        <CollegeSection section={active} />
      </main>
    </div>}
  </SecondarySidebarLayout>;
}

function CollegeSectionHeader({ section, navigate }) {
  const [title, description] = SECTION_COPY[section] || ["College placement", "Student success workspace"];
  const ask = encodeURIComponent(aiPrompt(section));
  return <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
    <div className="min-w-0"><p className="section-kicker">College / Placement intelligence</p><h1 className="mt-1.5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">{title}</h1><p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{description}</p></div>
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
  if (section === "batches") return <BatchesPanel />;
  if (section === "attendance") return <AttendancePanel />;
  if (section === "evidence") return <AcademicEvidencePanel />;
  if (section === "assessments") return <AssessmentsPanel />;
  if (section === "integrations") return <IntegrationsPanel />;
  if (section === "imports") return <ImportsPanel />;
  if (section === "policy") return <ReadinessPolicyPanel />;
  if (section === "clearance") return <ClearancePanel />;
  return null;
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
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [status, setStatus] = useState("all");
  const [drawer, setDrawer] = useState(false);
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
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [drawer, setDrawer] = useState(false);
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

function BatchesPanel() {
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const paging = useCursorPagination(q);
  const query = useGetCollegeCohortsPageQuery({ q, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "name", label: "Batch", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.code}</div></div> },
    { key: "program", label: "Program", render: (row) => row.program_name },
    { key: "year", label: "Admission year", render: (row) => row.admission_year },
    { key: "semester", label: "Semester", render: (row) => row.current_semester },
    { key: "students", label: "Students", render: (row) => row.student_count },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Batch directory" /><FilterBar className="rounded-none border-x-0 border-t"><SearchField value={search} onChange={setSearch} placeholder="Search batch or code" /></FilterBar><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant="section" alignment="left" icon={UsersThree} title="No batches available" description="Synchronize batches from the College ERP or use an approved import." />} /><ListFooter query={query} paging={paging} noun="batches" /></Surface>;
}

function AttendancePanel() {
  const { can } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const [register, setRegister] = useState(null);
  const paging = useCursorPagination("attendance-sessions");
  const query = useGetCollegeAttendanceSessionsPageQuery({ cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "course", label: "Course", render: (row) => <div><div className="font-semibold">{row.course_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.course_code} / {row.cohort_name}</div></div> },
    { key: "held", label: "Held on", render: (row) => shortDate(row.held_on) },
    { key: "topic", label: "Topic", render: (row) => row.topic || "Not recorded" },
    { key: "coverage", label: "Recorded", render: (row) => `${row.record_count} students` },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "open", label: "", render: () => <ArrowRight /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Attendance sessions" action={can("college.attendance.mark") && <Button size="sm" onClick={() => setDrawer(true)}><Plus className="mr-2" />New local session</Button>} /><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} onRowClick={setRegister} empty={<EmptyState variant="section" alignment="left" icon={CalendarCheck} title="No attendance evidence yet" description="ERP attendance snapshots are preferred; use a local session only when needed." />} /><ListFooter query={query} paging={paging} noun="sessions" /><AttendanceSessionDrawer open={drawer} onClose={() => setDrawer(false)} /><AttendanceRegisterDrawer session={register} onClose={() => setRegister(null)} /></Surface>;
}

function AcademicEvidencePanel() {
  const [kind, setKind] = useState("term_results");
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const paging = useCursorPagination(JSON.stringify({ kind, q }));
  const query = useGetCollegeAcademicEvidencePageQuery({ kind, q, cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = kind === "term_results" ? [
    { key: "student", label: "Student", render: studentEvidenceCell },
    { key: "semester", label: "Semester", render: (row) => row.semester },
    { key: "sgpa", label: "SGPA", render: (row) => row.sgpa ?? "-" },
    { key: "cgpa", label: "CGPA", render: (row) => row.cgpa ?? "-" },
    { key: "backlogs", label: "Active backlogs", render: (row) => row.active_backlogs ?? "Not recorded" },
    { key: "source", label: "Source", render: (row) => <StatusBadge status="neutral" label={sentence(row.source_type || "local")} /> },
  ] : [
    { key: "student", label: "Student", render: studentEvidenceCell },
    { key: "attendance", label: "Attendance", render: (row) => row.attendance_percent == null ? "-" : `${row.attendance_percent}%` },
    { key: "classes", label: "Classes", render: (row) => `${row.classes_attended}/${row.classes_held}` },
    { key: "as_of", label: "As of", render: (row) => shortDate(row.as_of) },
    { key: "source", label: "Source", render: (row) => <StatusBadge status="neutral" label={sentence(row.source_type || "local")} /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Verified academic evidence" /><div className="flex flex-col gap-3 border-t p-3 sm:flex-row sm:items-center"><SegmentControl value={kind} onChange={setKind} items={[{ value: "term_results", label: "Term results" }, { value: "attendance", label: "Attendance snapshots" }]} /><SearchField value={search} onChange={setSearch} placeholder="Search student" /></div><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant="section" alignment="left" icon={Books} title="No academic evidence in this view" description="Synchronize the College ERP or import a reviewed file." />} /><ListFooter query={query} paging={paging} noun="evidence records" /></Surface>;
}

function AssessmentsPanel() {
  const { can } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const [register, setRegister] = useState(null);
  const paging = useCursorPagination("assessments");
  const query = useGetCollegeAssessmentsPageQuery({ cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const columns = [
    { key: "title", label: "Assessment", render: (row) => <div><div className="font-semibold">{row.title}</div><div className="mt-1 text-xs text-muted-foreground">{sentence(row.assessment_type)} / {row.course_name}</div></div> },
    { key: "cohort", label: "Batch", render: (row) => row.cohort_name },
    { key: "due", label: "Due", render: (row) => shortDate(row.due_on) },
    { key: "scores", label: "Scores", render: (row) => row.score_count },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "open", label: "", render: () => <ArrowRight /> },
  ];
  return <Surface className="overflow-hidden"><PanelToolbar title="Placement and academic assessments" action={can("college.assessments.manage") && <Button size="sm" onClick={() => setDrawer(true)}><Plus className="mr-2" />New assessment</Button>} /><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} onRowClick={setRegister} empty={<EmptyState variant="section" alignment="left" icon={GraduationCap} title="No assessments yet" description="Create a placement-specific assessment or synchronize academic results." />} /><ListFooter query={query} paging={paging} noun="assessments" /><AssessmentDrawer open={drawer} onClose={() => setDrawer(false)} /><AssessmentRegisterDrawer assessment={register} onClose={() => setRegister(null)} /></Surface>;
}

function ImportsPanel() {
  const [resource, setResource] = useState("students");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const paging = useCursorPagination("imports");
  const query = useGetCollegeImportsQuery({ cursor: paging.cursor, limit: 25 });
  const rows = usePagedData(query, paging);
  const [previewCsv, previewState] = usePreviewCollegeCsvImportMutation();
  const [commit, commitState] = useCommitCollegeImportMutation();
  const validate = async () => {
    if (!file) return;
    try { setPreview(await previewCsv({ file, resourceType: resource }).unwrap()); }
    catch (error) { toast.error(error?.data?.detail || "Import could not be validated"); }
  };
  const commitRun = async () => {
    try { await commit(preview.id).unwrap(); toast.success("Validated evidence imported"); setPreview(null); setFile(null); }
    catch (error) { toast.error(error?.data?.detail || "Import could not be committed"); }
  };
  const columns = [
    { key: "resource", label: "Resource", render: (row) => sentence(row.resource_type) },
    { key: "source", label: "Source", render: (row) => sentence(row.source_type) },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "rows", label: "Committed", render: (row) => `${row.committed_count}/${row.row_count}` },
    { key: "started", label: "Started", render: (row) => dateTime(row.created_at) },
  ];
  return <div className="space-y-5"><OwnershipNotice /><Surface className="p-4 sm:p-5"><h2 className="font-semibold">Validate an academic evidence file</h2><p className="mt-1 text-xs text-muted-foreground">Nothing is committed until validation has completed and a staff member confirms the preview.</p><div className="mt-4 grid gap-3 sm:grid-cols-[190px_minmax(0,1fr)_auto]"><Select value={resource} onValueChange={setResource}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["students", "term_results", "attendance", "skills", "assessments"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select><Input type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} /><Button onClick={validate} disabled={!file || previewState.isLoading}>{previewState.isLoading ? "Validating..." : "Preview"}</Button></div>{preview && <div className="mt-4 flex flex-col gap-3 rounded-xl border bg-secondary/30 p-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="font-semibold">{preview.valid_count} of {preview.row_count} rows are ready</div><div className="mt-1 text-xs text-muted-foreground">{preview.failed_count ? `${preview.failed_count} rows need correction.` : "No validation errors found."}</div></div><Button onClick={commitRun} disabled={!preview.valid_count || commitState.isLoading}>{commitState.isLoading ? "Importing..." : "Commit valid rows"}</Button></div>}</Surface><Surface className="overflow-hidden"><PanelToolbar title="Import history" /><DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={<EmptyState variant="inline" alignment="left" icon={Archive} title="No import runs yet" description="Validated CSV and ERP runs will appear here." />} /><ListFooter query={query} paging={paging} noun="import runs" /></Surface></div>;
}

function IntegrationsPanel() {
  const [drawer, setDrawer] = useState(false);
  const query = useGetCollegeIntegrationsQuery();
  const [sync, syncState] = useQueueCollegeIntegrationSyncMutation();
  const run = async (id) => {
    try { await sync({ connectorId: id, resourceTypes: ["students", "term_results", "attendance", "skills", "assessments"], idempotencyKey: crypto.randomUUID() }).unwrap(); toast.success("ERP synchronization queued"); }
    catch (error) { toast.error(error?.data?.detail || "Synchronization could not be queued"); }
  };
  return <div className="space-y-5"><OwnershipNotice /><Surface className="overflow-hidden"><PanelToolbar title="Connected College ERP" action={<Button size="sm" onClick={() => setDrawer(true)}><Plus className="mr-2" />Connect ERP</Button>} /><div className="divide-y border-t">{(query.data?.items || []).map((row) => <div key={row.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary"><Database /></span><span className="min-w-0 flex-1"><span className="block font-semibold">{row.name}</span><span className="mt-1 block text-xs text-muted-foreground">{row.last_success_at ? `Last successful sync ${dateTime(row.last_success_at)}` : "No successful sync yet"}</span></span><StatusBadge status={row.status} /><Button variant="outline" size="sm" onClick={() => run(row.id)} disabled={!row.api_key_configured || syncState.isLoading}>Sync now</Button></div>)}{!query.isLoading && !query.data?.items?.length && <EmptyState variant="section" alignment="left" icon={Database} title="No ERP connected" description="Connect a credential-protected read-only source, or continue with reviewed CSV imports." primaryAction={<Button variant="outline" onClick={() => setDrawer(true)}>Connect ERP</Button>} className="m-4" />}</div><ConnectorDrawer open={drawer} onClose={() => setDrawer(false)} /></Surface></div>;
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

function AssessmentRegisterDrawer({ assessment, onClose }) {
  const [search, setSearch] = useState("");
  const [changes, setChanges] = useState({});
  const [rowErrors, setRowErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [pendingMode, setPendingMode] = useState(null);
  const submitLock = useRef(false);
  const q = useDeferredValue(search.trim());
  const paging = useCursorPagination(JSON.stringify({ id: assessment?.id, q }));
  const query = useGetCollegeAssessmentRegisterQuery({ assessmentId: assessment?.id, q, cursor: paging.cursor, limit: 50 }, { skip: !assessment?.id });
  const rows = usePagedData(query, paging);
  const [save, saveState] = useSaveCollegeScoresMutation();
  useEffect(() => { if (!assessment) { setSearch(""); setChanges({}); setRowErrors({}); setFormError(""); } }, [assessment]);
  const submit = async (publish = false) => {
    const rawScores = Object.entries(changes).map(([student_profile_id, value]) => ({ student_profile_id, marks_awarded: value.marks_awarded, grade: value.grade || null, feedback: value.feedback || null }));
    const errors = {};
    const scores = [];
    rawScores.forEach((score) => {
      const parsed = assessmentScoreSchema.safeParse(score);
      if (!parsed.success) { errors[score.student_profile_id] = parsed.error.issues[0]?.message || "Invalid score"; return; }
      if (parsed.data.marks_awarded != null && Number(parsed.data.marks_awarded) > Number(assessment?.max_marks || 0)) { errors[score.student_profile_id] = `Marks cannot exceed ${assessment.max_marks}`; return; }
      scores.push(parsed.data);
    });
    setRowErrors(errors);
    if (Object.keys(errors).length || submitLock.current) return;
    if (!scores.length) return;
    submitLock.current = true;
    setPendingMode(publish ? "publish" : "draft");
    setFormError("");
    try { await save({ assessmentId: assessment.id, scores, publish }).unwrap(); toast.success(publish ? "Scores published" : "Scores saved"); setChanges({}); setRowErrors({}); paging.reset(); query.refetch(); }
    catch (error) { setFormError(normalizeApiError(error, "Scores could not be saved").message); }
    finally { submitLock.current = false; setPendingMode(null); }
  };
  return <DrawerForm open={Boolean(assessment)} onOpenChange={(open) => { if (!open && !saveState.isLoading) onClose(); }} title={assessment?.title || "Assessment register"} description={query.data?.summary ? `${query.data.summary.scored} scored / ${query.data.summary.unscored} remaining` : "Paged score register"}><div className="space-y-4"><SearchField value={search} onChange={setSearch} placeholder="Search student" /><div className="divide-y rounded-xl border">{rows.map((row) => { const value = changes[row.student_profile_id] || row; const error = rowErrors[row.student_profile_id]; return <div key={row.student_profile_id} className="grid gap-3 p-3 sm:grid-cols-[minmax(0,1fr)_110px_90px] sm:items-center"><div><div className="font-semibold">{row.student_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number}</div>{error && <p role="alert" className="mt-1 text-xs font-medium text-destructive">{error}</p>}</div><Input inputMode="decimal" aria-label={`Marks for ${row.student_name}`} aria-invalid={Boolean(error)} value={value.marks_awarded ?? ""} placeholder={`/${assessment?.max_marks}`} onChange={(event) => { setChanges((current) => ({ ...current, [row.student_profile_id]: { ...value, marks_awarded: event.target.value } })); setRowErrors((current) => ({ ...current, [row.student_profile_id]: undefined })); }} /><Input value={value.grade || ""} maxLength={12} aria-label={`Grade for ${row.student_name}`} placeholder="Grade" onChange={(event) => { setChanges((current) => ({ ...current, [row.student_profile_id]: { ...value, grade: event.target.value } })); setRowErrors((current) => ({ ...current, [row.student_profile_id]: undefined })); }} /></div>; })}</div><ListFooter query={query} paging={paging} noun="students" />{formError && <div role="alert" className="rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">{formError}</div>}<div className="sticky bottom-0 flex flex-col gap-2 border-t bg-card/95 pt-4 backdrop-blur sm:flex-row sm:items-center sm:justify-between"><span className="text-xs text-muted-foreground">{Object.keys(changes).length} unsaved change(s)</span><div className="flex gap-2"><Button variant="outline" onClick={() => submit(false)} disabled={!Object.keys(changes).length || Boolean(pendingMode)} loading={pendingMode === "draft"} loadingText="Saving...">Save draft</Button><Button onClick={() => submit(true)} disabled={!Object.keys(changes).length || Boolean(pendingMode)} loading={pendingMode === "publish"} loadingText="Publishing...">Publish</Button></div></div></div></DrawerForm>;
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
  const refs = useGetCollegeReferencesQuery(undefined, { skip: !open });
  const [create, state] = useCreateCollegeAttendanceMutation();
  const form = useForm({ resolver: zodResolver(attendanceSessionSchema), defaultValues: attendanceSessionDefaults(), ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (open) reset(attendanceSessionDefaults()); }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try { await create({ ...values, starts_at: values.starts_at || null, ends_at: values.ends_at || null, records: [] }).unwrap(); toast.success("Attendance session created"); reset(attendanceSessionDefaults()); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "Session could not be created" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Create local attendance session" description="Use only when authoritative ERP attendance is unavailable."><Form {...form}><form noValidate onSubmit={submit} className="space-y-4"><CollegeReferenceField control={control} name="offering_id" label="Course offering" rows={refs.data?.offerings || []} getLabel={(row) => row.id} placeholder="Choose offering" /><div className="grid gap-4 sm:grid-cols-2"><CollegeFormField control={control} name="held_on" label="Held on"><Input type="date" /></CollegeFormField><CollegeFormField control={control} name="topic" label="Topic"><Input /></CollegeFormField><CollegeFormField control={control} name="starts_at" label="Starts"><Input type="time" /></CollegeFormField><CollegeFormField control={control} name="ends_at" label="Ends"><Input type="time" /></CollegeFormField></div><FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" loading={pending} loadingText="Creating...">Create session</Button></form></Form></DrawerForm>;
}

function AssessmentDrawer({ open, onClose }) {
  const refs = useGetCollegeReferencesQuery(undefined, { skip: !open });
  const [create, state] = useCreateCollegeAssessmentMutation();
  const form = useForm({ resolver: zodResolver(collegeAssessmentSchema), defaultValues: assessmentDefaults, ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (open) reset(assessmentDefaults); }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try { await create(values).unwrap(); toast.success("Assessment created"); reset(assessmentDefaults); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "Assessment could not be created" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Create assessment" description="Use for placement-specific evaluation or approved local academic evidence."><Form {...form}><form noValidate onSubmit={submit} className="space-y-4"><CollegeReferenceField control={control} name="offering_id" label="Course offering" rows={refs.data?.offerings || []} getLabel={(row) => row.id} placeholder="Choose offering" /><CollegeFormField control={control} name="title" label="Assessment title"><Input /></CollegeFormField><div className="grid gap-4 sm:grid-cols-2"><CollegeSelectField control={control} name="assessment_type" label="Type" values={["internal", "assignment", "quiz", "practical", "project", "semester"]} /><CollegeFormField control={control} name="max_marks" label="Maximum marks"><Input inputMode="decimal" /></CollegeFormField><CollegeFormField control={control} name="due_on" label="Due on"><Input type="date" /></CollegeFormField><CollegeFormField control={control} name="weightage_bps" label="Weightage (basis points)"><Input inputMode="numeric" /></CollegeFormField></div><FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" loading={pending} loadingText="Creating...">Create assessment</Button></form></Form></DrawerForm>;
}

function ConnectorDrawer({ open, onClose }) {
  const [create, state] = useCreateCollegeIntegrationMutation();
  const form = useForm({ resolver: zodResolver(collegeConnectorSchema), defaultValues: connectorDefaults, ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError, watch } = form;
  const authMode = watch("auth_mode");
  useEffect(() => { if (open) reset(connectorDefaults); }, [open, reset]);
  const pending = formState.isSubmitting || state.isLoading;
  const submit = handleSubmit(async (values) => {
    try { await create({ ...values, auth_header: values.auth_header || null, mapping: {}, pagination: {} }).unwrap(); toast.success("ERP connector saved"); reset(connectorDefaults); onClose(); }
    catch (error) { const normalized = applyApiErrors(error, setError, { fallback: "ERP connector could not be saved" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); }
  });
  return <DrawerForm open={open} onOpenChange={(value) => { if (!value && !pending) onClose(); }} title="Connect College ERP" description="Configure a credential-protected read-only HTTPS source."><Form {...form}><form noValidate onSubmit={submit} className="space-y-4"><CollegeFormField control={control} name="name" label="Connection name"><Input /></CollegeFormField><CollegeFormField control={control} name="base_url" label="HTTPS base URL"><Input type="url" /></CollegeFormField><div className="grid gap-4 sm:grid-cols-2"><CollegeSelectField control={control} name="auth_mode" label="Authentication" values={["bearer", "header"]} />{authMode === "header" && <CollegeFormField control={control} name="auth_header" label="Header name"><Input /></CollegeFormField>}<CollegeFormField control={control} name="sync_interval_hours" label="Sync interval (hours)"><Input inputMode="numeric" /></CollegeFormField></div><CollegeFormField control={control} name="api_key" label="API key" description="Stored securely and never returned to the browser."><Input type="password" autoComplete="off" /></CollegeFormField><FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" loading={pending} loadingText="Saving...">Save connector</Button></form></Form></DrawerForm>;
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

const companyDefaults = { name: "", industry: "", website: "", contact_name: "", contact_email: "", contact_phone: "", notes: "" };
const driveDefaults = { company_id: "", title: "", opportunity_type: "campus_drive", status: "active", deadline_at: "", drive_at: "", work_location: "", employment_type: "", package_min: "", package_max: "", minimum_cgpa: "", maximum_active_backlogs: "", minimum_attendance: "", minimum_solved: "" };
const applicationDefaults = { opportunity_id: "", student_profile_id: "", notes: "" };
const assessmentDefaults = { offering_id: "", title: "", assessment_type: "internal", max_marks: "100", weightage_bps: "0", due_on: "", status: "draft" };
const connectorDefaults = { name: "", base_url: "", auth_mode: "bearer", auth_header: "", api_key: "", sync_interval_hours: "6" };
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
function shortDate(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "Not scheduled"; }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)) : "Not scheduled"; }
function isoToday() { return new Date().toISOString().slice(0, 10); }
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
    batches: "Compare graduation batches by readiness, attendance, and placement outcomes.",
    attendance: "Show students whose attendance may affect placement eligibility.",
    evidence: "Find missing or stale academic evidence that affects placement readiness.",
    assessments: "Summarize assessment performance and students who need intervention.",
    integrations: "What College evidence is stale or missing from ERP synchronization?",
    imports: "Review recent import health and unresolved validation issues.",
    policy: "Explain the readiness policy in plain language and show how missing evidence is handled.",
    clearance: "Show internship candidates whose clearance needs review.",
  };
  return prompts[section] || "Summarize the current College placement position.";
}
