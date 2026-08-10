import React from "react";
import {
  Briefcase, CheckCircle, Clock, Code, FileText, GraduationCap,
  Medal, ShieldCheck, Target, TrendUp, WarningCircle,
} from "@phosphor-icons/react";

import BusinessChart from "@/components/charts/BusinessChart";
import { EmptyState, ErrorState, StatusBadge, Surface, formatMetric } from "@/components/system";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";


const profileTabs = [
  { value: "overview", label: "Overview" },
  { value: "academics", label: "Academic evidence" },
  { value: "coding", label: "Coding & skills" },
  { value: "placements", label: "Placements" },
  { value: "activity", label: "Activity" },
];


export default function CollegeStudentProfile({ query, canReviewFees = false, onReviewFees, defaultTab = "overview" }) {
  if (query.isLoading && !query.data) return <ProfileLoading />;
  if (query.isError && !query.data) return <ErrorState title="Student intelligence could not be loaded" description={query.error?.data?.detail} retry={query.refetch} />;

  const data = query.data;
  if (!data) return <EmptyState variant="section" alignment="left" icon={GraduationCap} title="Placement profile is not connected" description="The student can still be managed, but their placement intelligence record needs to be linked." />;

  const initialTab = profileTabs.some((tab) => tab.value === defaultTab) ? defaultTab : "overview";
  return <Tabs defaultValue={initialTab}>
    <div className="flex min-w-0">
      <TabsList className="premium-scrollbar h-auto max-w-full justify-start overflow-x-auto rounded-xl p-1">
        {profileTabs.map((tab) => <TabsTrigger key={tab.value} value={tab.value}>{tab.label}</TabsTrigger>)}
      </TabsList>
    </div>

    <TabsContent value="overview" className="mt-5"><StudentOverview data={data} canReviewFees={canReviewFees} onReviewFees={onReviewFees} /></TabsContent>
    <TabsContent value="academics" className="mt-5"><Academics data={data} /></TabsContent>
    <TabsContent value="coding" className="mt-5"><CodingAndSkills data={data} /></TabsContent>
    <TabsContent value="placements" className="mt-5"><Placements data={data} canReviewFees={canReviewFees} onReviewFees={onReviewFees} /></TabsContent>
    <TabsContent value="activity" className="mt-5"><StudentActivity rows={data.activity || []} /></TabsContent>
  </Tabs>;
}


