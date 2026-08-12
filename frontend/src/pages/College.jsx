import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight, Books, Briefcase, CalendarBlank, ChartBar, CheckCircle, Clock,
  Code, Database, GraduationCap, List, Medal, Plus, Receipt, Student,
  UserPlus, UsersThree, Warning,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import {
  DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip,
  PageHeader, PageShell, SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import SecondarySidebarLayout, { SecondarySidebarTrigger } from "@/components/layout/SecondarySidebarLayout";
import PlacementDashboard from "@/components/college/PlacementDashboard";
import BusinessChart from "@/components/charts/BusinessChart";
import {
  useAdmitCollegeStudentMutation,
  useCreateCollegeAssessmentMutation,
  useCreateCollegeAttendanceMutation,
  useCreateCollegeFeePlanMutation,
  useCreateCollegeCohortMutation,
  useCreateCollegeCourseMutation,
  useCreateCollegeDepartmentMutation,
  useCreateCollegeOfferingMutation,
  useCreateCollegeProgramMutation,
  useCreateCollegeTermMutation,
  useGetCollegeWorkspaceQuery,
  useGetCollegeCompaniesQuery,
  useGetCollegeApplicationsQuery,
  useGetCollegeImportsQuery,
  useGetCollegeIntegrationsQuery,
  useGetCollegeLeaderboardsQuery,
  useGetCollegeOpportunitiesQuery,
  useGetCollegePipelineStagesQuery,
  useGetCollegePlacementDashboardQuery,
  useGetCollegeStudentIntelligenceQuery,
  usePreviewCollegeCsvImportMutation,
  useCommitCollegeImportMutation,
  useCreateCollegeCompanyMutation,
  useCreateCollegeApplicationMutation,
  useCreateCollegeIntegrationMutation,
  useCreateCollegeOpportunityMutation,
  useQueueCollegeIntegrationSyncMutation,
  useMoveCollegeApplicationStageMutation,
  useAssignCollegeStudentFeeMutation,
  useSaveCollegeScoresMutation,
} from "@/features/college/collegeApi";


const sections = [
  { id: "overview", label: "Overview", icon: ChartBar },
  { id: "students", label: "Students", icon: Student, permission: "college.students.view" },
  { id: "batches", label: "Batches", icon: UsersThree, permission: "college.students.view" },
  { id: "academics", label: "Academics", icon: Books },
  { id: "coding", label: "Coding", icon: Code, permission: "college.coding.view" },
  { id: "placements", label: "Placements", icon: Briefcase, permission: "college.placements.view" },
  { id: "leaderboards", label: "Leaderboards", icon: Medal, permission: "college.readiness.view" },
  { id: "imports", label: "Data imports", icon: Database, permission: "college.imports.manage" },
  { id: "fees", label: "Fee clearance", icon: Receipt, permission: "college.fees.view", administration: true },
];

const academicModes = [
  { value: "departments", label: "Departments" },
  { value: "programs", label: "Programs" },
  { value: "cohorts", label: "Cohorts" },
  { value: "courses", label: "Courses" },
  { value: "terms", label: "Terms" },
];


export default function College() {
  const { can } = useAuth();
  const { locationId } = useBusiness();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const availableSections = sections.filter((item) => !item.permission || can(item.permission) || can(item.permission.replace(".view", ".manage")));
  const requested = params.get("section") || "overview";
  const active = availableSections.some((item) => item.id === requested) ? requested : "overview";
  const range = 30;
  const [drawer, setDrawer] = useState(() => initialDrawer(params));
  const [scoreAssessment, setScoreAssessment] = useState(null);
  const needsWorkspace = ["batches", "academics", "fees"].includes(active)
    || ["student", "department", "program", "term", "cohort", "course", "offering", "attendance", "assessment", "fee-plan", "student-fee"].includes(drawer)
    || Boolean(scoreAssessment);
  const query = useGetCollegeWorkspaceQuery({ locationId, range }, { skip: !needsWorkspace });
  const data = query.data;

  const [createDepartment, departmentState] = useCreateCollegeDepartmentMutation();
  const [createProgram, programState] = useCreateCollegeProgramMutation();
  const [createTerm, termState] = useCreateCollegeTermMutation();
  const [createCohort, cohortState] = useCreateCollegeCohortMutation();
  const [createCourse, courseState] = useCreateCollegeCourseMutation();
  const [createOffering, offeringState] = useCreateCollegeOfferingMutation();
  const [admitStudent, studentState] = useAdmitCollegeStudentMutation();
  const [createAttendance, attendanceState] = useCreateCollegeAttendanceMutation();
  const [createAssessment, assessmentState] = useCreateCollegeAssessmentMutation();
  const [createFeePlan, feePlanState] = useCreateCollegeFeePlanMutation();
  const [assignStudentFee, studentFeeState] = useAssignCollegeStudentFeeMutation();
  const [saveScores, scoresState] = useSaveCollegeScoresMutation();

  const changeSection = (section) => {
    setParams(section === "overview" ? {} : { section });
  };
  const closeDrawer = () => {
    setDrawer(null);
    if (params.has("new")) {
      const next = new URLSearchParams(params);
      next.delete("new");
      setParams(next, { replace: true });
    }
  };
  const run = async (trigger, payload, success) => {
    try {
      await trigger(payload).unwrap();
      toast.success(success);
      closeDrawer();
    } catch (error) {
      toast.error(error?.data?.detail || "The College record could not be saved");
    }
  };

  const activeSection = availableSections.find((item) => item.id === active) || availableSections[0];
  if (query.isError && !data) return <SecondarySidebarLayout sidebar={<div className="p-5 text-sm font-semibold">Placement workspace</div>}><div className="p-6"><ErrorState title="College workspace could not be loaded" description={query.error?.data?.detail} retry={query.refetch} /></div></SecondarySidebarLayout>;

  const navigation = (closeSidebar) => <CollegeNavigation
    sections={availableSections}
    active={active}
    onChange={(section) => { changeSection(section); closeSidebar?.(); }}
  />;

  return <>
    <SecondarySidebarLayout
      ariaLabel="College workspace navigation"
      className="reveal bg-card"
      sidebarClassName="bg-surface-subtle/35"
      contentClassName="bg-background"
      mobileTitle="College placement"
      mobileDescription="Student success workspace"
      sidebar={<><div className="shrink-0 border-b px-5 py-5"><div className="text-sm font-semibold">Placement workspace</div><div className="mt-1 text-xs text-muted-foreground">Students to outcomes</div></div>{navigation()}</>}
      mobileSidebar={({ closeSidebar }) => navigation(closeSidebar)}
    >
      {({ openSidebar }) => <div className="min-w-0">
        <div className="flex items-center gap-3 border-b bg-card px-4 py-3 lg:hidden">
          <SecondarySidebarTrigger icon={activeSection?.icon || List} label={activeSection?.label || "College"} onClick={openSidebar} />
        </div>
        {active !== "overview" && <div className="flex flex-col gap-3 border-b bg-card px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div><p className="section-kicker">College placement</p><h1 className="mt-1.5 text-2xl font-semibold tracking-[-0.035em]">{activeSection?.label}</h1></div>
          <HeaderActions active={active} can={can} onOpen={setDrawer} />
        </div>}
        <main>
          {active === "overview" && <PlacementDashboard embedded onSection={changeSection} />}
          {active === "students" && <StudentIntelligencePanel canManage={can("college.students.manage")} onCreate={() => setDrawer("student")} onOpen={(row) => navigate(`/app/clients/${row.client_id}`)} />}
          {active === "batches" && <BatchesPanel data={data} loading={query.isLoading} onOpenStudents={() => changeSection("students")} />}
          {active === "academics" && <AcademicHub data={data} loading={query.isLoading} can={can} onCreate={setDrawer} onScores={setScoreAssessment} />}
          {active === "coding" && <CodingIntelligencePanel />}
          {active === "placements" && <PlacementsPanel initialAction={params.get("new")} onActionHandled={closeDrawer} />}
          {active === "leaderboards" && <LeaderboardsPanel />}
          {active === "imports" && <DataImportsPanel />}
          {active === "fees" && <FeeClearancePanel data={data} loading={query.isLoading} canManage={can("college.fees.manage")} onCreatePlan={() => setDrawer("fee-plan")} onAssign={() => setDrawer("student-fee")} onOpenInvoice={(invoiceId) => navigate(`/app/sales/${invoiceId}`)} />}
        </main>
      </div>}
    </SecondarySidebarLayout>

    <StudentDrawer open={drawer === "student"} onClose={closeDrawer} data={data} locationId={locationId} pending={studentState.isLoading} onSubmit={(payload) => run(admitStudent, payload, "Student admitted")} />
    <AcademicDrawer key={drawer || "academic"} mode={academicMode(drawer)} open={Boolean(academicMode(drawer))} onClose={closeDrawer} data={data} locationId={locationId} pending={departmentState.isLoading || programState.isLoading || termState.isLoading || cohortState.isLoading || courseState.isLoading} onSubmit={(mode, payload) => {
      const actions = { department: createDepartment, program: createProgram, term: createTerm, cohort: createCohort, course: createCourse };
      return run(actions[mode], payload, `${sentence(mode)} created`);
    }} />
    <OfferingDrawer open={drawer === "offering"} onClose={closeDrawer} data={data} pending={offeringState.isLoading} onSubmit={(payload) => run(createOffering, payload, "Course offering scheduled")} />
    <AttendanceDrawer open={drawer === "attendance"} onClose={closeDrawer} data={data} pending={attendanceState.isLoading} onSubmit={(payload) => run(createAttendance, payload, "Attendance recorded")} />
    <AssessmentDrawer open={drawer === "assessment"} onClose={closeDrawer} data={data} pending={assessmentState.isLoading} onSubmit={(payload) => run(createAssessment, payload, "Assessment created")} />
    <FeePlanDrawer open={drawer === "fee-plan"} onClose={closeDrawer} data={data} pending={feePlanState.isLoading} onSubmit={(payload) => run(createFeePlan, payload, "Fee plan created")} />
    <StudentFeeDrawer open={drawer === "student-fee"} onClose={closeDrawer} data={data} pending={studentFeeState.isLoading} onSubmit={(payload) => run(assignStudentFee, payload, "Fee assigned and invoice created")} />
    <ScoreDrawer assessment={scoreAssessment} onClose={() => setScoreAssessment(null)} data={data} pending={scoresState.isLoading} onSubmit={async (payload) => {
      try {
        await saveScores(payload).unwrap();
        toast.success(payload.publish ? "Results published" : "Scores saved");
        setScoreAssessment(null);
      } catch (error) {
        toast.error(error?.data?.detail || "Scores could not be saved");
      }
    }} />
  </>;
}


function CollegeNavigation({ sections: items, active, onChange }) {
  const primaryItems = items.filter((item) => !item.administration);
  const administrationItems = items.filter((item) => item.administration);
  return <nav className="min-h-0 flex-1 overflow-y-auto p-3" aria-label="College placement sections">
    <div className="space-y-1">{primaryItems.map((item) => {
      const Icon = item.icon;
      return <button key={item.id} type="button" onClick={() => onChange(item.id)} className={`flex h-10 w-full items-center gap-3 rounded-lg px-3 text-left text-sm transition-colors ${active === item.id ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}>
        <Icon size={17} className="shrink-0" /><span className="truncate font-medium">{item.label}</span>
      </button>;
    })}</div>
    {administrationItems.length > 0 && <div className="mt-6 border-t pt-4">
      <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Administration</div>
      <div className="space-y-1">{administrationItems.map((item) => {
        const Icon = item.icon;
        return <button key={item.id} type="button" onClick={() => onChange(item.id)} className={`flex h-10 w-full items-center gap-3 rounded-lg px-3 text-left text-sm transition-colors ${active === item.id ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}><Icon size={17} className="shrink-0" /><span className="font-medium">{item.label}</span></button>;
      })}</div>
    </div>}
  </nav>;
}


function WorkspaceSection({ children, className = "" }) {
  return <div className={`mx-auto w-full max-w-[1500px] space-y-5 px-4 py-5 sm:px-6 lg:px-8 lg:py-7 ${className}`}>{children}</div>;
}


function StudentIntelligencePanel({ canManage, onCreate, onOpen }) {
  const [search, setSearch] = useState("");
  const [band, setBand] = useState("all");
  const query = useGetCollegeStudentIntelligenceQuery({
    q: search.trim() || undefined,
    readiness_band: band === "all" ? undefined : band,
    limit: 250,
  });
  const rows = query.data?.items || [];
  const filtered = Boolean(search.trim() || band !== "all");
  const columns = [
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number} / {row.program.code}</div></div> },
    { key: "readiness", label: "Readiness", render: (row) => <div className="min-w-28"><StatusBadge status={row.readiness_band === "ready" ? "active" : row.readiness_band === "needs_support" ? "warning" : row.readiness_band === "insufficient_evidence" ? "pending" : "scheduled"} label={row.readiness_band.replaceAll("_", " ")} />{row.readiness?.score != null && <div className="mt-1.5 text-xs text-muted-foreground">{row.readiness.score}% / {row.readiness.coverage_percent}% evidence</div>}</div> },
    { key: "cgpa", label: "CGPA", render: (row) => row.cgpa ?? "—" },
    { key: "attendance", label: "Attendance", render: (row) => <span className={row.attendance_percent != null && row.attendance_percent < 75 ? "font-semibold text-warning" : ""}>{row.attendance_percent == null ? "-" : `${row.attendance_percent}%`}</span> },
    { key: "coding", label: "Coding", render: (row) => row.coding_total == null ? <span className="text-muted-foreground">No profile</span> : `${row.coding_total} solved` },
    { key: "profile", label: "Profile", render: (row) => <StatusBadge status={row.resume_status === "reviewed" || row.resume_status === "approved" ? "completed" : "pending"} label={row.resume_status} /> },
    { key: "fee_clearance", label: "Internship clearance", render: (row) => <StatusBadge status={clearanceTone(row.fee_clearance_status)} label={internshipClearanceLabel(row.fee_clearance_status)} /> },
  ];
  return <WorkspaceSection>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search student, admission or roll number" className="sm:max-w-sm" />
      <Select value={band} onValueChange={setBand}><SelectTrigger className="sm:w-56"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All readiness bands</SelectItem><SelectItem value="ready">Ready</SelectItem><SelectItem value="developing">Developing</SelectItem><SelectItem value="needs_support">Needs support</SelectItem><SelectItem value="insufficient_evidence">Insufficient evidence</SelectItem></SelectContent></Select>
      {canManage && <Button className="sm:ml-auto" onClick={onCreate}><UserPlus className="mr-2" />Admit student</Button>}
    </div>
    <Surface className="overflow-hidden">
      <div className="flex items-center justify-between border-b px-4 py-4 sm:px-5"><div><h2 className="font-semibold">Student intelligence</h2><p className="mt-1 text-xs text-muted-foreground">{query.data?.total ?? 0} students in the current view</p></div></div>
      <DataTable className="rounded-none border-0 shadow-none" loading={query.isLoading} rows={rows} columns={columns} onRowClick={onOpen} empty={<EmptyState variant={filtered ? "filtered" : "section"} icon={Student} title={filtered ? "No students match this view" : "No students yet"} description={filtered ? "Clear the search or readiness filter." : "Admit students to begin placement intelligence."} primaryAction={filtered ? <Button variant="outline" onClick={() => { setSearch(""); setBand("all"); }}>Clear filters</Button> : canManage ? <Button onClick={onCreate}>Admit first student</Button> : null} />} />
    </Surface>
  </WorkspaceSection>;
}


