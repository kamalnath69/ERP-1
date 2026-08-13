import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import {
  ArrowRight, Cards, List, MagnifyingGlass, Plus, UserPlus, UsersThree,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { EntityAvatar } from "@/components/entities/EntityProfile";
import AcademicScopeNavigator from "@/components/college/AcademicScopeNavigator";
import CohortCompareSheet from "@/components/college/CohortCompareSheet";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip,
  PageHeader, PageShell, SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { profileRef } from "@/lib/profileNavigation";
import { QUERY_POLICIES } from "@/store/api/queryPolicies";
import { useCreateClientMutation, useGetClientDirectoryQuery } from "@/store/api/workspaceApi";
import { clientLabel } from "@/app/routeManifest";
import {
  useAdmitCollegeStudentMutation,
  useGetCollegeAcademicHierarchyQuery,
  useGetCollegePlacementDashboardQuery,
  useGetCollegeStudentIntelligenceQuery,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import { applyApiErrors, clientSchema, FORM_OPTIONS, studentAdmissionSchema } from "@/lib/validation";

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
  const graduationYear = isCollege ? searchParams.get("batch") : null;
  const departmentId = isCollege ? searchParams.get("department") : null;
  const cohortId = isCollege ? searchParams.get("section") : null;
  const cohortIds = isCollege ? [...new Set(searchParams.getAll("cohort_ids"))] : [];
  const placementStatus = isCollege ? searchParams.get("placement") || "all" : "all";
  const studentSort = isCollege ? searchParams.get("sort") || "name" : "name";
  const [view, setView] = useState(() => localStorage.getItem("edvatiq.clients.view") || "table");
  const [drawerOpen, setDrawerOpen] = useState(() => searchParams.get("new") === "1");
  const [createClient, createState] = useCreateClientMutation();
  const [admitStudent, admitState] = useAdmitCollegeStudentMutation();

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (deferredQuery) next.set("q", deferredQuery); else next.delete("q");
    if (next.toString() !== searchParams.toString()) setSearchParams(next, { replace: true });
  }, [deferredQuery, searchParams, setSearchParams]);

  const pageKey = JSON.stringify({
    industry, locationId, q: deferredQuery, segment,
    graduationYear, departmentId, cohortId, cohortIds, placementStatus, studentSort,
  });
  const paging = useCursorPagination(pageKey);

  const clientDirectory = useGetClientDirectoryQuery(
    { locationId, q: deferredQuery, segment, limit: 25, cursor: paging.cursor },
    { ...QUERY_POLICIES.operational, skip: isCollege },
  );
  const collegeDirectory = useGetCollegeStudentIntelligenceQuery({
    q: deferredQuery || undefined,
    graduation_year: graduationYear || undefined,
    department_id: departmentId || undefined,
    cohort_id: cohortId || undefined,
    cohort_ids: cohortIds,
    readiness_band: segment === "all" ? undefined : segment,
    placement_status: placementStatus === "all" ? undefined : placementStatus,
    sort: studentSort,
    cursor: paging.cursor || undefined,
    limit: 25,
  }, { skip: !isCollege });
  const academicHierarchy = useGetCollegeAcademicHierarchyQuery(undefined, { skip: !isCollege });
  const collegeDashboard = useGetCollegePlacementDashboardQuery({
    graduation_year: graduationYear || undefined,
    department_id: departmentId || undefined,
    cohort_id: cohortId || undefined,
    cohort_ids: cohortIds,
  }, { skip: !isCollege });
  const directory = isCollege ? collegeDirectory : clientDirectory;
  const data = directory.data;
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(data); }, [acceptPage, data]);
  const items = paging.items;
  const plural = clientLabel(industry);
  const singular = clientLabel(industry, false);
  const isClinic = industry === "clinic";
  const openCreate = () => {
    if (isCollege && academicHierarchy.isLoading && !academicHierarchy.data) {
      toast.info("Academic structure is still loading");
      return;
    }
    if (isCollege && !hasAcademicAdmissionStructure(academicHierarchy.data)) {
      toast.info("Create a department, program, and batch before admitting students");
      navigate("/app/college?section=structure");
      return;
    }
    setDrawerOpen(true);
    const next = new URLSearchParams(searchParams);
    next.set("new", "1");
    setSearchParams(next, { replace: true });
  };

  const closeDrawer = (open, force = false) => {
    if (!open && !force && (createState.isLoading || admitState.isLoading)) return;
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
  const setAcademicScope = ({ graduationYear: year, departmentId: department, cohortId: cohort }) => {
    const next = new URLSearchParams(searchParams);
    next.delete("cohort_ids");
    if (year) next.set("batch", String(year)); else next.delete("batch");
    if (department) next.set("department", department); else next.delete("department");
    if (cohort) next.set("section", cohort); else next.delete("section");
    setSearchParams(next, { replace: true });
  };
  const setComparedCohorts = (ids) => {
    const next = new URLSearchParams(searchParams);
    next.delete("batch");
    next.delete("department");
    next.delete("section");
    next.delete("cohort_ids");
    ids.forEach((id) => next.append("cohort_ids", id));
    setSearchParams(next, { replace: true });
  };
  const setCollegeOption = (key, value, defaultValue = "all") => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === defaultValue) next.delete(key); else next.set(key, value);
    setSearchParams(next, { replace: true });
  };
  const clearFilters = () => {
    setQuery("");
    const next = new URLSearchParams(searchParams);
    ["q", "segment", "batch", "department", "section", "cohort_ids", "placement", "sort"].forEach((key) => next.delete(key));
    setSearchParams(next, { replace: true });
  };
  const chooseView = (value) => {
    setView(value);
    localStorage.setItem("edvatiq.clients.view", value);
  };
  const openProfile = (item) => navigate(`/app/clients/${item.client_id || item.id}`, {
    state: { profileFrom: `${window.location.pathname}${window.location.search}` },
  });

  const columns = useMemo(() => isCollege ? [
    {
      key: "student", label: "Student", render: (item) => <div className="flex min-w-56 items-center gap-3">
        <EntityAvatar name={item.name} className="h-11 w-11" />
        <div className="min-w-0"><div className="truncate font-semibold">{item.name}</div><div className="mt-0.5 text-xs text-muted-foreground">{[item.admission_number, item.roll_number].filter(Boolean).join(" / ") || "Student record"}</div></div>
      </div>,
    },
    { key: "program", label: "Academic group", render: (item) => <div><div>{item.department?.code || "Department"} / {item.program?.code || "Program"}</div><div className="mt-1 text-xs text-muted-foreground">Class of {item.graduation_year || "-"} / Section {item.section || "General"}{item.semester ? ` / Sem ${item.semester}` : ""}</div></div> },
    { key: "readiness", label: "Readiness & outcome", render: (item) => <div className="min-w-36 space-y-1.5"><StatusBadge status={readinessTone(item.readiness_band)} label={readinessLabel(item.readiness_band)} /><div><StatusBadge status={placementTone(item.placement_status)} label={sentence(item.placement_status || "seeking")} /></div>{item.readiness?.score != null && <div className="text-xs text-muted-foreground">{item.readiness.score}% / {item.readiness.coverage_percent}% evidence</div>}</div> },
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
  const isFilteredEmpty = Boolean(
    deferredQuery || segment !== "all" || graduationYear || departmentId || cohortId || cohortIds.length
    || placementStatus !== "all" || studentSort !== "name",
  );
  const canCreate = Boolean(data?.capabilities?.create || (isCollege ? can("college.students.manage") : can("clients.manage")));
  const directoryEmpty = <EmptyState
    variant={isFilteredEmpty ? "filtered" : "page"}
    alignment="left"
    icon={UsersThree}
    title={isFilteredEmpty ? `No ${plural.toLowerCase()} match this view` : `Build your ${plural.toLowerCase()} directory`}
    description={isFilteredEmpty ? "Clear the current search and segment to return to the full directory." : isCollege ? "Admit the first student with a connected program, cohort, academic history, and placement profile." : `Add the first ${singular.toLowerCase()} to connect contact details, visits, billing, and operational history.`}
    primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={clearFilters}>Clear filters</Button> : canCreate ? <Button onClick={openCreate}><UserPlus className="mr-2" />Add {singular.toLowerCase()}</Button> : null}
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

    {isCollege && <AcademicScopeNavigator
      data={academicHierarchy.data}
      loading={academicHierarchy.isLoading}
      error={academicHierarchy.isError}
      retry={academicHierarchy.refetch}
      value={{ graduationYear, departmentId, cohortId }}
      onChange={setAcademicScope}
    />}

    {isCollege && <CohortCompareSheet data={academicHierarchy.data} selectedIds={cohortIds} onApply={setComparedCohorts} />}

    <MetricStrip metrics={metrics} loading={directory.isLoading && !data} onMetric={(metric) => setSegment(metric.id)} />

    <SegmentControl className="hidden w-full md:inline-flex" items={segments.map(([value, label]) => ({ value, label }))} value={segment} onChange={setSegment} />

    <FilterBar className={isCollege ? "sm:flex-wrap xl:flex-nowrap" : undefined}>
      <div className="relative min-w-0 flex-1">
        <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={isCollege ? "Search student, admission number, or roll number" : `Search ${plural.toLowerCase()} by name, phone, email, or number`} className="border-0 bg-surface-subtle pl-10" />
      </div>
      <Select value={segment} onValueChange={setSegment}><SelectTrigger className="w-full md:hidden"><SelectValue /></SelectTrigger><SelectContent>{segments.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select>
      {isCollege && <Select value={placementStatus} onValueChange={(value) => setCollegeOption("placement", value)}><SelectTrigger className="w-full md:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All outcomes</SelectItem><SelectItem value="unplaced">Not placed</SelectItem><SelectItem value="placed">Placed</SelectItem><SelectItem value="seeking">Seeking placement</SelectItem><SelectItem value="not_participating">Not participating</SelectItem></SelectContent></Select>}
      {isCollege && <Select value={studentSort} onValueChange={(value) => setCollegeOption("sort", value, "name")}><SelectTrigger className="w-full md:w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="name">Sort by name</SelectItem><SelectItem value="academics_desc">Best academics first</SelectItem></SelectContent></Select>}
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
      <ClientCreateForm createClient={createClient} loading={createState.isLoading} locations={locations} locationId={locationId} singular={singular} onCreated={(created) => { toast.success(`${singular} created`); closeDrawer(false, true); navigate(`/app/clients/${created.id}`); }} />
    </DrawerForm>}

    {isCollege && <DrawerForm open={drawerOpen} onOpenChange={closeDrawer} title="Admit student" description="Create the local placement identity and connect it to the authoritative program and cohort.">
      <StudentAdmissionForm
        hierarchy={academicHierarchy.data}
        locations={locations}
        locationId={locationId}
        canViewContact={can("college.students.contact.view")}
        loading={admitState.isLoading}
        admitStudent={admitStudent}
        onCreated={(created) => { toast.success("Student admitted"); closeDrawer(false, true); navigate(`/app/clients/${created.client_id}`); }}
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
      <div className="flex items-start justify-between gap-3"><EntityAvatar name={name} avatarUrl={item.avatar_url} className="h-14 w-14" />{isCollege ? <div className="flex flex-col items-end gap-2"><StatusBadge status={readinessTone(item.readiness_band)} label={readinessLabel(item.readiness_band)} /><StatusBadge status={placementTone(item.placement_status)} label={sentence(item.placement_status || "seeking")} /></div> : <div className="flex flex-col items-end gap-2"><StatusBadge status={item.status} />{item.open_signal_count > 0 && <StatusBadge status="warning" label={`${item.open_signal_count} attention`} />}</div>}</div>
      <h2 className="mt-5 truncate font-display text-2xl font-semibold">{name}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{isCollege ? [item.admission_number, item.department?.code, item.program?.code].filter(Boolean).join(" / ") : item.phone || item.email || `No ${singular.toLowerCase()} contact recorded`}</p>
      <div className="mt-5 grid grid-cols-2 gap-3 border-t pt-4 text-sm"><div><div className="text-xs text-muted-foreground">{isCollege ? "Academics" : "Next work"}</div><div className="mt-1 truncate">{isCollege ? `CGPA ${item.cgpa ?? "-"}` : item.next_appointment_at ? dateTime(item.next_appointment_at) : "Nothing scheduled"}</div></div><div><div className="text-xs text-muted-foreground">{isCollege ? "Attendance" : "Balance"}</div><div className={`mt-1 truncate ${!isCollege && item.outstanding_paise > 0 ? "font-semibold text-danger" : ""}`}>{isCollege ? item.attendance_percent == null ? "Not recorded" : `${item.attendance_percent}%` : money(item.outstanding_paise)}</div></div></div>
      <div className="mt-5 flex items-center justify-between gap-3 text-xs text-muted-foreground"><span className="truncate">{isCollege ? `Class of ${item.graduation_year || "-"} / ${item.department?.code || "Department"} ${item.section || "General"}` : item.location_name || "No home location"}</span><span className="inline-flex shrink-0 items-center gap-1 font-semibold text-accent">Open profile <ArrowRight /></span></div>
    </button>;
  })}</div>;
}