function StudentOverview({ data, canReviewFees, onReviewFees }) {
  const readiness = data.readiness || {};
  const career = data.career || {};
  const factors = Object.entries(readiness.factors || {});
  const applications = data.applications || [];
  const interventions = (data.interventions || []).filter((row) => row.status !== "resolved");
  const offers = applications.flatMap((item) => item.offers || []);
  const latestAcademic = data.academics?.[0];
  const latestAttendance = data.attendance?.[0];
  const latestCoding = data.coding?.snapshots?.[0];
  return <div className="grid items-start gap-5 xl:grid-cols-12">
    <Surface className="overflow-hidden xl:col-span-8">
      <PanelHeader eyebrow="Placement readiness" title="Evidence-backed readiness" copy={`Policy v${readiness.policy_version || "-"}; missing evidence lowers coverage, not the score.`} />
      <div className="grid gap-px border-t bg-border lg:grid-cols-[220px_1fr]">
        <div className="bg-card p-5 sm:p-6">
          <div className="text-5xl font-semibold tracking-[-0.06em]">{readiness.score == null ? "-" : Math.round(readiness.score)}</div>
          <div className="mt-3 flex flex-wrap gap-2"><StatusBadge status={readiness.band} label={sentence(readiness.band)} /><StatusBadge status={readiness.rankable ? "active" : "warning"} label={`${Math.round(readiness.coverage_percent || 0)}% coverage`} /></div>
          <p className="mt-4 text-xs leading-5 text-muted-foreground">Calculated {dateTime(readiness.calculated_at)}</p>
        </div>
        <div className="grid gap-px bg-border sm:grid-cols-2">
          {factors.map(([key, factor]) => <Factor key={key} label={sentence(key)} value={factor?.value} available={factor?.available !== false && factor?.value != null} />)}
        </div>
      </div>
    </Surface>

    <Surface className="overflow-hidden xl:col-span-4">
      <PanelHeader eyebrow="Placement direction" title="Career profile" />
      <div className="grid gap-px border-t bg-border sm:grid-cols-2 xl:grid-cols-1">
        <InfoCell label="Participation" value={sentence(career.participation_status || "not configured")} />
        <InfoCell label="Placement status" value={sentence(career.placement_status || "preparing")} />
        <InfoCell label="Resume" value={sentence(career.resume_status || "not uploaded")} warning={!career.resume_status || career.resume_status === "missing"} />
        <InfoCell label="Preferred roles" value={career.preferred_roles?.join(", ") || "Not recorded"} />
      </div>
    </Surface>

    <section className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,210px),1fr))] gap-3 xl:col-span-12" aria-label="Student evidence summary">
      <Metric icon={GraduationCap} label="Current CGPA" value={latestAcademic?.cgpa ?? "-"} detail={`${latestAcademic?.active_backlogs || 0} active backlogs`} warning={(latestAcademic?.active_backlogs || 0) > 0} />
      <Metric icon={CheckCircle} label="Attendance" value={latestAttendance?.attendance_percent == null ? "-" : `${latestAttendance.attendance_percent}%`} detail="Latest imported snapshot" warning={latestAttendance?.attendance_percent != null && latestAttendance.attendance_percent < 75} />
      <Metric icon={Code} label="Coding solved" value={latestCoding?.total ?? "-"} detail={data.coding?.account?.username || "Profile not connected"} />
      <Metric icon={Briefcase} label="Placement activity" value={applications.length} detail={`${offers.length} recorded offers`} />
    </section>

    {(readiness.missing_evidence || []).length > 0 && <Surface className="border-warning/30 bg-warning/5 p-4 sm:p-5 xl:col-span-12">
      <div className="flex items-start gap-3"><WarningCircle className="mt-0.5 shrink-0 text-warning" size={21} /><div><h3 className="font-semibold">Evidence needs review</h3><p className="mt-1 text-sm text-muted-foreground">Add or verify {readiness.missing_evidence.map(sentence).join(", ")} to improve confidence. The student remains visible and manageable.</p></div></div>
    </Surface>}
    {interventions.length > 0 && <Surface className="overflow-hidden xl:col-span-12">
      <PanelHeader eyebrow="Student support" title="Active interventions" copy="Placement and academic follow-up owned by the staff team." />
      <div className="divide-y border-t">{interventions.map((row) => <RecordRow key={row.id} title={row.title} meta={[row.note, row.due_on ? `Due ${shortDate(row.due_on)}` : null].filter(Boolean).join(" / ") || "No additional note"} aside={<StatusBadge status={row.priority === "urgent" || row.priority === "high" ? "warning" : row.status} label={`${sentence(row.priority)} priority`} />} />)}</div>
    </Surface>}
  </div>;
}


function Academics({ data }) {
  const academics = data.academics || [];
  const attendance = data.attendance || [];
  const assessments = data.assessments || [];
  if (!academics.length && !attendance.length && !assessments.length) return <EmptyState variant="section" alignment="left" icon={GraduationCap} title="No academic evidence yet" description="Import term results, attendance, or placement assessments to build this view." />;
  const cgpaData = [...academics].reverse().map((row) => ({ semester: `Sem ${row.semester}`, cgpa: row.cgpa, sgpa: row.sgpa }));
  const attendanceData = [...attendance].reverse().map((row) => ({ date: shortDate(row.as_of), attendance: row.attendance_percent }));
  return <div className="space-y-5">
    <div className="grid items-start gap-5 xl:grid-cols-2">
      {cgpaData.length > 0 && <ChartCard title="CGPA history" copy="Semester movement, with SGPA for context."><BusinessChart data={cgpaData} xKey="semester" series={[{ key: "cgpa", label: "CGPA" }, { key: "sgpa", label: "SGPA" }]} type="line" height={280} ariaLabel="CGPA and SGPA history" /></ChartCard>}
      {attendanceData.length > 0 && <ChartCard title="Attendance trend" copy="Imported course and term snapshots."><BusinessChart data={attendanceData} xKey="date" series={[{ key: "attendance", label: "Attendance %" }]} type="area" height={280} ariaLabel="Student attendance trend" /></ChartCard>}
    </div>
    <div className="grid items-start gap-5 xl:grid-cols-2">
      {academics.length > 0 && <Surface className="overflow-hidden"><PanelHeader title="Term results" /><div className="divide-y">{academics.map((row) => <RecordRow key={row.id} title={`Semester ${row.semester}`} meta={`SGPA ${row.sgpa ?? "-"} / CGPA ${row.cgpa ?? "-"}`} aside={<StatusBadge status={row.active_backlogs ? "warning" : "active"} label={row.active_backlogs ? `${row.active_backlogs} backlogs` : "No active backlog"} />} />)}</div></Surface>}
      {assessments.length > 0 && <Surface className="overflow-hidden"><PanelHeader title="Placement assessments" /><div className="divide-y">{assessments.map((row) => <RecordRow key={row.id} title={row.title} meta={`${sentence(row.type)} / ${shortDate(row.assessed_on)}`} aside={<strong>{row.score_percent == null ? "-" : `${row.score_percent}%`}</strong>} />)}</div></Surface>}
    </div>
  </div>;
}