function FeeClearancePanel({ data, loading, canManage, onCreatePlan, onAssign, onOpenInvoice }) {
  const rows = useMemo(() => feeClearanceRows(data), [data]);
  const metrics = [
    { id: "cleared", label: "Cleared students", value: rows.filter((row) => row.clearance_status === "cleared").length },
    { id: "pending", label: "Pending clearance", value: rows.filter((row) => row.clearance_status === "pending").length, tone: rows.some((row) => row.clearance_status === "pending") ? "warning" : "neutral" },
    { id: "not_assessed", label: "Needs assessment", value: rows.filter((row) => row.clearance_status === "not_assessed").length },
  ];
  const columns = [
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.student_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number || "No admission number"}</div></div> },
    { key: "clearance", label: "Clearance", render: (row) => <StatusBadge status={clearanceTone(row.clearance_status)} label={clearanceLabel(row.clearance_status)} /> },
    { key: "plans", label: "Assigned fees", render: (row) => row.plan_names.length ? <div><div>{row.plan_names.slice(0, 2).join(", ")}</div>{row.plan_names.length > 2 && <div className="mt-1 text-xs text-muted-foreground">+{row.plan_names.length - 2} more</div>}</div> : <span className="text-muted-foreground">Not assessed</span> },
    { key: "invoice", label: "Latest invoice", render: (row) => row.invoice_id ? <Button variant="ghost" size="sm" className="-ml-3" onClick={(event) => { event.stopPropagation(); onOpenInvoice(row.invoice_id); }}>{row.invoice_number || "Open invoice"}</Button> : <span className="text-muted-foreground">Not created</span> },
    { key: "outstanding", label: "Outstanding", render: (row) => row.clearance_status === "pending" ? <span className="font-semibold text-warning">{money(row.outstanding_paise)}</span> : <span className="text-muted-foreground">-</span> },
  ];
  return <WorkspaceSection>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div><h2 className="text-lg font-semibold">Internship fee clearance</h2><p className="mt-1 max-w-2xl text-sm text-muted-foreground">Only the clearance result appears in placement views. Amounts and invoices remain restricted to this administration area.</p></div>
      <div className="flex flex-wrap gap-2">{canManage && <Button variant="outline" onClick={onCreatePlan}>New fee plan</Button>}{canManage && <Button onClick={onAssign} disabled={!data?.students?.length || !data?.fee_plans?.length}>Assign fee</Button>}</div>
    </div>
    <MetricStrip metrics={metrics} loading={loading && !data} />
    <div className="grid items-start gap-5 xl:grid-cols-12">
      <Surface className="overflow-hidden xl:col-span-4">
        <PanelHeader title="Fee plans" copy="Reusable obligations by program, cohort, or term." />
        {(data?.fee_plans || []).length ? <div className="divide-y">{data.fee_plans.map((row) => <div key={row.id} className="flex items-start gap-3 px-4 py-4 sm:px-5"><div className="min-w-0 flex-1"><div className="truncate font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{[row.program_name, row.cohort_name, row.due_on ? `Due ${shortDate(row.due_on)}` : null].filter(Boolean).join(" / ") || "All students"}</div></div><span className="shrink-0 text-sm font-semibold">{money(row.amount_paise)}</span></div>)}</div> : <EmptyState variant="inline" alignment="left" icon={Receipt} title="No fee plan" description="Create a plan before assigning a fee obligation." primaryAction={canManage ? <Button variant="outline" size="sm" onClick={onCreatePlan}>Create plan</Button> : null} className="m-4" />}
      </Surface>
      <Surface className="overflow-hidden xl:col-span-8">
        <PanelHeader title="Student clearance" copy="A student is cleared only when every active College fee obligation is settled or waived." />
        <DataTable className="rounded-none border-0 shadow-none" loading={loading} rows={rows} columns={columns} empty={<EmptyState variant="inline" alignment="left" icon={Student} title="No students available" description="Admit students before assigning fee clearance obligations." className="m-4" />} />
      </Surface>
    </div>
  </WorkspaceSection>;
}


function feeClearanceRows(data) {
  const students = data?.students || [];
  const grouped = new Map(students.map((student) => [student.id, {
    id: student.id,
    student_name: student.display_name,
    admission_number: student.admission_number,
    clearance_status: student.fee_clearance_status || "not_assessed",
    plan_names: [],
    invoice_number: null,
    invoice_id: null,
    outstanding_paise: Number(student.fee_outstanding_paise || 0),
    has_authoritative_clearance: Boolean(student.fee_clearance_status),
  }]));
  for (const fee of data?.student_fees || []) {
    if (["void", "refunded"].includes(fee.invoice_status)) continue;
    const row = grouped.get(fee.student_profile_id) || {
      id: fee.student_profile_id,
      student_name: fee.student_name,
      admission_number: null,
      clearance_status: "not_assessed",
      plan_names: [],
      invoice_number: null,
      invoice_id: null,
      outstanding_paise: 0,
      has_authoritative_clearance: false,
    };
    row.plan_names.push(fee.fee_plan_name || "Assigned fee");
    row.invoice_number = row.invoice_number || fee.invoice_number;
    row.invoice_id = row.invoice_id || fee.invoice_id;
    if (!row.has_authoritative_clearance) {
      row.outstanding_paise += Number(fee.outstanding_paise || 0);
      row.clearance_status = row.outstanding_paise > 0 ? "pending" : "cleared";
    }
    grouped.set(row.id, row);
  }
  return [...grouped.values()].sort((left, right) => {
    const priority = { pending: 0, not_assessed: 1, cleared: 2 };
    return priority[left.clearance_status] - priority[right.clearance_status] || left.student_name.localeCompare(right.student_name);
  });
}


function BatchesPanel({ data, loading, onOpenStudents }) {
  const programs = Object.fromEntries((data?.programs || []).map((row) => [row.id, row]));
  const rows = data?.cohorts || [];
  return <WorkspaceSection>
    <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))] gap-4">
      {loading && !rows.length ? [1, 2, 3].map((key) => <Surface key={key} className="h-44 animate-pulse bg-secondary/50" />) : rows.map((row) => <Surface key={row.id} className="p-5">
        <div className="flex items-start justify-between gap-4"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><UsersThree size={20} /></span><StatusBadge status={row.is_active ? "active" : "inactive"} /></div>
        <h2 className="mt-5 font-semibold">{row.name}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{programs[row.program_id]?.name || row.program_name}</p>
        <div className="mt-5 grid grid-cols-3 gap-3 border-t pt-4"><BatchValue label="Students" value={row.student_count} /><BatchValue label="Semester" value={row.current_semester} /><BatchValue label="Section" value={row.section || "—"} /></div>
        <Button variant="ghost" size="sm" className="mt-4 -ml-3" onClick={onOpenStudents}>View students<ArrowRight /></Button>
      </Surface>)}
    </div>
    {!loading && !rows.length && <EmptyState variant="page" alignment="left" icon={UsersThree} title="No active batches" description="Create a program and cohort to organize students by graduation batch." />}
  </WorkspaceSection>;
}


function BatchValue({ label, value }) {
  return <div><div className="text-lg font-semibold">{value ?? 0}</div><div className="mt-1 text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{label}</div></div>;
}


function AcademicHub({ data, loading, can, onCreate, onScores }) {
  const [view, setView] = useState("structure");
  const views = [{ value: "structure", label: "Structure" }, { value: "timetable", label: "Timetable" }, { value: "attendance", label: "Attendance" }, { value: "assessments", label: "Assessments" }];
  return <WorkspaceSection>
    <div className="premium-scrollbar overflow-x-auto"><SegmentControl value={view} onChange={setView} items={views} /></div>
    {view === "structure" && <AcademicsPanel data={data} loading={loading} canManage={can("college.academics.manage")} onCreate={onCreate} />}
    {view === "timetable" && <TimetablePanel data={data} loading={loading} canManage={can("college.academics.manage")} onCreate={() => onCreate("offering")} />}
    {view === "attendance" && <AttendancePanel data={data} loading={loading} canManage={can("college.attendance.mark")} onCreate={() => onCreate("attendance")} />}
    {view === "assessments" && <AssessmentsPanel data={data} loading={loading} canManage={can("college.assessments.manage")} onCreate={() => onCreate("assessment")} onScores={onScores} />}
  </WorkspaceSection>;
}