function ClientCreateForm({ createClient, loading, locations, locationId, singular, onCreated }) {
  const form = useForm({ resolver: zodResolver(clientSchema), defaultValues: { ...emptyClient, home_location_id: locationId || "" }, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, setValue, watch } = form;
  const whatsappConsent = watch("whatsapp_consent"); const emailConsent = watch("email_consent");
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      const created = await createClient({
        ...values, last_name: values.last_name || "", home_location_id: values.home_location_id || locationId || null,
      }).unwrap();
      reset({ ...emptyClient, home_location_id: locationId || "" });
      onCreated(created);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: `Could not create ${singular.toLowerCase()}` });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
    <div className="grid grid-cols-2 gap-4"><ValidatedField control={control} name="first_name" label="First name"><Input autoFocus autoComplete="given-name" /></ValidatedField><ValidatedField control={control} name="last_name" label="Last name"><Input autoComplete="family-name" /></ValidatedField></div>
    <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={control} name="phone" label="Phone"><Input inputMode="tel" autoComplete="tel" /></ValidatedField><ValidatedField control={control} name="email" label="Email"><Input type="email" autoComplete="email" /></ValidatedField></div>
    <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={control} name="date_of_birth" label="Date of birth"><Input type="date" /></ValidatedField><SelectField control={control} name="gender" label="Gender" placeholder="Prefer not to record" options={[["female", "Female"], ["male", "Male"], ["non_binary", "Non-binary"], ["other", "Other"]]} /></div>
    <SelectField control={control} name="home_location_id" label="Home location" placeholder="Choose location" options={locations.map((location) => [location.id, location.name])} />
    <ValidatedField control={control} name="address" label="Address"><Input autoComplete="street-address" /></ValidatedField>
    <ValidatedField control={control} name="tags" label="Tags" description="Separate tags with commas."><Input placeholder="VIP, morning, referral" /></ValidatedField>
    <ValidatedField control={control} name="notes" label="Relationship notes"><Textarea rows={4} /></ValidatedField>
    <Surface className="space-y-3 p-4"><Consent checked={whatsappConsent} onChange={(value) => setValue("whatsapp_consent", value, { shouldDirty: true, shouldValidate: true })} label="They agreed to WhatsApp service updates and reminders" /><Consent checked={emailConsent} onChange={(value) => setValue("email_consent", value, { shouldDirty: true })} label="They agreed to email service updates" /></Surface>
    <FormRootError error={formState.errors.root?.server} />
    <Button type="submit" className="h-11 w-full" loading={formState.isSubmitting || loading} loadingText="Creating..." disabled={!formState.isValid}>Create {singular.toLowerCase()}</Button>
  </form></Form>;
}