function Coding({ data }) {
  const account = data.coding?.account;
  const snapshots = data.coding?.snapshots || [];
  if (!account && !snapshots.length) return <EmptyState variant="section" alignment="left" icon={Code} title="Coding profile is not connected" description="A verified public profile or CSV snapshot can be added without blocking placement activity." />;
  const latest = snapshots[0] || {};
  const trend = [...snapshots].reverse().map((row) => ({ date: shortDate(row.captured_at), total: row.total, easy: row.easy, medium: row.medium, hard: row.hard }));
  return <div className="space-y-5">
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric icon={Code} label="Total solved" value={latest.total ?? "-"} detail={account?.username || "Imported snapshot"} />
      <Metric icon={CheckCircle} label="Easy" value={latest.easy ?? "-"} />
      <Metric icon={Target} label="Medium" value={latest.medium ?? "-"} />
      <Metric icon={Medal} label="Hard" value={latest.hard ?? "-"} detail={latest.contest_rating ? `Rating ${latest.contest_rating}` : "No contest rating"} />
    </div>
    {trend.length > 0 && <ChartCard title="Problem-solving progress" copy="Historical snapshots are retained when a connector is unavailable."><BusinessChart data={trend} xKey="date" series={[{ key: "total", label: "Total solved" }, { key: "medium", label: "Medium" }, { key: "hard", label: "Hard" }]} type="line" height={310} ariaLabel="Coding progress history" /></ChartCard>}
    {account && <Surface className="overflow-hidden"><PanelHeader title="Connected profile" /><div className="grid gap-px border-t bg-border sm:grid-cols-2 lg:grid-cols-4"><InfoCell label="Platform" value={sentence(account.platform)} /><InfoCell label="Username" value={account.username} /><InfoCell label="Verification" value={sentence(account.verification_status)} /><InfoCell label="Last successful sync" value={dateTime(account.last_success_at)} /></div></Surface>}
  </div>;
}


function CodingAndSkills({ data }) {
  const account = data.coding?.account;
  const snapshots = data.coding?.snapshots || [];
  const evidence = data.evidence || {};
  const career = data.career || {};
  const hasEvidence = ["skill", "project", "certification"].some((key) => evidence[key]?.length)
    || (career.resume_status && career.resume_status !== "missing");
  if (!account && !snapshots.length && !hasEvidence) return <EmptyState variant="section" alignment="left" icon={Code} title="No coding or reviewed profile evidence" description="Connect a coding profile or review resume evidence when it becomes available. Placement work can continue without it." />;
  return <div className="space-y-5">{(account || snapshots.length > 0) && <Coding data={data} />}{hasEvidence && <Evidence data={data} />}</div>;
}