function CodingIntelligencePanel() {
  const [windowDays, setWindowDays] = useState(30);
  const query = useGetCollegeLeaderboardsQuery({ window_days: windowDays, limit: 100 });
  const rows = query.data?.coding || [];
  const chartRows = rows.slice(0, 12).map((row) => ({ name: row.name.split(" ")[0], solved: row.total_solved || 0 }));
  const columns = [
    { key: "rank", label: "Rank", render: (row) => <span className="font-mono text-xs">#{row.rank}</span> },
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.department}</div></div> },
    { key: "solved", label: "Solved", render: (row) => <span className="font-semibold">{row.total_solved}</span> },
    { key: "mix", label: "Difficulty mix", render: (row) => <span className="text-xs text-muted-foreground">{row.easy} easy / {row.medium} medium / {row.hard} hard</span> },
    { key: "rating", label: "Contest rating", render: (row) => row.contest_rating ? Math.round(row.contest_rating) : "—" },
    { key: "fresh", label: "Last evidence", render: (row) => shortDate(row.captured_at) },
  ];
  return <WorkspaceSection>
    <div className="flex justify-end"><SegmentControl value={windowDays} onChange={setWindowDays} items={[{ value: 30, label: "30 days" }, { value: 90, label: "90 days" }]} /></div>
    <div className="grid items-start gap-5 xl:grid-cols-12">
      <Surface className="overflow-hidden xl:col-span-7"><PanelHeader title="Coding leaderboard" copy="Difficulty-weighted progress with contest evidence." /><div className="px-3 pb-4 sm:px-5"><BusinessChart data={chartRows} xKey="name" series={[{ key: "solved", label: "Solved" }]} type="bar" height={290} /></div></Surface>
      <Surface className="xl:col-span-5"><PanelHeader title="How this board works" copy="LeetCode is a supporting signal, never the only eligibility authority." /><div className="space-y-3 border-t p-5 text-sm text-muted-foreground"><p>Ranking considers solved difficulty mix, contest rating, and freshness.</p><p>Unavailable or private profiles remain visible in student records without lowering academic scores.</p><p>Daily synchronization preserves the latest successful snapshot during provider failures.</p></div></Surface>
    </div>
    <DataTable loading={query.isLoading} rows={rows} columns={columns} empty={<EmptyState variant="section" icon={Code} title="No coding evidence yet" description="Connect consented student profiles or import a coding snapshot." />} />
  </WorkspaceSection>;
}


function PlacementsPanel({ initialAction, onActionHandled }) {
  const { can } = useAuth();
  const canManageApplications = can("college.applications.manage");
  const canManageCompanies = can("college.companies.manage");
  const canManageOpportunities = can("college.opportunities.manage");
  const opportunities = useGetCollegeOpportunitiesQuery({ limit: 100 });
  const companies = useGetCollegeCompaniesQuery({ limit: 250 });
  const stages = useGetCollegePipelineStagesQuery();
  const dashboard = useGetCollegePlacementDashboardQuery({});
  const [opportunityFilter, setOpportunityFilter] = useState("all");
  const [drawer, setDrawer] = useState(() => initialAction === "company" ? "company" : initialAction ? "opportunity" : null);
  const applications = useGetCollegeApplicationsQuery({ opportunity_id: opportunityFilter === "all" ? undefined : opportunityFilter, limit: 250 });
  const students = useGetCollegeStudentIntelligenceQuery({ limit: 250 }, { skip: drawer !== "application" });
  const [createCompany, companyState] = useCreateCollegeCompanyMutation();
  const [createOpportunity, opportunityState] = useCreateCollegeOpportunityMutation();
  const [createApplication, applicationState] = useCreateCollegeApplicationMutation();
  const [moveApplication, moveState] = useMoveCollegeApplicationStageMutation();
  const rows = opportunities.data?.items || [];
  const active = rows.filter((row) => ["published", "active"].includes(row.status));
  useEffect(() => {
    if (initialAction) setDrawer(initialAction === "company" ? "company" : "opportunity");
  }, [initialAction]);
  const closeDrawer = () => { setDrawer(null); onActionHandled?.(); };
  const moveStage = async (application, stageId) => {
    try {
      await moveApplication({ applicationId: application.id, stageId, version: application.version, reason: "Updated from placement workspace" }).unwrap();
      toast.success("Application stage updated");
    } catch (error) {
      toast.error(error?.status === 409 ? "This application changed elsewhere. Refresh and try again." : error?.data?.detail || "Application stage could not be updated");
    }
  };
  const applicationColumns = [
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.student?.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.student?.admission_number}</div></div> },
    { key: "opportunity", label: "Opportunity", render: (row) => <div><div className="font-medium">{row.opportunity?.title}</div><div className="mt-1 text-xs text-muted-foreground">{row.company?.name}</div></div> },
    { key: "eligibility", label: "Eligibility", render: (row) => <StatusBadge status={row.eligibility_override_status || row.eligibility_status} label={sentence(row.eligibility_override_status || row.eligibility_status)} /> },
    { key: "stage", label: "Pipeline stage", render: (row) => canManageApplications ? <Select value={row.current_stage_id || row.stage?.id || ""} onValueChange={(value) => moveStage(row, value)} disabled={moveState.isLoading}><SelectTrigger className="h-9 min-w-44"><SelectValue placeholder="Choose stage" /></SelectTrigger><SelectContent>{(stages.data?.items || []).filter((stage) => stage.is_enabled).map((stage) => <SelectItem key={stage.id} value={stage.id}>{stage.name}</SelectItem>)}</SelectContent></Select> : <StatusBadge status={row.stage?.slug || "pending"} label={row.stage?.name || "Not assigned"} /> },
  ];
  return <WorkspaceSection>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="text-lg font-semibold">Opportunity pipeline</h2><p className="mt-1 text-sm text-muted-foreground">Companies, drives, eligibility, and student progression.</p></div><div className="flex flex-wrap gap-2">{canManageCompanies && <Button variant="outline" onClick={() => setDrawer("company")}>Add company</Button>}{canManageApplications && active.length > 0 && <Button variant="outline" onClick={() => setDrawer("application")}>Add applicant</Button>}{canManageOpportunities && <Button onClick={() => setDrawer("opportunity")}><Plus className="mr-2" />New drive</Button>}</div></div>
    <div className="grid items-start gap-5 xl:grid-cols-12">
      <Surface className="overflow-hidden xl:col-span-7"><PanelHeader title="Application funnel" copy="Applications across your configurable pipeline." /><div className="px-3 pb-4 sm:px-5"><BusinessChart data={(dashboard.data?.placement_funnel || []).filter((row) => row.value)} xKey="label" series={[{ key: "value", label: "Applications" }]} type="bar" height={290} /></div></Surface>
      <Surface className="overflow-hidden xl:col-span-5"><PanelHeader title="Pipeline stages" copy="Placement Heads can rename and reorder these stages." /><div className="divide-y border-t">{(stages.data?.items || []).map((row) => <div key={row.id} className="flex items-center gap-3 px-5 py-3"><span className="grid h-7 w-7 place-items-center rounded-lg bg-secondary font-mono text-[10px]">{row.display_order}</span><span className="min-w-0 flex-1 truncate text-sm font-medium">{row.name}</span>{row.is_terminal && <StatusBadge status={row.stage_type === "placed" ? "completed" : "closed"} label={row.stage_type} />}</div>)}</div></Surface>
    </div>
    <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))] gap-4">{active.map((row) => <Surface key={row.id} className="p-5"><div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Briefcase size={19} /></span><StatusBadge status={row.status} /></div><h3 className="mt-5 font-semibold">{row.title}</h3><p className="mt-1 text-sm text-muted-foreground">{row.company?.name}</p><div className="mt-5 space-y-2 border-t pt-4 text-xs text-muted-foreground"><div className="flex justify-between gap-3"><span>Drive</span><span className="font-medium text-foreground">{row.drive_at ? shortDate(row.drive_at) : "To be scheduled"}</span></div><div className="flex justify-between gap-3"><span>Location</span><span className="font-medium text-foreground">{row.work_location || "Flexible"}</span></div><div className="flex justify-between gap-3"><span>Package</span><span className="font-medium text-foreground">{packageRange(row)}</span></div></div></Surface>)}</div>
    {!opportunities.isLoading && !active.length && <EmptyState variant="section" alignment="left" icon={Briefcase} title="No active drives" description="Create an opportunity to evaluate students and begin the placement pipeline." primaryAction={canManageOpportunities ? <Button onClick={() => setDrawer("opportunity")}>Create drive</Button> : null} />}
    <Surface className="overflow-hidden"><PanelHeader title="Student applications" copy="Eligibility and progression across each placement drive." action={<Select value={opportunityFilter} onValueChange={setOpportunityFilter}><SelectTrigger className="w-52"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All opportunities</SelectItem>{rows.map((row) => <SelectItem key={row.id} value={row.id}>{row.title}</SelectItem>)}</SelectContent></Select>} /><DataTable className="rounded-none border-0 shadow-none" loading={applications.isLoading} rows={applications.data?.items || []} columns={applicationColumns} empty={<EmptyState variant="inline" icon={Briefcase} title="No applications in this view" description="Add an eligible student to begin tracking their placement progress." primaryAction={canManageApplications && active.length > 0 ? <Button variant="outline" size="sm" onClick={() => setDrawer("application")}>Add applicant</Button> : null} className="m-4" />} /></Surface>
    <PlacementDrawer mode={["company", "opportunity"].includes(drawer) ? drawer : null} onClose={closeDrawer} companies={companies.data?.items || []} departments={dashboard.data?.filters?.departments || []} pending={companyState.isLoading || opportunityState.isLoading} onCompany={async (payload) => { try { await createCompany(payload).unwrap(); toast.success("Company added"); closeDrawer(); } catch (error) { toast.error(error?.data?.detail || "Company could not be added"); } }} onOpportunity={async (payload) => { try { await createOpportunity(payload).unwrap(); toast.success("Placement drive created"); closeDrawer(); } catch (error) { toast.error(error?.data?.detail || "Drive could not be created"); } }} />
    <ApplicationDrawer open={drawer === "application"} onClose={closeDrawer} opportunities={active} students={students.data?.items || []} pending={applicationState.isLoading} onSubmit={async (payload) => { try { await createApplication(payload).unwrap(); toast.success("Student added to placement pipeline"); closeDrawer(); } catch (error) { toast.error(error?.data?.detail || (error?.status === 409 ? "This student is already in the selected drive." : "Application could not be created")); } }} />
  </WorkspaceSection>;
}


