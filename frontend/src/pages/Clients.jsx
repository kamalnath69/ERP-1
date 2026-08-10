import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight, Cards, List, MagnifyingGlass, Plus, UserPlus, UsersThree,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { EntityAvatar } from "@/components/entities/EntityProfile";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip,
  PageHeader, PageShell, SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { profileRef } from "@/lib/profileNavigation";
import { QUERY_POLICIES } from "@/store/api/queryPolicies";
import { useCreateClientMutation, useGetClientDirectoryQuery } from "@/store/api/workspaceApi";
import { clientLabel } from "@/app/routeManifest";
import {
  useAdmitCollegeStudentMutation,
  useGetCollegePlacementDashboardQuery,
  useGetCollegeReferencesQuery,
  useGetCollegeStudentIntelligenceQuery,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";

const emptyClient = {
  first_name: "", last_name: "", phone: "", email: "", address: "",
  date_of_birth: "", gender: "", home_location_id: "", notes: "", tags: "",
  whatsapp_consent: false, email_consent: false,
};

const emptyStudent = {
  first_name: "", last_name: "", email: "", phone: "", admission_number: "",
  roll_number: "", program_id: "", cohort_id: "", current_semester: "1",
  admitted_on: new Date().toISOString().slice(0, 10), home_location_id: "",
};

export default function Clients() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const { industry, locations, locationId } = useBusiness();
  const isCollege = industry === "college";
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(() => searchParams.get("q") || "");
  const deferredQuery = useDeferredValue(query.trim());
  const requestedSegment = searchParams.get("segment") || "all";
  const collegeSegments = ["all", "ready", "developing", "needs_support", "insufficient_evidence"];
  const segment = isCollege && !collegeSegments.includes(requestedSegment) ? "all" : requestedSegment;
  const [view, setView] = useState(() => localStorage.getItem("edvatiq.clients.view") || "table");
  const [drawerOpen, setDrawerOpen] = useState(() => searchParams.get("new") === "1");
  const [form, setForm] = useState(emptyClient);
  const [studentForm, setStudentForm] = useState(emptyStudent);
  const [createClient, createState] = useCreateClientMutation();
  const [admitStudent, admitState] = useAdmitCollegeStudentMutation();

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (deferredQuery) next.set("q", deferredQuery); else next.delete("q");
    if (next.toString() !== searchParams.toString()) setSearchParams(next, { replace: true });
  }, [deferredQuery, searchParams, setSearchParams]);

  const pageKey = JSON.stringify({ industry, locationId, q: deferredQuery, segment });
  const paging = useCursorPagination(pageKey);

  const clientDirectory = useGetClientDirectoryQuery(
    { locationId, q: deferredQuery, segment, limit: 25, cursor: paging.cursor },
    { ...QUERY_POLICIES.operational, skip: isCollege },
  );
  const collegeDirectory = useGetCollegeStudentIntelligenceQuery({
    q: deferredQuery || undefined,
    readiness_band: segment === "all" ? undefined : segment,
    cursor: paging.cursor || undefined,
    limit: 25,
  }, { skip: !isCollege });
  const references = useGetCollegeReferencesQuery(undefined, { skip: !isCollege || !drawerOpen });
  const collegeDashboard = useGetCollegePlacementDashboardQuery({}, { skip: !isCollege });
  const directory = isCollege ? collegeDirectory : clientDirectory;
  const data = directory.data;
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(data); }, [acceptPage, data]);
  const items = paging.items;
  const plural = clientLabel(industry);
  const singular = clientLabel(industry, false);
  const isClinic = industry === "clinic";
  const openCreate = () => {
    setDrawerOpen(true);
    const next = new URLSearchParams(searchParams);
    next.set("new", "1");
    setSearchParams(next, { replace: true });
  };

  const closeDrawer = (open) => {
    setDrawerOpen(open);
    if (open) return;
    const next = new URLSearchParams(searchParams);
    next.delete("new");
    setSearchParams(next, { replace: true });
  };

  const setSegment = (value) => {
    const next = new URLSearchParams(searchParams);
    if (value === "all") next.delete("segment"); else next.set("segment", value);
    setSearchParams(next, { replace: true });
  };
  const chooseView = (value) => {
    setView(value);
    localStorage.setItem("edvatiq.clients.view", value);
  };
  const openProfile = (item) => navigate(`/app/clients/${item.client_id || item.id}`, {
    state: { profileFrom: `${window.location.pathname}${window.location.search}` },
  });

  const submit = async (event) => {
    event.preventDefault();
    try {
      const created = await createClient({
        ...form,
        email: form.email || null,
        phone: form.phone || null,
        address: form.address || null,
        date_of_birth: form.date_of_birth || null,
        gender: form.gender || null,
        home_location_id: form.home_location_id || locationId || null,
        notes: form.notes || null,
        tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      }).unwrap();
      toast.success(`${singular} created`);
      setDrawerOpen(false);
      setForm(emptyClient);
      navigate(`/app/clients/${created.id}`);
    } catch (error) {
      toast.error(error?.data?.detail || `Could not create ${singular.toLowerCase()}`);
    }
  };

  const submitStudent = async (event) => {
    event.preventDefault();
    try {
      const created = await admitStudent({
        ...studentForm,
        email: studentForm.email || null,
        phone: studentForm.phone || null,
        roll_number: studentForm.roll_number || null,
        home_location_id: studentForm.home_location_id || locationId || null,
        current_semester: Number(studentForm.current_semester),
      }).unwrap();
      toast.success("Student admitted");
      closeDrawer(false);
      setStudentForm(emptyStudent);
      navigate(`/app/clients/${created.client_id}`);
    } catch (error) {
      toast.error(error?.data?.detail || "Student could not be admitted");
    }
  };

  const columns = useMemo(() => isCollege ? [
    {
      key: "student", label: "Student", render: (item) => <div className="flex min-w-56 items-center gap-3">
        <EntityAvatar name={item.name} className="h-11 w-11" />
        <div className="min-w-0"><div className="truncate font-semibold">{item.name}</div><div className="mt-0.5 text-xs text-muted-foreground">{[item.admission_number, item.roll_number].filter(Boolean).join(" / ") || "Student record"}</div></div>
      </div>,
    },
    { key: "program", label: "Program & batch", render: (item) => <div><div>{item.program?.name || "Program not assigned"}</div><div className="mt-1 text-xs text-muted-foreground">{item.cohort?.name || "Batch not assigned"}{item.semester ? ` / Semester ${item.semester}` : ""}</div></div> },
    { key: "readiness", label: "Placement readiness", render: (item) => <div className="min-w-32"><StatusBadge status={readinessTone(item.readiness_band)} label={readinessLabel(item.readiness_band)} />{item.readiness?.score != null && <div className="mt-1.5 text-xs text-muted-foreground">{item.readiness.score}% / {item.readiness.coverage_percent}% evidence</div>}</div> },
    { key: "academics", label: "Academics", render: (item) => <div><div className="font-medium">CGPA {item.cgpa ?? "-"}</div><div className={`mt-1 text-xs ${(item.active_backlogs || 0) > 0 ? "font-medium text-warning" : "text-muted-foreground"}`}>{item.active_backlogs == null ? "Backlogs not recorded" : item.active_backlogs ? `${item.active_backlogs} active backlog${item.active_backlogs === 1 ? "" : "s"}` : "No active backlogs"}</div></div> },
    { key: "attendance", label: "Attendance", render: (item) => <span className={item.attendance_percent != null && item.attendance_percent < 75 ? "font-semibold text-warning" : ""}>{item.attendance_percent == null ? "Not recorded" : `${item.attendance_percent}%`}</span> },
    { key: "coding", label: "Coding", render: (item) => item.coding_total == null ? <span className="text-muted-foreground">Not connected</span> : `${item.coding_total} solved` },
    { key: "profile", label: "Resume", render: (item) => <StatusBadge status={["reviewed", "approved"].includes(item.resume_status) ? "completed" : "pending"} label={sentence(item.resume_status || "missing")} /> },
    { key: "open", label: "", render: () => <ArrowRight className="ml-auto text-muted-foreground" /> },
  ] : [
    {
      key: "name", label: singular, render: (item) => <div className="flex min-w-56 items-center gap-3">
        <EntityAvatar name={item.display_name} avatarUrl={item.avatar_url} className="h-11 w-11" />
        <div className="min-w-0"><div className="truncate font-semibold">{item.display_name}</div><div className="mt-0.5 text-xs text-muted-foreground">{item.client_number}</div></div>
      </div>,
    },
    { key: "status", label: "Relationship", render: (item) => <div className="space-y-1.5"><StatusBadge status={item.status} />{item.open_signal_count > 0 && <div className="text-xs font-medium text-warning">{item.open_signal_count} need{item.open_signal_count === 1 ? "" : "s"} attention</div>}</div> },
    { key: "contact", label: "Contact", render: (item) => <div><div>{item.phone || "No phone"}</div><div className="mt-1 text-xs text-muted-foreground">{item.email || item.location_name || "No contact details"}</div></div> },
    { key: "relationship", label: isClinic ? "Next appointment" : "Relationship", render: (item) => <div><div>{item.next_appointment_at ? dateTime(item.next_appointment_at) : "Nothing scheduled"}</div>{!isClinic && <div className="mt-1 text-xs text-muted-foreground">{item.membership_ends_on ? `Membership to ${date(item.membership_ends_on)}` : item.invoice_count ? `${item.invoice_count} purchase${item.invoice_count === 1 ? "" : "s"}` : "New relationship"}</div>}</div> },
    { key: "value", label: "Balance", render: (item) => <div className={item.outstanding_paise > 0 ? "font-semibold text-danger" : "text-muted-foreground"}>{money(item.outstanding_paise)}</div> },
    { key: "open", label: "", render: () => <ArrowRight className="ml-auto text-muted-foreground" /> },
  ], [isClinic, isCollege, singular]);

  const segments = isCollege ? [
    ["all", "All students"], ["ready", "Placement ready"], ["developing", "Developing"],
    ["needs_support", "Needs support"], ["insufficient_evidence", "Evidence review"],
  ] : [
    ["all", `All ${plural.toLowerCase()}`], ["active", "Active"], ["new", "New this month"],
    ["attention", "Needs attention"], ["balance", "Balance due"],
    ...(!isClinic ? [["member", "Members"], ["product_only", "Product-only"]] : []),
    ["inactive", "Inactive"],
  ];
  const placementMetrics = collegeDashboard.data?.metrics;
  const metrics = isCollege ? placementMetrics ? [
    { id: "all", label: "Participating students", value: placementMetrics.participating_students },
    { id: "ready", label: "Placement ready", value: placementMetrics.placement_ready, tone: "positive" },
    { id: "developing", label: "Developing", value: readinessCount(collegeDashboard.data, "Developing") },
    { id: "needs_support", label: "Needs support", value: placementMetrics.needs_support, tone: placementMetrics.needs_support ? "warning" : "neutral" },
    { id: "insufficient_evidence", label: "Evidence review", value: Math.max(0, Number(collegeDashboard.data?.coverage?.total || 0) - Number(collegeDashboard.data?.coverage?.rankable || 0)) },
  ] : [] : data?.summary ? [
    { id: "active", label: `Active ${plural.toLowerCase()}`, value: data.summary.active },
    { id: "new", label: "New in 30 days", value: data.summary.new_30d },
    { id: "attention", label: "Needs attention", value: data.summary.attention, tone: data.summary.attention ? "warning" : "neutral" },
    ...(!isClinic ? [{ id: "member", label: "Active members", value: data.summary.active_members }] : []),
    { id: "balance", label: "Outstanding", value: data.summary.outstanding_paise, format: "money", tone: data.summary.outstanding_paise ? "warning" : "neutral" },
  ] : [];
  const isFilteredEmpty = Boolean(deferredQuery || segment !== "all");
  const canCreate = Boolean(data?.capabilities?.create || (isCollege ? can("college.students.manage") : can("clients.manage")));
  const directoryEmpty = <EmptyState
    variant={isFilteredEmpty ? "filtered" : "page"}
    alignment="left"
    icon={UsersThree}
    title={isFilteredEmpty ? `No ${plural.toLowerCase()} match this view` : `Build your ${plural.toLowerCase()} directory`}
    description={isFilteredEmpty ? "Clear the current search and segment to return to the full directory." : isCollege ? "Admit the first student with a connected program, cohort, academic history, and placement profile." : `Add the first ${singular.toLowerCase()} to connect contact details, visits, billing, and operational history.`}
    primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setQuery(""); setSegment("all"); }}>Clear filters</Button> : canCreate ? <Button onClick={openCreate}><UserPlus className="mr-2" />Add {singular.toLowerCase()}</Button> : null}
    steps={isFilteredEmpty ? [] : isCollege ? [{ title: "Choose program" }, { title: "Assign cohort" }, { title: "Start academic history" }] : [{ title: "Add identity" }, { title: "Record activity" }, { title: "Build history" }]}
  />;

  return <PageShell className="reveal">
    <PageHeader
      eyebrow={isCollege ? "Placement intelligence" : isClinic ? "Patient relationships" : "Relationship workspace"}
      title={plural}
      description={isCollege
        ? "Understand every student through academics, attendance, coding progress, profile evidence, and placement readiness."
        : isClinic
        ? "A permission-aware patient directory connecting appointments, billing, documents, and authorized care context."
        : `Know every ${singular.toLowerCase()} across visits, purchases, appointments, and industry work.`}
      actions={canCreate ? <Button onClick={openCreate}><Plus className="mr-2" />New {singular.toLowerCase()}</Button> : null}
    />

    <MetricStrip metrics={metrics} loading={directory.isLoading && !data} onMetric={(metric) => setSegment(metric.id)} />

    <SegmentControl className="hidden w-full md:inline-flex" items={segments.map(([value, label]) => ({ value, label }))} value={segment} onChange={setSegment} />

    <FilterBar>
      <div className="relative min-w-0 flex-1">
        <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={isCollege ? "Search student, admission number, or roll number" : `Search ${plural.toLowerCase()} by name, phone, email, or number`} className="border-0 bg-surface-subtle pl-10" />
      </div>
      <Select value={segment} onValueChange={setSegment}><SelectTrigger className="w-full md:hidden"><SelectValue /></SelectTrigger><SelectContent>{segments.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select>
      <div className="flex rounded-xl border bg-background p-1" aria-label="Directory view">
        <Button size="icon" variant={view === "table" ? "secondary" : "ghost"} onClick={() => chooseView("table")} aria-label="Table view"><List /></Button>
        <Button size="icon" variant={view === "cards" ? "secondary" : "ghost"} onClick={() => chooseView("cards")} aria-label="Card view"><Cards /></Button>
      </div>
    </FilterBar>

    {directory.error && !data ? <ErrorState title={`${plural} could not be loaded`} description={directory.error?.data?.detail} retry={directory.refetch} /> : view === "table" ? <DataTable
      columns={columns}
      rows={items}
      loading={directory.isLoading && !data}
      onRowClick={openProfile}
      empty={directoryEmpty}
    /> : <ClientCards items={items} loading={directory.isLoading && !data} onOpen={openProfile} singular={singular} empty={directoryEmpty} isCollege={isCollege} />}

    {(items.length > 0 || data?.has_more) && <CursorListFooter
      count={items.length}
      noun={plural.toLowerCase()}
      hasMore={Boolean(data?.has_more)}
      loading={directory.isFetching}
      error={directory.isError}
      onLoadMore={() => paging.loadMore(data?.next_cursor)}
      onRetry={directory.refetch}
    />}

    {!isCollege && <DrawerForm open={drawerOpen} onOpenChange={closeDrawer} title={`Add ${singular.toLowerCase()}`} description={`Start with identity and contact details. You can complete the ${singular.toLowerCase()} workspace after creation.`}>
      <form className="space-y-5" onSubmit={submit}>
        <div className="grid grid-cols-2 gap-4"><Field label="First name"><Input required autoFocus value={form.first_name} onChange={update(setForm, "first_name")} /></Field><Field label="Last name"><Input value={form.last_name} onChange={update(setForm, "last_name")} /></Field></div>
        <div className="grid sm:grid-cols-2 gap-4"><Field label="Phone"><Input inputMode="tel" value={form.phone} onChange={update(setForm, "phone")} /></Field><Field label="Email"><Input type="email" value={form.email} onChange={update(setForm, "email")} /></Field></div>
        <div className="grid sm:grid-cols-2 gap-4"><Field label="Date of birth"><Input type="date" value={form.date_of_birth} onChange={update(setForm, "date_of_birth")} /></Field><Field label="Gender"><Select value={form.gender || "unspecified"} onValueChange={(value) => setForm((current) => ({ ...current, gender: value === "unspecified" ? "" : value }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="unspecified">Prefer not to record</SelectItem><SelectItem value="female">Female</SelectItem><SelectItem value="male">Male</SelectItem><SelectItem value="non_binary">Non-binary</SelectItem><SelectItem value="other">Other</SelectItem></SelectContent></Select></Field></div>
        <Field label="Home location"><Select value={form.home_location_id || locationId || ""} onValueChange={(value) => setForm((current) => ({ ...current, home_location_id: value }))}><SelectTrigger><SelectValue placeholder="Choose location" /></SelectTrigger><SelectContent>{locations.map((location) => <SelectItem key={location.id} value={location.id}>{location.name}</SelectItem>)}</SelectContent></Select></Field>
        <Field label="Address"><Input value={form.address} onChange={update(setForm, "address")} /></Field>
        <Field label="Tags"><Input value={form.tags} onChange={update(setForm, "tags")} placeholder="VIP, morning, referral" /><p className="mt-1 text-xs text-muted-foreground">Separate tags with commas.</p></Field>
        <Field label="Relationship notes"><textarea className="min-h-24 w-full rounded-xl border bg-background p-3 text-sm" value={form.notes} onChange={update(setForm, "notes")} /></Field>
        <Surface className="space-y-3 p-4">
          <Consent checked={form.whatsapp_consent} onChange={(value) => setForm((current) => ({ ...current, whatsapp_consent: value }))} label="They agreed to WhatsApp service updates and reminders" />
          <Consent checked={form.email_consent} onChange={(value) => setForm((current) => ({ ...current, email_consent: value }))} label="They agreed to email service updates" />
          {form.whatsapp_consent && !form.phone && <p className="text-xs font-medium text-danger">A phone number is required for WhatsApp consent.</p>}
        </Surface>
        <Button className="h-11 w-full" disabled={createState.isLoading || (form.whatsapp_consent && !form.phone)}>{createState.isLoading ? "Creating..." : `Create ${singular.toLowerCase()}`}</Button>
      </form>
    </DrawerForm>}

    {isCollege && <DrawerForm open={drawerOpen} onOpenChange={closeDrawer} title="Admit student" description="Create the local placement identity and connect it to the authoritative program and cohort.">
      <StudentAdmissionForm
        form={studentForm}
        setForm={setStudentForm}
        references={references.data}
        locations={locations}
        locationId={locationId}
        loading={admitState.isLoading}
        onSubmit={submitStudent}
      />
    </DrawerForm>}
  </PageShell>;
}

function ClientCards({ items, loading, onOpen, singular, empty, isCollege }) {
  if (loading) return <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[1, 2, 3, 4, 5, 6].map((item) => <Surface key={item} className="h-56 animate-pulse bg-surface-subtle" />)}</div>;
  if (!items.length) return empty;
  return <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map((item) => {
    const name = isCollege ? item.name : item.display_name;
    return <button key={item.id} type="button" onClick={() => onOpen(item)} className="surface-card surface-interactive p-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <div className="flex items-start justify-between gap-3"><EntityAvatar name={name} avatarUrl={item.avatar_url} className="h-14 w-14" />{isCollege ? <StatusBadge status={readinessTone(item.readiness_band)} label={readinessLabel(item.readiness_band)} /> : <div className="flex flex-col items-end gap-2"><StatusBadge status={item.status} />{item.open_signal_count > 0 && <StatusBadge status="warning" label={`${item.open_signal_count} attention`} />}</div>}</div>
      <h2 className="mt-5 truncate font-display text-2xl font-semibold">{name}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{isCollege ? [item.admission_number, item.program?.code].filter(Boolean).join(" / ") : item.phone || item.email || `No ${singular.toLowerCase()} contact recorded`}</p>
      <div className="mt-5 grid grid-cols-2 gap-3 border-t pt-4 text-sm"><div><div className="text-xs text-muted-foreground">{isCollege ? "Academics" : "Next work"}</div><div className="mt-1 truncate">{isCollege ? `CGPA ${item.cgpa ?? "-"}` : item.next_appointment_at ? dateTime(item.next_appointment_at) : "Nothing scheduled"}</div></div><div><div className="text-xs text-muted-foreground">{isCollege ? "Attendance" : "Balance"}</div><div className={`mt-1 truncate ${!isCollege && item.outstanding_paise > 0 ? "font-semibold text-danger" : ""}`}>{isCollege ? item.attendance_percent == null ? "Not recorded" : `${item.attendance_percent}%` : money(item.outstanding_paise)}</div></div></div>
      <div className="mt-5 flex items-center justify-between text-xs text-muted-foreground"><span>{isCollege ? item.cohort?.name || "Batch not assigned" : item.location_name || "No home location"}</span><span className="inline-flex items-center gap-1 font-semibold text-accent">Open profile <ArrowRight /></span></div>
    </button>;
  })}</div>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function Consent({ checked, onChange, label }) { return <label className="flex cursor-pointer items-start gap-3 text-sm"><input className="mt-0.5 h-4 w-4 accent-[hsl(var(--accent))]" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span>{label}</span></label>; }
function StudentAdmissionForm({ form, setForm, references, locations, locationId, loading, onSubmit }) {
  const programs = references?.programs || [];
  const cohorts = (references?.cohorts || []).filter((row) => !form.program_id || row.program_id === form.program_id);
  return <form className="space-y-5" onSubmit={onSubmit}>
    <div className="grid grid-cols-2 gap-4"><Field label="First name"><Input required autoFocus value={form.first_name} onChange={update(setForm, "first_name")} /></Field><Field label="Last name"><Input value={form.last_name} onChange={update(setForm, "last_name")} /></Field></div>
    <div className="grid gap-4 sm:grid-cols-2"><Field label="Admission number"><Input required value={form.admission_number} onChange={update(setForm, "admission_number")} placeholder="CSE-2026-001" /></Field><Field label="Roll number"><Input value={form.roll_number} onChange={update(setForm, "roll_number")} /></Field></div>
    <div className="grid gap-4 sm:grid-cols-2"><Field label="Program"><Select value={form.program_id} onValueChange={(value) => setForm((current) => ({ ...current, program_id: value, cohort_id: "" }))}><SelectTrigger><SelectValue placeholder="Choose program" /></SelectTrigger><SelectContent>{programs.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select></Field><Field label="Cohort"><Select value={form.cohort_id} onValueChange={(value) => setForm((current) => ({ ...current, cohort_id: value }))} disabled={!form.program_id}><SelectTrigger><SelectValue placeholder="Choose cohort" /></SelectTrigger><SelectContent>{cohorts.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select></Field></div>
    <div className="grid gap-4 sm:grid-cols-2"><Field label="Current semester"><Input required type="number" min="1" max="16" value={form.current_semester} onChange={update(setForm, "current_semester")} /></Field><Field label="Admitted on"><Input required type="date" value={form.admitted_on} onChange={update(setForm, "admitted_on")} /></Field></div>
    <div className="grid gap-4 sm:grid-cols-2"><Field label="Email"><Input type="email" value={form.email} onChange={update(setForm, "email")} /></Field><Field label="Phone"><Input inputMode="tel" value={form.phone} onChange={update(setForm, "phone")} /></Field></div>
    <Field label="Campus"><Select value={form.home_location_id || locationId || ""} onValueChange={(value) => setForm((current) => ({ ...current, home_location_id: value }))}><SelectTrigger><SelectValue placeholder="Choose campus" /></SelectTrigger><SelectContent>{locations.map((location) => <SelectItem key={location.id} value={location.id}>{location.name}</SelectItem>)}</SelectContent></Select></Field>
    <Surface className="p-4 text-xs leading-5 text-muted-foreground">Student identity and academic ownership can later move to ERP synchronization. Local placement evidence remains in Edvatiq.</Surface>
    <Button className="h-11 w-full" disabled={loading || !form.program_id || !form.cohort_id}>{loading ? "Admitting..." : "Admit student"}</Button>
  </form>;
}
function update(setter, key) { return (event) => setter((current) => ({ ...current, [key]: event.target.value })); }
function money(paise = 0) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise) / 100); }
function date(value) { return value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "Not set"; }
function dateTime(value) { return value ? new Date(value).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "Not set"; }
function sentence(value = "") { return String(value).replaceAll("_", " ").replace(/^./, (match) => match.toUpperCase()); }
function readinessLabel(value) { return value === "insufficient_evidence" ? "Evidence review" : sentence(value || "insufficient_evidence"); }
function readinessTone(value) { return value === "ready" ? "active" : value === "needs_support" ? "warning" : value === "developing" ? "scheduled" : "pending"; }
function readinessCount(data, label) { return Number((data?.readiness_distribution || []).find((row) => row.label === label)?.value || 0); }