function Evidence({ data }) {
  const career = data.career || {};
  const evidence = data.evidence || {};
  const hasEvidence = ["skill", "project", "certification"].some((key) => evidence[key]?.length);
  return <div className="space-y-5">
    <Surface className="overflow-hidden">
      <PanelHeader eyebrow="Resume" title="Profile completeness" copy="Resume extraction remains a draft until staff reviews it." />
      <div className="grid gap-px border-t bg-border sm:grid-cols-2 lg:grid-cols-4">
        <InfoCell label="Resume status" value={sentence(career.resume_status || "not uploaded")} warning={!career.resume_status || career.resume_status === "missing"} />
        <InfoCell label="LinkedIn" value={career.linkedin_url || "Not recorded"} />
        <InfoCell label="GitHub" value={career.github_url || "Not recorded"} />
        <InfoCell label="Portfolio" value={career.portfolio_url || "Not recorded"} />
      </div>
    </Surface>
    {hasEvidence ? <div className="grid items-start gap-5 xl:grid-cols-3">
      <EvidenceGroup title="Verified skills" rows={evidence.skill || []} empty="No verified skills" />
      <EvidenceGroup title="Projects" rows={evidence.project || []} empty="No projects" />
      <EvidenceGroup title="Certifications" rows={evidence.certification || []} empty="No certifications" />
    </div> : <EmptyState variant="section" alignment="left" icon={FileText} title="No reviewed profile evidence" description="Resume extraction, skills, projects, and certifications will appear after staff verification." />}
  </div>;
}