function PlacementDrawer({ mode, onClose, companies, departments, pending, onCompany, onOpportunity }) {
  const [company, setCompany] = useState({ name: "", industry: "", contact_email: "" });
  const [opportunity, setOpportunity] = useState({ company_id: "", title: "", opportunity_type: "campus_drive", status: "draft", work_location: "", department_id: "all", minimum_cgpa: "", maximum_backlogs: "", minimum_attendance: "", minimum_solved: "" });
  if (!mode) return null;
  const submit = (event) => {
    event.preventDefault();
    if (mode === "company") return onCompany(company);
    return onOpportunity({
      company_id: opportunity.company_id,
      title: opportunity.title,
      opportunity_type: opportunity.opportunity_type,
      status: opportunity.status,
      work_location: opportunity.work_location || null,
      eligibility_rules: {
        ...(opportunity.department_id !== "all" ? { department_ids: [opportunity.department_id] } : {}),
        ...(opportunity.minimum_cgpa ? { minimum_cgpa: Number(opportunity.minimum_cgpa) } : {}),
        ...(opportunity.maximum_backlogs ? { maximum_active_backlogs: Number(opportunity.maximum_backlogs) } : {}),
        ...(opportunity.minimum_attendance ? { minimum_attendance: Number(opportunity.minimum_attendance) } : {}),
        ...(opportunity.minimum_solved ? { minimum_solved: Number(opportunity.minimum_solved) } : {}),
      },
      rounds: [],
    });
  };
  return <DrawerForm open title={mode === "company" ? "Add placement company" : "Create placement drive"} description={mode === "company" ? "Store only the contact details your placement team needs." : "Optional details can be completed later without blocking the pipeline."} onClose={onClose} onSubmit={submit} footer={<Button type="submit" form="placement-form" disabled={pending}>{pending ? "Saving..." : mode === "company" ? "Add company" : "Create drive"}</Button>}>
    <form id="placement-form" onSubmit={submit} className="space-y-4">{mode === "company" ? <><Field label="Company name"><Input required value={company.name} onChange={(event) => setCompany({ ...company, name: event.target.value })} /></Field><Field label="Industry"><Input value={company.industry} onChange={(event) => setCompany({ ...company, industry: event.target.value })} /></Field><Field label="Contact email"><Input type="email" value={company.contact_email} onChange={(event) => setCompany({ ...company, contact_email: event.target.value })} /></Field></> : <><Field label="Company"><Select required value={opportunity.company_id} onValueChange={(value) => setOpportunity({ ...opportunity, company_id: value })}><SelectTrigger><SelectValue placeholder="Choose company" /></SelectTrigger><SelectContent>{companies.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select></Field><Field label="Role or drive title"><Input required value={opportunity.title} onChange={(event) => setOpportunity({ ...opportunity, title: event.target.value })} /></Field><Field label="Opportunity type"><Select value={opportunity.opportunity_type} onValueChange={(value) => setOpportunity({ ...opportunity, opportunity_type: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="campus_drive">Campus drive</SelectItem><SelectItem value="internship">Internship</SelectItem><SelectItem value="apprenticeship">Apprenticeship</SelectItem><SelectItem value="off_campus">Off campus</SelectItem></SelectContent></Select></Field>{opportunity.opportunity_type === "internship" && <div className="rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm"><div className="font-semibold">Fee clearance required</div><p className="mt-1 text-xs leading-5 text-muted-foreground">Only students with verified fee completion can be added to this internship.</p></div>}<div className="grid gap-4 sm:grid-cols-2"><Field label="Status"><Select value={opportunity.status} onValueChange={(value) => setOpportunity({ ...opportunity, status: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">Draft</SelectItem><SelectItem value="published">Published</SelectItem><SelectItem value="active">Active</SelectItem></SelectContent></Select></Field><Field label="Eligible department"><Select value={opportunity.department_id} onValueChange={(value) => setOpportunity({ ...opportunity, department_id: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All departments</SelectItem>{departments.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select></Field></div><Field label="Work location"><Input value={opportunity.work_location} onChange={(event) => setOpportunity({ ...opportunity, work_location: event.target.value })} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Minimum CGPA"><Input type="number" min="0" max="10" step="0.1" value={opportunity.minimum_cgpa} onChange={(event) => setOpportunity({ ...opportunity, minimum_cgpa: event.target.value })} /></Field><Field label="Maximum active backlogs"><Input type="number" min="0" max="100" value={opportunity.maximum_backlogs} onChange={(event) => setOpportunity({ ...opportunity, maximum_backlogs: event.target.value })} /></Field><Field label="Minimum attendance %"><Input type="number" min="0" max="100" value={opportunity.minimum_attendance} onChange={(event) => setOpportunity({ ...opportunity, minimum_attendance: event.target.value })} /></Field><Field label="Minimum coding solved"><Input type="number" min="0" value={opportunity.minimum_solved} onChange={(event) => setOpportunity({ ...opportunity, minimum_solved: event.target.value })} /></Field></div></>}</form>
  </DrawerForm>;
}


function ApplicationDrawer({ open, onClose, opportunities, students, pending, onSubmit }) {
  const [form, setForm] = useState({ opportunity_id: "", student_profile_id: "", notes: "" });
  useEffect(() => {
    if (!open) setForm({ opportunity_id: "", student_profile_id: "", notes: "" });
  }, [open]);
  const submit = (event) => {
    event.preventDefault();
    onSubmit({ ...form, notes: form.notes.trim() || null });
  };
  return <DrawerForm open={open} title="Add placement applicant" description="Eligibility is evaluated from current evidence and remains reviewable by authorized staff." onClose={onClose} onSubmit={submit} footer={<Button type="submit" form="application-form" disabled={pending || !form.opportunity_id || !form.student_profile_id}>{pending ? "Adding..." : "Add applicant"}</Button>}>
    <form id="application-form" onSubmit={submit} className="space-y-4"><Field label="Placement drive"><Select required value={form.opportunity_id} onValueChange={(opportunity_id) => setForm((current) => ({ ...current, opportunity_id }))}><SelectTrigger><SelectValue placeholder="Choose drive" /></SelectTrigger><SelectContent>{opportunities.map((row) => <SelectItem key={row.id} value={row.id}>{row.title} / {row.company?.name}</SelectItem>)}</SelectContent></Select></Field><Field label="Student"><Select required value={form.student_profile_id} onValueChange={(student_profile_id) => setForm((current) => ({ ...current, student_profile_id }))}><SelectTrigger><SelectValue placeholder="Choose student" /></SelectTrigger><SelectContent>{students.map((row) => <SelectItem key={row.id} value={row.id}>{row.name} / {row.admission_number}</SelectItem>)}</SelectContent></Select></Field><Field label="Coordinator note"><Textarea value={form.notes} onChange={setFormField(setForm, "notes")} placeholder="Optional context for the placement team" /></Field></form>
  </DrawerForm>;
}


function LeaderboardsPanel() {
  const [board, setBoard] = useState("readiness");
  const [windowDays, setWindowDays] = useState(30);
  const query = useGetCollegeLeaderboardsQuery({ window_days: windowDays, limit: 100 });
  const rows = query.data?.[board] || [];
  const columns = leaderboardColumns(board);
  return <WorkspaceSection>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><SegmentControl value={board} onChange={setBoard} items={[{ value: "readiness", label: "Readiness" }, { value: "coding", label: "Coding" }, { value: "academics", label: "Academics" }, { value: "improvement", label: "Improvement" }]} />{board === "improvement" && <SegmentControl value={windowDays} onChange={setWindowDays} items={[{ value: 30, label: "30 days" }, { value: 90, label: "90 days" }]} />}</div>
    <Surface className="overflow-hidden"><div className="border-b px-5 py-4"><h2 className="font-semibold">{sentence(board)} leaderboard</h2><p className="mt-1 text-xs text-muted-foreground">Multiple evidence boards keep achievements transparent and comparable.</p></div><DataTable className="rounded-none border-0 shadow-none" loading={query.isLoading} rows={rows} columns={columns} empty={<EmptyState variant="section" icon={Medal} title={`No ${board} evidence yet`} description="This board appears when the required student evidence is available." />} /></Surface>
  </WorkspaceSection>;
}


function DataImportsPanel() {
  const { can } = useAuth();
  const canManageIntegrations = can("college.integrations.manage");
  const imports = useGetCollegeImportsQuery({ limit: 50 });
  const integrations = useGetCollegeIntegrationsQuery(undefined, { skip: !canManageIntegrations });
  const [previewCsv, previewState] = usePreviewCollegeCsvImportMutation();
  const [commitImport, commitState] = useCommitCollegeImportMutation();
  const [createIntegration, createIntegrationState] = useCreateCollegeIntegrationMutation();
  const [queueSync, queueSyncState] = useQueueCollegeIntegrationSyncMutation();
  const [resourceType, setResourceType] = useState("students");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [connectorOpen, setConnectorOpen] = useState(false);
  const upload = async () => {
    if (!file) return toast.error("Choose a CSV file first");
    try { setPreview(await previewCsv({ file, resourceType }).unwrap()); } catch (error) { toast.error(error?.data?.detail || "CSV could not be validated"); }
  };
  const commit = async () => {
    try { const result = await commitImport(preview.id).unwrap(); toast.success(`${result.committed_count} rows imported`); setPreview(null); setFile(null); } catch (error) { toast.error(error?.data?.detail || "Import could not be committed"); }
  };
  const saveConnector = async (payload) => {
    try {
      await createIntegration(payload).unwrap();
      toast.success("ERP connector saved");
      setConnectorOpen(false);
    } catch (error) {
      toast.error(error?.data?.detail || "ERP connector could not be saved");
    }
  };
  const syncConnector = async (connectorId) => {
    try {
      await queueSync({
        connectorId,
        resourceTypes: collegeImportResources.map((row) => row.value),
        idempotencyKey: operationKey("erp-sync"),
      }).unwrap();
      toast.success("ERP synchronization queued");
    } catch (error) {
      toast.error(error?.data?.detail || "ERP synchronization could not be queued");
    }
  };
  return <WorkspaceSection>
    <div className="grid items-start gap-5 xl:grid-cols-12">
      <Surface className="p-5 xl:col-span-7"><div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Database size={20} /></span><div><h2 className="font-semibold">Import student evidence</h2><p className="mt-1 text-sm text-muted-foreground">CSV and ERP use the same validate, preview, and commit pipeline.</p></div></div><div className="mt-5 grid gap-3 sm:grid-cols-[190px_minmax(0,1fr)_auto]"><Select value={resourceType} onValueChange={setResourceType}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="students">Students</SelectItem><SelectItem value="term_results">Term results</SelectItem><SelectItem value="attendance">Attendance</SelectItem><SelectItem value="skills">Skills</SelectItem><SelectItem value="assessments">Assessments</SelectItem><SelectItem value="internship_clearance">Internship clearance</SelectItem></SelectContent></Select><Input type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} /><Button onClick={upload} disabled={previewState.isLoading}>{previewState.isLoading ? "Validating..." : "Preview"}</Button></div>{preview && <div className="mt-5 rounded-xl border bg-secondary/35 p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><div className="font-semibold">{preview.valid_count} of {preview.row_count} rows are ready</div><div className="mt-1 text-xs text-muted-foreground">{preview.failed_count ? `${preview.failed_count} rows need correction before or after a partial commit.` : "No validation errors found."}</div></div><Button onClick={commit} disabled={!preview.valid_count || commitState.isLoading}>{commitState.isLoading ? "Importing..." : "Commit valid rows"}</Button></div></div>}</Surface>
      <Surface className="overflow-hidden xl:col-span-5"><PanelHeader title="Connected ERP" copy="Read-only HTTPS pulls with masked credentials." action={canManageIntegrations ? <Button variant="outline" size="sm" onClick={() => setConnectorOpen(true)}>Connect ERP</Button> : null} /><div className="divide-y border-t">{(integrations.data?.items || []).map((row) => <div key={row.id} className="flex items-center gap-3 px-4 py-4 sm:px-5"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-secondary"><Database size={17} /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.name}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{row.last_sync_at ? `Last sync ${shortDate(row.last_sync_at)}` : "Not synchronized yet"}</span></span><StatusBadge status={row.status} /><Button variant="ghost" size="sm" disabled={!row.api_key_configured || ["queued", "syncing"].includes(row.status) || queueSyncState.isLoading} onClick={() => syncConnector(row.id)}>Sync</Button></div>)}{canManageIntegrations && !integrations.isLoading && !integrations.data?.items?.length && <EmptyState variant="inline" icon={Database} title="No ERP connector" description="Connect a read-only HTTPS endpoint, or continue with CSV imports." primaryAction={<Button variant="outline" size="sm" onClick={() => setConnectorOpen(true)}>Connect ERP</Button>} className="m-4" />}{!canManageIntegrations && <EmptyState variant="inline" icon={Database} title="ERP access is restricted" description="An integration administrator can manage synchronized sources." className="m-4" />}</div></Surface>
    </div>
    <Surface className="overflow-hidden"><PanelHeader title="Import history" copy="Committed rows, validation failures, and synchronization runs." /><DataTable className="rounded-none border-0 shadow-none" loading={imports.isLoading} rows={imports.data?.items || []} columns={[{ key: "resource_type", label: "Resource", render: (row) => sentence(row.resource_type.replaceAll("_", " ")) }, { key: "source_type", label: "Source", render: (row) => row.source_type.toUpperCase() }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }, { key: "rows", label: "Rows", render: (row) => `${row.committed_count}/${row.row_count}` }, { key: "created_at", label: "Started", render: (row) => shortDate(row.created_at) }]} empty={<EmptyState variant="inline" icon={Database} title="No import runs yet" description="Validated CSV and ERP runs will appear here." />} /></Surface>
    <ERPConnectorDrawer open={connectorOpen} onClose={() => setConnectorOpen(false)} pending={createIntegrationState.isLoading} onSubmit={saveConnector} />
  </WorkspaceSection>;
}


const collegeImportResources = [
  { value: "students", label: "Students", fields: ["external_id", "admission_number", "first_name", "last_name", "email", "phone", "program_code", "cohort_code", "current_semester"] },
  { value: "term_results", label: "Term results", fields: ["external_id", "admission_number", "semester", "sgpa", "cgpa", "active_backlogs", "total_backlogs", "credits_earned", "published_on"] },
  { value: "attendance", label: "Attendance", fields: ["external_id", "admission_number", "scope", "classes_held", "classes_attended", "attendance_percent", "as_of"] },
  { value: "skills", label: "Skills", fields: ["external_id", "admission_number", "title", "proficiency", "verified", "evidence_url"] },
  { value: "assessments", label: "Assessments", fields: ["external_id", "admission_number", "title", "assessment_type", "score_percent", "assessed_on", "provider"] },
  { value: "internship_clearance", label: "Internship clearance", fields: ["external_id", "admission_number", "status", "source_updated_at"] },
];


function ERPConnectorDrawer({ open, onClose, pending, onSubmit }) {
  const [resource, setResource] = useState("students");
  const [form, setForm] = useState(() => ({
    name: "", base_url: "", auth_mode: "bearer", auth_header: "X-API-Key", api_key: "",
    pagination_mode: "updated_since", cursor_param: "cursor", cursor_path: "meta.next_cursor",
    updated_since_param: "updated_since", next_url_path: "meta.next",
    resources: Object.fromEntries(collegeImportResources.map((item) => [item.value, {
      path: `/${item.value.replaceAll("_", "-")}`,
      root_path: "data",
      fields: Object.fromEntries(item.fields.map((field) => [field, field])),
    }])),
  }));
  const definition = collegeImportResources.find((item) => item.value === resource) || collegeImportResources[0];
  const resourceConfig = form.resources[resource];
  const updateResource = (key, value) => setForm((current) => ({
    ...current,
    resources: { ...current.resources, [resource]: { ...current.resources[resource], [key]: value } },
  }));
  const updateField = (field, value) => setForm((current) => ({
    ...current,
    resources: {
      ...current.resources,
      [resource]: {
        ...current.resources[resource],
        fields: { ...current.resources[resource].fields, [field]: value },
      },
    },
  }));
  const submit = (event) => {
    event.preventDefault();
    const pagination = form.pagination_mode === "none" ? {} : {
      mode: form.pagination_mode,
      cursor_param: form.cursor_param || undefined,
      cursor_path: form.cursor_path || undefined,
      updated_since_param: form.updated_since_param || undefined,
      next_url_path: form.next_url_path || undefined,
    };
    onSubmit({
      name: form.name,
      base_url: form.base_url,
      auth_mode: form.auth_mode,
      auth_header: form.auth_mode === "header" ? form.auth_header : null,
      api_key: form.api_key || null,
      mapping: { resources: form.resources },
      pagination,
      sync_interval_hours: 6,
    });
  };
  return <DrawerForm open={open} title="Connect College ERP" description="Configure a read-only HTTPS source. Credentials remain server-side and every run is previewed and audited." onClose={onClose} onSubmit={submit} footer={<Button type="submit" form="erp-connector-form" disabled={pending}>{pending ? "Connecting..." : "Save connector"}</Button>}>
    <form id="erp-connector-form" onSubmit={submit} className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2"><Field label="Connection name"><Input required value={form.name} onChange={setFormField(setForm, "name")} placeholder="Campus ERP" /></Field><Field label="HTTPS base URL"><Input required type="url" value={form.base_url} onChange={setFormField(setForm, "base_url")} placeholder="https://erp.college.edu/api" /></Field></div>
      <div className="grid gap-4 sm:grid-cols-2"><Field label="Authentication"><Select value={form.auth_mode} onValueChange={(auth_mode) => setForm((current) => ({ ...current, auth_mode }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="bearer">Bearer token</SelectItem><SelectItem value="header">Custom header</SelectItem></SelectContent></Select></Field>{form.auth_mode === "header" && <Field label="Header name"><Input required value={form.auth_header} onChange={setFormField(setForm, "auth_header")} /></Field>}<Field label="API key"><Input type="password" autoComplete="new-password" value={form.api_key} onChange={setFormField(setForm, "api_key")} placeholder="Stored encrypted" /></Field></div>
      <div className="border-t pt-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><h3 className="text-sm font-semibold">Resource mapping</h3><p className="mt-1 text-xs text-muted-foreground">Map Edvatiq fields to JSON paths returned by your ERP.</p></div><Select value={resource} onValueChange={setResource}><SelectTrigger className="sm:w-48"><SelectValue /></SelectTrigger><SelectContent>{collegeImportResources.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent></Select></div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2"><Field label="Endpoint path"><Input value={resourceConfig.path} onChange={(event) => updateResource("path", event.target.value)} /></Field><Field label="Rows root path"><Input value={resourceConfig.root_path} onChange={(event) => updateResource("root_path", event.target.value)} placeholder="data.items" /></Field></div>
        <div className="mt-4 grid gap-x-4 gap-y-3 sm:grid-cols-2">{definition.fields.map((field) => <Field key={field} label={sentence(field)}><Input value={resourceConfig.fields[field]} onChange={(event) => updateField(field, event.target.value)} placeholder={field} /></Field>)}</div>
      </div>
      <div className="border-t pt-5"><h3 className="text-sm font-semibold">Pagination and freshness</h3><div className="mt-4 grid gap-4 sm:grid-cols-2"><Field label="Pagination mode"><Select value={form.pagination_mode} onValueChange={(pagination_mode) => setForm((current) => ({ ...current, pagination_mode }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="updated_since">Updated since</SelectItem><SelectItem value="cursor">Cursor</SelectItem><SelectItem value="none">None</SelectItem></SelectContent></Select></Field>{form.pagination_mode === "updated_since" && <Field label="Updated-since parameter"><Input value={form.updated_since_param} onChange={setFormField(setForm, "updated_since_param")} /></Field>}{form.pagination_mode === "cursor" && <><Field label="Cursor request parameter"><Input value={form.cursor_param} onChange={setFormField(setForm, "cursor_param")} /></Field><Field label="Cursor response path"><Input value={form.cursor_path} onChange={setFormField(setForm, "cursor_path")} /></Field></>}<Field label="Next-page URL path"><Input value={form.next_url_path} onChange={setFormField(setForm, "next_url_path")} placeholder="meta.next" /></Field></div></div>
    </form>
  </DrawerForm>;
}


function leaderboardColumns(board) {
  const base = [{ key: "rank", label: "Rank", render: (row) => <span className="font-mono text-xs">#{row.rank}</span> }, { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.department} / {row.program}</div></div> }];
  if (board === "readiness") return [...base, { key: "score", label: "Score", render: (row) => row.score == null ? "—" : `${row.score}%` }, { key: "coverage", label: "Evidence", render: (row) => `${row.coverage_percent}%` }, { key: "band", label: "Band", render: (row) => <StatusBadge status={row.rankable ? row.band === "ready" ? "active" : "scheduled" : "pending"} label={row.rankable ? row.band : "Insufficient evidence"} /> }];
  if (board === "coding") return [...base, { key: "solved", label: "Solved", render: (row) => row.total_solved }, { key: "mix", label: "Difficulty", render: (row) => `${row.easy}/${row.medium}/${row.hard}` }, { key: "rating", label: "Rating", render: (row) => row.contest_rating ? Math.round(row.contest_rating) : "—" }];
  if (board === "academics") return [...base, { key: "cgpa", label: "CGPA" }, { key: "sgpa", label: "Latest SGPA" }, { key: "backlogs", label: "Active backlogs", render: (row) => row.active_backlogs || 0 }];
  return [...base, { key: "solved_change", label: "Solved change", render: (row) => row.solved_change == null ? "—" : `+${row.solved_change}` }, { key: "readiness_change", label: "Readiness change", render: (row) => row.readiness_change == null ? "—" : `${row.readiness_change > 0 ? "+" : ""}${row.readiness_change}` }];
}


function packageRange(row) {
  if (row.package_min_paise == null && row.package_max_paise == null) return "Not disclosed";
  const lakh = (value) => `₹${(Number(value || 0) / 10000000).toFixed(1)}L`;
  return row.package_max_paise && row.package_max_paise !== row.package_min_paise ? `${lakh(row.package_min_paise)}–${lakh(row.package_max_paise)}` : lakh(row.package_min_paise || row.package_max_paise);
}


function HeaderActions({ active, can, onOpen }) {
  if (active === "students" && can("college.students.manage")) return <Button onClick={() => onOpen("student")}><UserPlus className="mr-2" />Admit student</Button>;
  if (active === "academics" && can("college.academics.manage")) return <Button onClick={() => onOpen("course")}><Plus className="mr-2" />Add academic record</Button>;
  if (active === "timetable" && can("college.academics.manage")) return <Button onClick={() => onOpen("offering")}><Plus className="mr-2" />Schedule course</Button>;
  if (active === "attendance" && can("college.attendance.mark")) return <Button onClick={() => onOpen("attendance")}><CheckCircle className="mr-2" />Record attendance</Button>;
  if (active === "assessments" && can("college.assessments.manage")) return <Button onClick={() => onOpen("assessment")}><Plus className="mr-2" />New assessment</Button>;
  return null;
}


function Overview({ data, loading, range, setRange, can, onSection }) {
  const summary = data?.summary;
  const metrics = summary ? [
    { id: "students", label: "Active students", value: summary.active_students },
    { id: "attendance", label: `${range}-day attendance`, value: summary.attendance_percent, format: "percent", tone: summary.attendance_percent != null && summary.attendance_percent < 75 ? "warning" : "neutral" },
    { id: "classes", label: "Classes today", value: summary.classes_today },
    { id: "assessments", label: "Assessments due", value: summary.assessments_due },
  ] : [];
  const today = (new Date().getDay() + 6) % 7;
  const classes = (data?.offerings || []).flatMap((offering) => (offering.weekly_schedule || []).filter((slot) => slot.weekday === today).map((slot) => ({ ...slot, offering }))).sort((a, b) => String(a.starts_at).localeCompare(String(b.starts_at)));
  const assessments = (data?.assessments || []).filter((row) => row.status !== "closed").slice(0, 6);
  const emptyWorkspace = !loading && !(data?.departments?.length || data?.programs?.length || data?.students?.length);

  if (emptyWorkspace) return <EmptyState
    variant="page"
    alignment="left"
    icon={GraduationCap}
    title="Set up your academic foundation"
    description="Create a department, program, term, and cohort before admitting students or scheduling courses."
    primaryAction={can("college.academics.manage") ? <Button onClick={() => onSection("academics")}>Set up academics<ArrowRight className="ml-2" /></Button> : null}
    steps={[{ title: "Create structure" }, { title: "Admit students" }, { title: "Run the term" }]}
  />;

  return <>
    <div className="flex justify-end"><SegmentControl value={range} onChange={setRange} items={[7, 30, 90].map((value) => ({ value, label: `${value} days` }))} /></div>
    <MetricStrip metrics={metrics} loading={loading && !summary} />
    {data?.current_term && <Surface className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary text-primary-foreground"><CalendarBlank /></span><div><div className="text-sm font-semibold">{data.current_term.name}</div><div className="mt-0.5 text-xs text-muted-foreground">{data.current_term.academic_year} / {shortDate(data.current_term.starts_on)} to {shortDate(data.current_term.ends_on)}</div></div></div>
      <StatusBadge status={data.current_term.status} />
    </Surface>}
    <div className="grid items-start gap-5 xl:grid-cols-12">
      <Surface className="overflow-hidden xl:col-span-7">
        <PanelHeader title="Today&apos;s timetable" copy="Scheduled classes across the selected campus." action={<Button variant="ghost" size="sm" onClick={() => onSection("timetable")}>Full timetable<ArrowRight /></Button>} />
        {classes.length ? <div className="divide-y">{classes.slice(0, 7).map((row, index) => <div key={`${row.offering.id}:${index}`} className="flex items-center gap-3 px-4 py-3.5 sm:px-5"><span className="min-w-16 font-mono text-xs font-semibold">{shortTime(row.starts_at)}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.offering.course_name}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{row.offering.cohort_name} / {row.offering.faculty_name || "Faculty unassigned"}</span></span><span className="hidden text-xs text-muted-foreground sm:block">{row.room || row.offering.room || "Room TBA"}</span></div>)}</div> : <EmptyState variant="inline" icon={Clock} title="No classes scheduled today" description="The current weekly timetable has no classes for today." className="m-4" />}
      </Surface>
      <Surface className="overflow-hidden xl:col-span-5">
        <PanelHeader title="Upcoming assessments" copy="Open academic deadlines." action={can("college.assessments.view") ? <Button variant="ghost" size="sm" onClick={() => onSection("assessments")}>View all<ArrowRight /></Button> : null} />
        {assessments.length ? <div className="divide-y">{assessments.map((row) => <div key={row.id} className="flex items-start gap-3 px-4 py-3.5 sm:px-5"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-secondary"><Books size={16} /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.title}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{row.offering?.course_code} / {row.offering?.cohort_name}</span></span><span className="shrink-0 text-xs text-muted-foreground">{row.due_on ? shortDate(row.due_on) : "No date"}</span></div>)}</div> : <EmptyState variant="inline" icon={CheckCircle} title="No assessments due" description="There are no open assessment deadlines in this term." className="m-4" />}
      </Surface>
    </div>
    {!!data?.programs?.length && <Surface className="overflow-hidden"><PanelHeader title="Program position" copy="Enrollment across active programs." /><DataTable className="rounded-none border-0 shadow-none" rows={data.programs} columns={programColumns()} /></Surface>}
  </>;
}


function StudentsPanel({ data, loading, canManage, onCreate, onOpen }) {
  const [search, setSearch] = useState("");
  const [cohort, setCohort] = useState("all");
  const rows = useMemo(() => (data?.students || []).filter((row) => {
    const query = search.trim().toLowerCase();
    return (cohort === "all" || row.cohort_id === cohort) && (!query || [row.display_name, row.admission_number, row.roll_number, row.phone, row.email].some((value) => String(value || "").toLowerCase().includes(query)));
  }), [cohort, data?.students, search]);
  const filtered = Boolean(search || cohort !== "all");
  return <div className="space-y-4">
    <FilterBar><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, admission or roll number" className="sm:max-w-sm" /><Select value={cohort} onValueChange={setCohort}><SelectTrigger className="sm:w-64"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All cohorts</SelectItem>{(data?.cohorts || []).map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select>{canManage && <Button className="sm:ml-auto" onClick={onCreate}><UserPlus className="mr-2" />Admit student</Button>}</FilterBar>
    <DataTable loading={loading} rows={rows} columns={studentColumns()} onRowClick={onOpen} empty={<EmptyState variant={filtered ? "filtered" : "page"} alignment="left" icon={UsersThree} title={filtered ? "No students match these filters" : "No students admitted yet"} description={filtered ? "Change the cohort or clear the search." : "Admissions create a connected student profile with program and cohort context."} primaryAction={filtered ? <Button variant="outline" onClick={() => { setSearch(""); setCohort("all"); }}>Clear filters</Button> : canManage ? <Button onClick={onCreate}>Admit first student</Button> : null} />} />
  </div>;
}


function AcademicsPanel({ data, loading, canManage, onCreate }) {
  const [mode, setMode] = useState("departments");
  const definitions = {
    departments: { rows: data?.departments || [], columns: departmentColumns(), create: "department", label: "department" },
    programs: { rows: data?.programs || [], columns: programColumns(), create: "program", label: "program" },
    cohorts: { rows: data?.cohorts || [], columns: cohortColumns(), create: "cohort", label: "cohort" },
    courses: { rows: data?.courses || [], columns: courseColumns(), create: "course", label: "course" },
    terms: { rows: data?.terms || [], columns: termColumns(), create: "term", label: "term" },
  };
  const current = definitions[mode];
  return <div className="space-y-4">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><SegmentControl value={mode} onChange={setMode} items={academicModes} />{canManage && <Button onClick={() => onCreate(current.create)}><Plus className="mr-2" />Add {current.label}</Button>}</div>
    <DataTable loading={loading} rows={current.rows} columns={current.columns} empty={<EmptyState variant="section" alignment="left" icon={Books} title={`No ${current.label}s yet`} description="Add the first record to build the academic structure." primaryAction={canManage ? <Button onClick={() => onCreate(current.create)}>Add {current.label}</Button> : null} />} />
  </div>;
}


function TimetablePanel({ data, loading, canManage, onCreate }) {
  return <div className="space-y-4"><div className="flex justify-end">{canManage && <Button onClick={onCreate}><Plus className="mr-2" />Schedule course</Button>}</div><DataTable loading={loading} rows={data?.offerings || []} columns={offeringColumns()} empty={<EmptyState variant="page" alignment="left" icon={CalendarBlank} title="No course timetable yet" description="Assign courses to cohorts and faculty for the current term." primaryAction={canManage ? <Button onClick={onCreate}>Schedule first course</Button> : null} steps={[{ title: "Choose course" }, { title: "Assign cohort" }, { title: "Set weekly slot" }]} />} /></div>;
}


function AttendancePanel({ data, loading, canManage, onCreate }) {
  return <div className="space-y-4"><div className="flex justify-end">{canManage && <Button onClick={onCreate}><CheckCircle className="mr-2" />Record attendance</Button>}</div><DataTable loading={loading} rows={data?.attendance_sessions || []} columns={attendanceColumns()} empty={<EmptyState variant="page" alignment="left" icon={CheckCircle} title="No attendance sessions yet" description="Record attendance against a scheduled course offering." primaryAction={canManage ? <Button onClick={onCreate}>Record first session</Button> : null} />} /></div>;
}


function AssessmentsPanel({ data, loading, canManage, onCreate, onScores }) {
  return <div className="space-y-4"><div className="flex justify-end">{canManage && <Button onClick={onCreate}><Plus className="mr-2" />New assessment</Button>}</div><DataTable loading={loading} rows={data?.assessments || []} columns={assessmentColumns(canManage ? onScores : null)} empty={<EmptyState variant="page" alignment="left" icon={Books} title="No assessments created" description="Create an internal, assignment, practical, or semester assessment for a course offering." primaryAction={canManage ? <Button onClick={onCreate}>Create assessment</Button> : null} />} /></div>;
}


function StudentDrawer({ open, onClose, data, locationId, pending, onSubmit }) {
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", phone: "", admission_number: "", roll_number: "", program_id: "", cohort_id: "", current_semester: "1", admitted_on: isoToday(), guardian_name: "", guardian_phone: "" });
  const cohorts = (data?.cohorts || []).filter((row) => !form.program_id || row.program_id === form.program_id);
  const submit = (event) => {
    event.preventDefault();
    onSubmit({
      first_name: form.first_name, last_name: form.last_name,
      email: form.email || null, phone: form.phone || null,
      admission_number: form.admission_number, roll_number: form.roll_number || null,
      program_id: form.program_id, cohort_id: form.cohort_id,
      current_semester: Number(form.current_semester), admitted_on: form.admitted_on,
      home_location_id: locationId,
      guardian: form.guardian_name || form.guardian_phone ? { name: form.guardian_name, phone: form.guardian_phone } : {},
    });
  };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title="Admit student" description="Create one connected identity for academics, evidence, documents, placement, and AI."><form onSubmit={submit} className="space-y-5">
    <div className="grid gap-4 sm:grid-cols-2"><Field label="First name"><Input required value={form.first_name} onChange={setFormField(setForm, "first_name")} /></Field><Field label="Last name"><Input value={form.last_name} onChange={setFormField(setForm, "last_name")} /></Field><Field label="Admission number"><Input required value={form.admission_number} onChange={setFormField(setForm, "admission_number")} /></Field><Field label="Roll number"><Input value={form.roll_number} onChange={setFormField(setForm, "roll_number")} /></Field><Field label="Email"><Input type="email" value={form.email} onChange={setFormField(setForm, "email")} /></Field><Field label="Phone"><Input value={form.phone} onChange={setFormField(setForm, "phone")} /></Field></div>
    <div className="grid gap-4 sm:grid-cols-2"><Field label="Program"><Select required value={form.program_id} onValueChange={(program_id) => setForm((current) => ({ ...current, program_id, cohort_id: "" }))}><SelectTrigger><SelectValue placeholder="Choose program" /></SelectTrigger><SelectContent>{(data?.programs || []).map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select></Field><Field label="Cohort"><Select required value={form.cohort_id} onValueChange={(cohort_id) => setForm((current) => ({ ...current, cohort_id }))}><SelectTrigger><SelectValue placeholder="Choose cohort" /></SelectTrigger><SelectContent>{cohorts.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select></Field><Field label="Current semester"><Input required type="number" min="1" max="16" value={form.current_semester} onChange={setFormField(setForm, "current_semester")} /></Field><Field label="Admission date"><Input required type="date" value={form.admitted_on} onChange={setFormField(setForm, "admitted_on")} /></Field></div>
    <div className="border-t pt-5"><div className="mb-3 text-sm font-semibold">Guardian contact</div><div className="grid gap-4 sm:grid-cols-2"><Field label="Name"><Input value={form.guardian_name} onChange={setFormField(setForm, "guardian_name")} /></Field><Field label="Phone"><Input value={form.guardian_phone} onChange={setFormField(setForm, "guardian_phone")} /></Field></div></div>
    <Button className="w-full" disabled={pending}>{pending ? "Admitting..." : "Admit student"}</Button>
  </form></DrawerForm>;
}


function FeePlanDrawer({ open, onClose, data, pending, onSubmit }) {
  const [form, setForm] = useState({ name: "", amount: "", due_on: "", program_id: "", cohort_id: "", term_id: "" });
  useEffect(() => {
    if (!open) setForm({ name: "", amount: "", due_on: "", program_id: "", cohort_id: "", term_id: "" });
  }, [open]);
  const cohorts = (data?.cohorts || []).filter((row) => !form.program_id || row.program_id === form.program_id);
  const submit = (event) => {
    event.preventDefault();
    const amountPaise = Math.round(Number(form.amount) * 100);
    onSubmit({
      name: form.name.trim(),
      program_id: form.program_id || null,
      cohort_id: form.cohort_id || null,
      term_id: form.term_id || null,
      amount_paise: amountPaise,
      due_on: form.due_on || null,
      line_items: [{ name: form.name.trim(), amount_paise: amountPaise }],
    });
  };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title="Create fee plan" description="Keep fee setup in administration. Placement screens will only show the resulting clearance status.">
    <form onSubmit={submit} className="space-y-4">
      <Field label="Plan name"><Input required value={form.name} onChange={setFormField(setForm, "name")} placeholder="Semester 3 tuition" /></Field>
      <div className="grid gap-4 sm:grid-cols-2"><Field label="Amount"><Input required type="number" min="0.01" step="0.01" value={form.amount} onChange={setFormField(setForm, "amount")} placeholder="25000" /></Field><Field label="Due date"><Input type="date" value={form.due_on} onChange={setFormField(setForm, "due_on")} /></Field></div>
      <Field label="Program"><ReferenceSelect optional value={form.program_id} onChange={(program_id) => setForm((current) => ({ ...current, program_id, cohort_id: "" }))} rows={data?.programs} placeholder="All programs" /></Field>
      <Field label="Cohort"><ReferenceSelect optional value={form.cohort_id} onChange={(cohort_id) => setForm((current) => ({ ...current, cohort_id }))} rows={cohorts} placeholder="All cohorts" /></Field>
      <Field label="Term"><ReferenceSelect optional value={form.term_id} onChange={(term_id) => setForm((current) => ({ ...current, term_id }))} rows={data?.terms} placeholder="No specific term" /></Field>
      <Button className="w-full" disabled={pending || !form.name.trim() || Number(form.amount) <= 0}>{pending ? "Creating..." : "Create fee plan"}</Button>
    </form>
  </DrawerForm>;
}


function StudentFeeDrawer({ open, onClose, data, pending, onSubmit }) {
  const [form, setForm] = useState({ student_profile_id: "", fee_plan_id: "", concession: "0" });
  useEffect(() => {
    if (!open) setForm({ student_profile_id: "", fee_plan_id: "", concession: "0" });
  }, [open]);
  const student = (data?.students || []).find((row) => row.id === form.student_profile_id);
  const plans = (data?.fee_plans || []).filter((row) => (
    (!row.program_id || row.program_id === student?.program_id)
    && (!row.cohort_id || row.cohort_id === student?.cohort_id)
  ));
  const plan = plans.find((row) => row.id === form.fee_plan_id);
  const concessionPaise = Math.round(Number(form.concession || 0) * 100);
  const submit = (event) => {
    event.preventDefault();
    onSubmit({
      student_profile_id: form.student_profile_id,
      fee_plan_id: form.fee_plan_id,
      concession_paise: concessionPaise,
      idempotency_key: operationKey("college-fee"),
    });
  };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title="Assign student fee" description="Assigning a fee creates its linked invoice. Clearance updates automatically after payment or a full concession.">
    <form onSubmit={submit} className="space-y-4">
      <Field label="Student"><ReferenceSelect value={form.student_profile_id} onChange={(student_profile_id) => setForm((current) => ({ ...current, student_profile_id, fee_plan_id: "" }))} rows={data?.students} placeholder="Choose student" /></Field>
      <Field label="Fee plan"><ReferenceSelect value={form.fee_plan_id} onChange={(fee_plan_id) => setForm((current) => ({ ...current, fee_plan_id }))} rows={plans} placeholder={student ? "Choose applicable plan" : "Choose a student first"} label={(row) => `${row.name} / ${money(row.amount_paise)}`} /></Field>
      <Field label="Concession"><Input type="number" min="0" max={plan ? Number(plan.amount_paise) / 100 : undefined} step="0.01" value={form.concession} onChange={setFormField(setForm, "concession")} /></Field>
      {plan && <div className="rounded-xl border bg-secondary/35 p-4 text-sm"><div className="flex justify-between gap-3"><span className="text-muted-foreground">Fee amount</span><strong>{money(plan.amount_paise)}</strong></div><div className="mt-2 flex justify-between gap-3"><span className="text-muted-foreground">Invoice total</span><strong>{money(Math.max(0, Number(plan.amount_paise) - concessionPaise))}</strong></div></div>}
      <Button className="w-full" disabled={pending || !form.student_profile_id || !form.fee_plan_id || concessionPaise > Number(plan?.amount_paise || 0)}>{pending ? "Assigning..." : "Assign fee and create invoice"}</Button>
    </form>
  </DrawerForm>;
}


function AcademicDrawer({ mode, open, onClose, data, locationId, pending, onSubmit }) {
  const year = new Date().getFullYear();
  const [form, setForm] = useState({ name: "", code: "", department_id: "", degree_type: "undergraduate", duration_semesters: "6", academic_year: `${year}-${year + 1}`, term_number: "1", starts_on: `${year}-07-01`, ends_on: `${year + 1}-05-31`, is_current: false, program_id: "", admission_year: String(year), current_semester: "1", section: "", advisor_employee_id: "", credits: "3", course_type: "core" });
  if (!mode) return null;
  const submit = (event) => {
    event.preventDefault();
    const payloads = {
      department: { name: form.name, code: form.code, location_id: locationId },
      program: { name: form.name, code: form.code, department_id: form.department_id, degree_type: form.degree_type, duration_semesters: Number(form.duration_semesters) },
      term: { name: form.name, academic_year: form.academic_year, term_number: Number(form.term_number), starts_on: form.starts_on, ends_on: form.ends_on, is_current: form.is_current, status: form.is_current ? "active" : "planned" },
      cohort: { name: form.name, code: form.code, program_id: form.program_id, admission_year: Number(form.admission_year), current_semester: Number(form.current_semester), section: form.section || null, advisor_employee_id: form.advisor_employee_id || null },
      course: { name: form.name, code: form.code, department_id: form.department_id, credits: Number(form.credits), course_type: form.course_type },
    };
    onSubmit(mode, payloads[mode]);
  };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title={`Add ${mode}`} description="Academic structure remains connected to the active term and campus."><form onSubmit={submit} className="space-y-4">
    <Field label="Name"><Input required value={form.name} onChange={setFormField(setForm, "name")} /></Field>
    {mode !== "term" && <Field label="Code"><Input required value={form.code} onChange={setFormField(setForm, "code")} /></Field>}
    {["program", "course"].includes(mode) && <Field label="Department"><ReferenceSelect value={form.department_id} onChange={(department_id) => setForm((current) => ({ ...current, department_id }))} rows={data?.departments} placeholder="Choose department" /></Field>}
    {mode === "program" && <div className="grid gap-4 sm:grid-cols-2"><Field label="Degree type"><Select value={form.degree_type} onValueChange={(degree_type) => setForm((current) => ({ ...current, degree_type }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["undergraduate", "postgraduate", "diploma", "certificate"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></Field><Field label="Semesters"><Input type="number" min="1" max="16" value={form.duration_semesters} onChange={setFormField(setForm, "duration_semesters")} /></Field></div>}
    {mode === "term" && <><div className="grid gap-4 sm:grid-cols-2"><Field label="Academic year"><Input required value={form.academic_year} onChange={setFormField(setForm, "academic_year")} /></Field><Field label="Term number"><Input required type="number" min="1" max="16" value={form.term_number} onChange={setFormField(setForm, "term_number")} /></Field><Field label="Starts on"><Input required type="date" value={form.starts_on} onChange={setFormField(setForm, "starts_on")} /></Field><Field label="Ends on"><Input required type="date" value={form.ends_on} onChange={setFormField(setForm, "ends_on")} /></Field></div><label className="flex items-center gap-3 rounded-xl border p-3 text-sm"><input type="checkbox" checked={form.is_current} onChange={(event) => setForm((current) => ({ ...current, is_current: event.target.checked }))} />Make this the current term</label></>}
    {mode === "cohort" && <><Field label="Program"><ReferenceSelect value={form.program_id} onChange={(program_id) => setForm((current) => ({ ...current, program_id }))} rows={data?.programs} placeholder="Choose program" /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Admission year"><Input type="number" min="2000" max="2200" value={form.admission_year} onChange={setFormField(setForm, "admission_year")} /></Field><Field label="Current semester"><Input type="number" min="1" max="16" value={form.current_semester} onChange={setFormField(setForm, "current_semester")} /></Field><Field label="Section"><Input value={form.section} onChange={setFormField(setForm, "section")} /></Field><Field label="Advisor"><ReferenceSelect optional value={form.advisor_employee_id} onChange={(advisor_employee_id) => setForm((current) => ({ ...current, advisor_employee_id }))} rows={data?.employees} placeholder="Unassigned" /></Field></div></>}
    {mode === "course" && <div className="grid gap-4 sm:grid-cols-2"><Field label="Credits"><Input type="number" min="0" max="30" value={form.credits} onChange={setFormField(setForm, "credits")} /></Field><Field label="Course type"><Select value={form.course_type} onValueChange={(course_type) => setForm((current) => ({ ...current, course_type }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["core", "elective", "lab", "project", "audit"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></Field></div>}
    <Button className="w-full" disabled={pending}>{pending ? "Saving..." : `Create ${mode}`}</Button>
  </form></DrawerForm>;
}


function OfferingDrawer({ open, onClose, data, pending, onSubmit }) {
  const [form, setForm] = useState({ term_id: data?.current_term?.id || "", course_id: "", cohort_id: "", faculty_employee_id: "", room: "", weekday: "0", starts_at: "09:00", ends_at: "10:00" });
  const submit = (event) => { event.preventDefault(); onSubmit({ term_id: form.term_id, course_id: form.course_id, cohort_id: form.cohort_id, faculty_employee_id: form.faculty_employee_id || null, room: form.room || null, weekly_schedule: [{ weekday: Number(form.weekday), starts_at: form.starts_at, ends_at: form.ends_at, room: form.room || null }] }); };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title="Schedule course" description="Assign a course, cohort, faculty member, and weekly class slot."><form onSubmit={submit} className="space-y-4"><Field label="Term"><ReferenceSelect value={form.term_id} onChange={(term_id) => setForm((current) => ({ ...current, term_id }))} rows={data?.terms} placeholder="Choose term" /></Field><Field label="Course"><ReferenceSelect value={form.course_id} onChange={(course_id) => setForm((current) => ({ ...current, course_id }))} rows={data?.courses} placeholder="Choose course" label={(row) => `${row.code} / ${row.name}`} /></Field><Field label="Cohort"><ReferenceSelect value={form.cohort_id} onChange={(cohort_id) => setForm((current) => ({ ...current, cohort_id }))} rows={data?.cohorts} placeholder="Choose cohort" /></Field><Field label="Faculty"><ReferenceSelect optional value={form.faculty_employee_id} onChange={(faculty_employee_id) => setForm((current) => ({ ...current, faculty_employee_id }))} rows={data?.employees} placeholder="Unassigned" /></Field><div className="grid grid-cols-2 gap-4"><Field label="Weekday"><Select value={form.weekday} onValueChange={(weekday) => setForm((current) => ({ ...current, weekday }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{weekdays.map((label, index) => <SelectItem key={label} value={String(index)}>{label}</SelectItem>)}</SelectContent></Select></Field><Field label="Room"><Input value={form.room} onChange={setFormField(setForm, "room")} /></Field><Field label="Starts"><Input required type="time" value={form.starts_at} onChange={setFormField(setForm, "starts_at")} /></Field><Field label="Ends"><Input required type="time" value={form.ends_at} onChange={setFormField(setForm, "ends_at")} /></Field></div><Button className="w-full" disabled={pending}>{pending ? "Scheduling..." : "Schedule course"}</Button></form></DrawerForm>;
}


function AttendanceDrawer({ open, onClose, data, pending, onSubmit }) {
  const [form, setForm] = useState({ offering_id: "", held_on: isoToday(), starts_at: "", ends_at: "", topic: "" });
  const [statuses, setStatuses] = useState({});
  const offering = (data?.offerings || []).find((row) => row.id === form.offering_id);
  const students = (data?.students || []).filter((row) => row.cohort_id === offering?.cohort_id);
  const statusFor = (id) => statuses[id] || "present";
  const submit = (event) => { event.preventDefault(); onSubmit({ ...form, starts_at: form.starts_at || null, ends_at: form.ends_at || null, topic: form.topic || null, records: students.map((row) => ({ student_profile_id: row.id, status: statusFor(row.id) })) }); };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title="Record attendance" description="Every enrolled student in the selected cohort is included."><form onSubmit={submit} className="space-y-4"><Field label="Course offering"><ReferenceSelect value={form.offering_id} onChange={(offering_id) => { setForm((current) => ({ ...current, offering_id })); setStatuses({}); }} rows={data?.offerings} placeholder="Choose scheduled course" label={(row) => `${row.course_code} / ${row.cohort_name}`} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Date"><Input required type="date" value={form.held_on} onChange={setFormField(setForm, "held_on")} /></Field><Field label="Topic"><Input value={form.topic} onChange={setFormField(setForm, "topic")} /></Field><Field label="Starts"><Input type="time" value={form.starts_at} onChange={setFormField(setForm, "starts_at")} /></Field><Field label="Ends"><Input type="time" value={form.ends_at} onChange={setFormField(setForm, "ends_at")} /></Field></div>{offering && <div className="max-h-[42vh] divide-y overflow-y-auto rounded-xl border premium-scrollbar">{students.map((row) => <div key={row.id} className="flex items-center gap-3 p-3"><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.display_name}</span><span className="text-xs text-muted-foreground">{row.roll_number || row.admission_number}</span></span><Select value={statusFor(row.id)} onValueChange={(status) => setStatuses((current) => ({ ...current, [row.id]: status }))}><SelectTrigger className="w-32"><SelectValue /></SelectTrigger><SelectContent>{["present", "absent", "late", "excused"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></div>)}</div>}<Button className="w-full" disabled={pending || !offering || !students.length}>{pending ? "Recording..." : `Record ${students.length} students`}</Button></form></DrawerForm>;
}


function AssessmentDrawer({ open, onClose, data, pending, onSubmit }) {
  const [form, setForm] = useState({ offering_id: "", title: "", assessment_type: "internal", max_marks: "100", weightage: "20", due_on: "", status: "draft" });
  const submit = (event) => { event.preventDefault(); onSubmit({ offering_id: form.offering_id, title: form.title, assessment_type: form.assessment_type, max_marks: Number(form.max_marks), weightage_bps: Math.round(Number(form.weightage || 0) * 100), due_on: form.due_on || null, status: form.status }); };
  return <DrawerForm open={open} onOpenChange={(value) => !value && onClose()} title="New assessment" description="Create an assessment against an active course offering."><form onSubmit={submit} className="space-y-4"><Field label="Course offering"><ReferenceSelect value={form.offering_id} onChange={(offering_id) => setForm((current) => ({ ...current, offering_id }))} rows={data?.offerings} placeholder="Choose course" label={(row) => `${row.course_code} / ${row.cohort_name}`} /></Field><Field label="Title"><Input required value={form.title} onChange={setFormField(setForm, "title")} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Type"><Select value={form.assessment_type} onValueChange={(assessment_type) => setForm((current) => ({ ...current, assessment_type }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["internal", "assignment", "quiz", "practical", "project", "semester"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></Field><Field label="Due date"><Input type="date" value={form.due_on} onChange={setFormField(setForm, "due_on")} /></Field><Field label="Maximum marks"><Input required type="number" min="1" step="0.01" value={form.max_marks} onChange={setFormField(setForm, "max_marks")} /></Field><Field label="Weightage (%)"><Input type="number" min="0" max="100" step="0.01" value={form.weightage} onChange={setFormField(setForm, "weightage")} /></Field></div><Button className="w-full" disabled={pending}>{pending ? "Creating..." : "Create assessment"}</Button></form></DrawerForm>;
}


function ScoreDrawer({ assessment, onClose, data, pending, onSubmit }) {
  const [scores, setScores] = useState({});
  if (!assessment) return null;
  const students = (data?.students || []).filter((row) => row.cohort_id === assessment.offering?.cohort_id);
  const submit = (event) => { event.preventDefault(); onSubmit({ assessmentId: assessment.id, publish: event.nativeEvent.submitter?.value === "publish", scores: students.map((row) => ({ student_profile_id: row.id, marks_awarded: scores[row.id] === "" || scores[row.id] == null ? null : Number(scores[row.id]) })) }); };
  return <DrawerForm open onOpenChange={(value) => !value && onClose()} title={`Scores / ${assessment.title}`} description={`${assessment.offering?.course_code || "Course"} / Maximum ${assessment.max_marks} marks`}><form onSubmit={submit} className="space-y-4"><div className="max-h-[58vh] divide-y overflow-y-auto rounded-xl border premium-scrollbar">{students.map((row) => <div key={row.id} className="flex items-center gap-3 p-3"><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{row.display_name}</span><span className="text-xs text-muted-foreground">{row.roll_number || row.admission_number}</span></span><Input className="w-28" type="number" min="0" max={assessment.max_marks} step="0.01" value={scores[row.id] ?? ""} onChange={(event) => setScores((current) => ({ ...current, [row.id]: event.target.value }))} placeholder="Marks" /></div>)}</div><div className="flex gap-2"><Button type="submit" value="draft" variant="outline" className="flex-1" disabled={pending || !students.length}>Save draft</Button><Button type="submit" value="publish" className="flex-1" disabled={pending || !students.length}>Publish results</Button></div></form></DrawerForm>;
}


function ReferenceSelect({ value, onChange, rows = [], placeholder, label = (row) => row.display_name || row.name, optional = false }) {
  return <Select required={!optional} value={value || (optional ? "none" : "")} onValueChange={(next) => onChange(next === "none" ? "" : next)}><SelectTrigger><SelectValue placeholder={placeholder} /></SelectTrigger><SelectContent>{optional && <SelectItem value="none">{placeholder}</SelectItem>}{rows.map((row) => <SelectItem key={row.id} value={row.id}>{label(row)}</SelectItem>)}</SelectContent></Select>;
}


function PanelHeader({ title, copy, action }) {
  return <div className="flex flex-col gap-3 border-b px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-5"><div><h2 className="font-display text-lg font-semibold">{title}</h2>{copy && <p className="mt-1 text-xs text-muted-foreground">{copy}</p>}</div>{action}</div>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function setFormField(setter, key) { return (event) => setter((current) => ({ ...current, [key]: event.target.value })); }
function initialDrawer(params) { const value = params.get("new"); const section = params.get("section"); if (!value) return null; if (section === "students") return "student"; if (section === "attendance") return "attendance"; if (section === "academics") return value === "course" ? "course" : value; if (section === "fees") return value === "plan" ? "fee-plan" : "student-fee"; return null; }
function academicMode(value) { return ["department", "program", "term", "cohort", "course"].includes(value) ? value : null; }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function clearanceLabel(value) { return value === "cleared" ? "Cleared" : value === "pending" ? "Pending" : "Needs review"; }
function internshipClearanceLabel(value) { return value === "cleared" ? "Eligible" : value === "pending" ? "Fee action needed" : "Not assessed"; }
function clearanceTone(value) { return value === "cleared" ? "active" : value === "pending" ? "warning" : "pending"; }
function isoToday() { return new Date().toISOString().slice(0, 10); }
function shortDate(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${String(value).slice(0, 10)}T00:00:00`)) : "-"; }
function shortTime(value) { if (!value) return "TBA"; const [hour, minute] = String(value).split(":"); return new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit" }).format(new Date(2000, 0, 1, Number(hour), Number(minute))); }
function operationKey(prefix) { return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`; }
function money(paise = 0) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise) / 100); }
function scheduleText(rows = []) { return rows.length ? rows.map((row) => `${weekdays[row.weekday]} ${shortTime(row.starts_at)}`).join(", ") : "Not scheduled"; }

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const departmentColumns = () => [{ key: "name", label: "Department" }, { key: "code", label: "Code" }, { key: "program_count", label: "Programs" }];
const programColumns = () => [{ key: "name", label: "Program" }, { key: "code", label: "Code" }, { key: "department_name", label: "Department" }, { key: "student_count", label: "Students" }, { key: "duration_semesters", label: "Semesters" }];
const cohortColumns = () => [{ key: "name", label: "Cohort" }, { key: "program_name", label: "Program" }, { key: "admission_year", label: "Admitted" }, { key: "current_semester", label: "Semester" }, { key: "student_count", label: "Students" }];
const courseColumns = () => [{ key: "code", label: "Code" }, { key: "name", label: "Course" }, { key: "department_name", label: "Department" }, { key: "credits", label: "Credits" }, { key: "course_type", label: "Type", render: (row) => sentence(row.course_type) }];
const termColumns = () => [{ key: "name", label: "Term" }, { key: "academic_year", label: "Academic year" }, { key: "dates", label: "Dates", render: (row) => `${shortDate(row.starts_on)} - ${shortDate(row.ends_on)}` }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} label={row.is_current ? "Current" : undefined} /> }];
const studentColumns = () => [{ key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.display_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number}{row.roll_number ? ` / ${row.roll_number}` : ""}</div></div> }, { key: "program_name", label: "Program" }, { key: "cohort_name", label: "Cohort" }, { key: "current_semester", label: "Semester" }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }];
const offeringColumns = () => [{ key: "course", label: "Course", render: (row) => <div><div className="font-semibold">{row.course_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.course_code}</div></div> }, { key: "cohort_name", label: "Cohort" }, { key: "faculty_name", label: "Faculty", render: (row) => row.faculty_name || "Unassigned" }, { key: "schedule", label: "Weekly schedule", render: (row) => scheduleText(row.weekly_schedule) }, { key: "room", label: "Room", render: (row) => row.room || "TBA" }];
const attendanceColumns = () => [{ key: "date", label: "Date", render: (row) => shortDate(row.held_on) }, { key: "course", label: "Course", render: (row) => `${row.offering?.course_code || "Course"} / ${row.offering?.cohort_name || "Cohort"}` }, { key: "topic", label: "Topic", render: (row) => row.topic || "Class session" }, { key: "attendance", label: "Present", render: (row) => row.record_count ? `${row.present_count}/${row.record_count}` : "Not marked" }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }];
const assessmentColumns = (onScores) => [{ key: "title", label: "Assessment" }, { key: "course", label: "Course", render: (row) => `${row.offering?.course_code || "Course"} / ${row.offering?.cohort_name || "Cohort"}` }, { key: "due_on", label: "Due", render: (row) => shortDate(row.due_on) }, { key: "score_count", label: "Scores" }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }, ...(onScores ? [{ key: "actions", label: "", render: (row) => <Button size="sm" variant="outline" onClick={(event) => { event.stopPropagation(); onScores(row); }}>Enter scores</Button> }] : [])];