function Consent({ checked, onChange, label }) { return <label className="flex cursor-pointer items-start gap-3 text-sm"><input className="mt-0.5 h-4 w-4 accent-[hsl(var(--accent))]" type="checkbox" checked={Boolean(checked)} onChange={(event) => onChange(event.target.checked)} /><span>{label}</span></label>; }

function StudentAdmissionForm({ hierarchy, locations, locationId, canViewContact, loading, admitStudent, onCreated }) {
  const form = useForm({ resolver: zodResolver(studentAdmissionSchema), defaultValues: { ...emptyStudent, home_location_id: locationId || "" }, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, setValue, watch } = form;
  const programId = watch("program_id");
  const { programs, cohorts: allCohorts } = academicAdmissionOptions(hierarchy);
  const cohorts = allCohorts.filter((row) => !programId || row.program_id === programId);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      const created = await admitStudent({ ...values, last_name: values.last_name || "", home_location_id: values.home_location_id || locationId || null }).unwrap();
      reset({ ...emptyStudent, home_location_id: locationId || "" });
      onCreated(created);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Student could not be admitted" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
    <div className="grid grid-cols-2 gap-4"><ValidatedField control={control} name="first_name" label="First name"><Input autoFocus autoComplete="given-name" /></ValidatedField><ValidatedField control={control} name="last_name" label="Last name"><Input autoComplete="family-name" /></ValidatedField></div>
    <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={control} name="admission_number" label="Admission number"><Input placeholder="Official admission number" /></ValidatedField><ValidatedField control={control} name="roll_number" label="Roll number"><Input /></ValidatedField></div>
    <div className="grid gap-4 sm:grid-cols-2"><FormField control={control} name="program_id" render={({ field }) => <FormItem><FormLabel>Program</FormLabel><Select value={field.value} onValueChange={(value) => { field.onChange(value); setValue("cohort_id", "", { shouldValidate: true }); }}><FormControl><SelectTrigger><SelectValue placeholder="Choose program" /></SelectTrigger></FormControl><SelectContent>{programs.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} /><SelectField control={control} name="cohort_id" label="Cohort" placeholder="Choose cohort" options={cohorts.map((row) => [row.id, row.name])} disabled={!programId} /></div>
    <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={control} name="current_semester" label="Current semester"><Input inputMode="numeric" /></ValidatedField><ValidatedField control={control} name="admitted_on" label="Admitted on"><Input type="date" /></ValidatedField></div>
    {canViewContact && <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={control} name="email" label="Email"><Input type="email" autoComplete="email" /></ValidatedField><ValidatedField control={control} name="phone" label="Phone"><Input inputMode="tel" autoComplete="tel" /></ValidatedField></div>}
    <SelectField control={control} name="home_location_id" label="Campus" placeholder="Choose campus" options={locations.map((location) => [location.id, location.name])} />
    <Surface className="p-4 text-xs leading-5 text-muted-foreground">Student identity and academic ownership can later move to ERP synchronization. Local placement evidence remains in Edvatiq.</Surface>
    <FormRootError error={formState.errors.root?.server} />
    <Button type="submit" className="h-11 w-full" loading={formState.isSubmitting || loading} loadingText="Admitting..." disabled={!formState.isValid}>Admit student</Button>
  </form></Form>;
}

function academicAdmissionOptions(hierarchy) {
  const programs = new Map();
  const cohorts = [];
  (hierarchy?.items || []).forEach((batch) => batch.departments.forEach((department) => department.programs.forEach((program) => {
    programs.set(program.id, { ...program, department_code: department.code });
    program.sections.forEach((section) => cohorts.push({
      ...section,
      program_id: program.id,
      name: `${program.code} / ${section.section || "GENERAL"} / ${batch.graduation_year}`,
    }));
  })));
  return { programs: [...programs.values()], cohorts };
}

function hasAcademicAdmissionStructure(hierarchy) {
  const options = academicAdmissionOptions(hierarchy);
  return options.programs.length > 0 && options.cohorts.length > 0;
}

function ValidatedField({ control, name, label, description, children }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl>{description && <FormDescription>{description}</FormDescription>}<FormMessage /></FormItem>} />; }
function SelectField({ control, name, label, placeholder, options, disabled }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><Select value={field.value || ""} onValueChange={field.onChange} disabled={disabled}><FormControl><SelectTrigger><SelectValue placeholder={placeholder} /></SelectTrigger></FormControl><SelectContent>{options.map(([value, text]) => <SelectItem key={value} value={value}>{text}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />; }
function money(paise = 0) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise) / 100); }
function date(value) { return value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "Not set"; }
function dateTime(value) { return value ? new Date(value).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "Not set"; }
function sentence(value = "") { return String(value).replaceAll("_", " ").replace(/^./, (match) => match.toUpperCase()); }
function readinessLabel(value) { return value === "insufficient_evidence" ? "Evidence review" : sentence(value || "insufficient_evidence"); }
function readinessTone(value) { return value === "ready" ? "active" : value === "needs_support" ? "warning" : value === "developing" ? "scheduled" : "pending"; }
function placementTone(value) { return ["placed", "joined"].includes(value) ? "completed" : value === "not_participating" ? "inactive" : "pending"; }
function readinessCount(data, label) { return Number((data?.readiness_distribution || []).find((row) => row.label === label)?.value || 0); }