function Placements({ data, canReviewFees, onReviewFees }) {
  const applications = data.applications || [];
  const clearance = data.fee_clearance || { status: "needs_review" };
  return <div className="space-y-4">
    <Surface className={`flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between ${clearance.status === "pending" ? "border-warning/40" : ""}`}>
      <div className="flex items-start gap-3"><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary ${clearance.status === "pending" ? "text-warning" : "text-muted-foreground"}`}><ShieldCheck /></span><div><div className="text-sm font-semibold">Internship prerequisite</div><p className="mt-1 text-xs leading-5 text-muted-foreground">{clearanceCopy(clearance)}</p></div></div>
      <div className="flex items-center gap-2"><StatusBadge status={clearance.status === "cleared" ? "active" : clearance.status === "pending" ? "warning" : "pending"} label={clearanceLabel(clearance.status)} />{canReviewFees && clearance.status !== "cleared" && <Button variant="outline" size="sm" onClick={onReviewFees}>Review</Button>}</div>
    </Surface>
    {!applications.length ? <EmptyState variant="section" alignment="left" icon={Briefcase} title="No placement applications yet" description="Eligible opportunities and applications will appear here without requiring every enrichment field." /> : <div className="grid items-start gap-4 lg:grid-cols-2">
    {applications.map((application) => {
      const offer = application.offers?.[0];
      const interview = application.interviews?.[0];
      return <Surface key={application.id} className="overflow-hidden">
        <div className="p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-muted-foreground">{application.company?.name}</p><h3 className="mt-1 text-lg font-semibold">{application.opportunity?.title}</h3></div><StatusBadge status={application.stage?.slug || application.opportunity?.status} label={application.stage?.name || sentence(application.opportunity?.status)} /></div>
          <div className="mt-4 flex flex-wrap gap-2"><StatusBadge status={application.eligibility_status} label={sentence(application.eligibility_status)} />{application.outcome && <StatusBadge status={application.outcome} />}</div>
        </div>
        <div className="grid gap-px border-t bg-border sm:grid-cols-2">
          <InfoCell label="Latest interview" value={interview ? `${sentence(interview.type)} / ${sentence(interview.status)}` : "Not scheduled"} />
          <InfoCell label="Offer" value={offer ? `${sentence(offer.status)}${offer.package_paise ? ` / ${money(offer.package_paise)}` : ""}` : "Not recorded"} />
        </div>
      </Surface>;
    })}
    </div>}
  </div>;
}


function StudentActivity({ rows }) {
  if (!rows.length) return <EmptyState variant="section" alignment="left" icon={Clock} title="No intelligence activity yet" description="Academic imports, coding syncs, and application stage changes will appear here." />;
  return <Surface className="overflow-hidden"><PanelHeader title="Student success activity" copy="Normalized academic, coding, and placement events." /><ol className="divide-y border-t">{rows.map((row, index) => <li key={`${row.source_id || index}:${row.at}`} className="flex gap-3 p-4 sm:p-5"><span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary">{activityIcon(row.type)}</span><div className="min-w-0 flex-1"><h3 className="font-semibold">{row.title}</h3>{row.detail && <p className="mt-1 text-sm text-muted-foreground">{row.detail}</p>}<p className="mt-2 text-xs text-muted-foreground">{dateTime(row.at)}</p></div></li>)}</ol></Surface>;
}


function ChartCard({ title, copy, children }) { return <Surface className="overflow-hidden"><PanelHeader title={title} copy={copy} /><div className="px-3 pb-4 sm:px-5">{children}</div></Surface>; }
function PanelHeader({ eyebrow, title, copy }) { return <div className="p-4 sm:p-5">{eyebrow && <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{eyebrow}</p>}<h2 className={`${eyebrow ? "mt-1" : ""} text-lg font-semibold tracking-[-0.025em]`}>{title}</h2>{copy && <p className="mt-1 text-xs leading-5 text-muted-foreground">{copy}</p>}</div>; }
function Factor({ label, value, available }) { return <div className="bg-card p-4"><div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold text-muted-foreground">{label}</span><span className="text-sm font-semibold">{available ? Math.round(value) : "-"}</span></div><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-primary" style={{ width: `${available ? Math.max(2, Math.min(100, value)) : 0}%` }} /></div></div>; }
function InfoCell({ label, value, warning }) { return <div className="min-w-0 bg-card p-4"><div className="text-[11px] text-muted-foreground">{label}</div><div className={`mt-1.5 break-words text-sm font-semibold ${warning ? "text-warning" : ""}`}>{value}</div></div>; }
function Metric({ icon: Icon, label, value, detail, warning, action }) { return <Surface className="p-4 sm:p-5"><div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold text-muted-foreground">{label}</span><span className={`grid h-8 w-8 place-items-center rounded-lg bg-secondary ${warning ? "text-warning" : "text-muted-foreground"}`}><Icon size={17} /></span></div><div className={`mt-4 text-3xl font-semibold tracking-[-0.04em] ${warning ? "text-warning" : ""}`}>{value}</div>{detail && <p className="mt-1.5 text-xs text-muted-foreground">{detail}</p>}{action}</Surface>; }
function RecordRow({ title, meta, aside }) { return <div className="flex items-center gap-3 p-4 sm:p-5"><div className="min-w-0 flex-1"><div className="font-semibold">{title}</div><div className="mt-1 text-xs text-muted-foreground">{meta}</div></div>{aside}</div>; }
function EvidenceGroup({ title, rows, empty }) { return <Surface className="overflow-hidden"><PanelHeader title={title} />{rows.length ? <div className="divide-y border-t">{rows.map((row) => <div key={row.id} className="p-4"><div className="flex items-start justify-between gap-3"><div className="font-semibold">{row.title}</div>{row.verified && <StatusBadge status="active" label="Verified" />}</div>{(row.issuer || row.proficiency) && <p className="mt-1 text-xs text-muted-foreground">{[row.issuer, row.proficiency].filter(Boolean).join(" / ")}</p>}{row.description && <p className="mt-2 text-sm leading-6 text-muted-foreground">{row.description}</p>}</div>)}</div> : <p className="border-t p-4 text-sm text-muted-foreground">{empty}</p>}</Surface>; }
function ProfileLoading() { return <div className="space-y-5"><div className="h-11 w-full animate-pulse rounded-xl bg-secondary sm:w-[42rem]" /><div className="grid gap-5 xl:grid-cols-12"><div className="h-72 animate-pulse rounded-2xl bg-secondary xl:col-span-8" /><div className="h-72 animate-pulse rounded-2xl bg-secondary xl:col-span-4" /></div></div>; }
function activityIcon(type) { if (type === "coding_snapshot") return <Code />; if (type === "application_stage") return <Briefcase />; return <TrendUp />; }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function clearanceLabel(status) { return status === "cleared" ? "Eligible" : status === "pending" ? "Action needed" : "Not assessed"; }
function clearanceCopy(clearance) { if (clearance.status === "cleared") return `Clearance evidence is current${clearance.as_of ? ` as of ${shortDate(clearance.as_of)}` : ""}.`; if (clearance.status === "pending") return "Confirmed pending clearance blocks internship participation. Placement staff cannot override it."; return "Clearance evidence is missing or stale and must be reviewed before internship participation."; }
function shortDate(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(value)) : "-"; }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)) : "Not available"; }
function money(value) { return formatMetric(value || 0, "money"); }
