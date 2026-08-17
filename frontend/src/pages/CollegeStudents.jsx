import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, ArrowRight, Buildings, GraduationCap, MagnifyingGlass,
  Plus, Scales, SlidersHorizontal, UsersThree, WarningCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import CohortCompareSheet from "@/components/college/CohortCompareSheet";
import { useRegisterAIPageContext } from "@/components/ai/AIConversationProvider";
import { EntityAvatar } from "@/components/entities/EntityProfile";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, FilterBar, MetricStrip,
  PageHeader, PageShell, ResponsiveCardGrid, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  useAdmitCollegeStudentMutation, useGetCollegeStudentHierarchyQuery,
  useGetCollegeStudentsPageQuery, useGetCollegeStudentSummaryQuery,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import { applyApiErrors, FORM_OPTIONS, studentAdmissionSchema } from "@/lib/validation";

const directoryCache = new Map();
const READINESS_VALUES = new Set(["ready", "developing", "needs_support", "insufficient_evidence"]);
const PLACEMENT_VALUES = new Set(["placed", "unplaced", "seeking", "not_participating"]);
const EMPTY_STUDENT = {
  first_name: "", last_name: "", email: "", phone: "", admission_number: "",
  roll_number: "", program_id: "", cohort_id: "", current_semester: "1",
  admitted_on: new Date().toISOString().slice(0, 10), home_location_id: "",
};

export default function CollegeStudents() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const { locations, locationId } = useBusiness();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const urlQuery = searchParams.get("q") || "";
  const [query, setQuery] = useState(urlQuery);
  const deferredQuery = useDeferredValue(query.trim());
  const requestedBatch = searchParams.get("batch");
  const graduationYear = validYear(requestedBatch);
  const cohortIds = [...new Set(searchParams.getAll("cohort_ids"))];
  const explicitAll = searchParams.get("scope") === "all";
  const mode = requestedBatch ? "batch" : cohortIds.length ? "compare" : explicitAll ? "all" : "hub";
  const departmentId = searchParams.get("department") || "";
  const programId = searchParams.get("program") || "";
  const cohortId = searchParams.get("section") || "";
  const readiness = READINESS_VALUES.has(searchParams.get("readiness")) ? searchParams.get("readiness") : "all";
  const placement = PLACEMENT_VALUES.has(searchParams.get("placement")) ? searchParams.get("placement") : "all";
  const sort = searchParams.get("sort") === "academics_desc" ? "academics_desc" : "name";
  const initialCursor = searchParams.get("cursor") || null;
  const drawerOpen = searchParams.get("new") === "1";

  const hierarchyQuery = useGetCollegeStudentHierarchyQuery();
  const hierarchy = hierarchyQuery.data;
  const selectedBatch = graduationYear
    ? (hierarchy?.items || []).find((row) => Number(row.graduation_year) === graduationYear)
    : null;
  useRegisterAIPageContext(collegeStudentsAIContext({
    hierarchy,
    mode,
    selectedBatch,
    cohortIds,
    departmentId,
    programId,
    cohortId,
  }));
  const invalidBatch = Boolean(requestedBatch && hierarchy && !hierarchyQuery.isFetching && (!graduationYear || !selectedBatch));
  const batchPending = mode === "batch" && (!hierarchy || !selectedBatch);
  const structuralFilters = {
    graduation_year: graduationYear || undefined,
    department_id: departmentId || undefined,
    program_id: programId || undefined,
    cohort_id: cohortId || undefined,
    cohort_ids: cohortIds,
  };
  const summaryQuery = useGetCollegeStudentSummaryQuery(structuralFilters, {
    skip: invalidBatch || batchPending || hierarchyQuery.isError,
  });
  const pageKey = JSON.stringify({
    mode, graduationYear, cohortIds, departmentId, programId, cohortId,
    q: deferredQuery, readiness, placement, sort,
  });
  const cachedPage = directoryCache.get(pageKey);
  const paging = useCursorPagination(pageKey, cachedPage || {
    key: pageKey, cursor: initialCursor, items: [], scrollTop: 0,
  });
  const directoryQuery = useGetCollegeStudentsPageQuery({
    ...structuralFilters,
    q: deferredQuery || undefined,
    readiness_band: readiness === "all" ? undefined : readiness,
    placement_status: placement === "all" ? undefined : placement,
    sort,
    cursor: paging.cursor || undefined,
    limit: 25,
  }, { skip: mode === "hub" || invalidBatch || batchPending || hierarchyQuery.isError });
  const summaryData = currentQueryData(summaryQuery);
  const directoryData = currentQueryData(directoryQuery);
  const capabilities = summaryData?.capabilities || directoryData?.capabilities || {};
  const { accept: acceptPage } = paging;

  useEffect(() => { acceptPage(directoryData); }, [acceptPage, directoryData]);
  useEffect(() => {
    if (urlQuery !== query) setQuery(urlQuery);
    // URL changes from browser navigation are authoritative.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlQuery]);
  useEffect(() => {
    if (mode === "hub" || deferredQuery === urlQuery) return;
    updateParams(setSearchParams, searchParams, (next) => {
      setOrDelete(next, "q", deferredQuery);
      next.delete("cursor");
    }, true);
  }, [deferredQuery, mode, searchParams, setSearchParams, urlQuery]);

  useEffect(() => {
    if (!hierarchy || mode !== "batch" || !selectedBatch) return;
    const departments = selectedBatch.departments || [];
    const department = departments.find((row) => row.id === departmentId);
    const programs = (department ? department.programs : departments.flatMap((row) => row.programs || []));
    const program = programs.find((row) => row.id === programId);
    const sections = (program ? program.sections : programs.flatMap((row) => row.sections || []));
    const validDepartment = !departmentId || Boolean(department);
    const validProgram = !programId || Boolean(program);
    const validCohort = !cohortId || sections.some((row) => row.id === cohortId);
    if (validDepartment && validProgram && validCohort) return;
    updateParams(setSearchParams, searchParams, (next) => {
      if (!validDepartment) next.delete("department");
      if (!validDepartment || !validProgram) next.delete("program");
      next.delete("section");
      next.delete("cursor");
    }, true);
  }, [cohortId, departmentId, hierarchy, mode, programId, searchParams, selectedBatch, setSearchParams]);

  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current || !cachedPage?.scrollTop || !paging.items.length) return;
    restoredRef.current = true;
    requestAnimationFrame(() => {
      const scroller = document.getElementById("main-content");
      if (scroller) scroller.scrollTop = cachedPage.scrollTop;
    });
  }, [cachedPage, paging.items.length]);

  const navigateHub = () => {
    setQuery("");
    setSearchParams(new URLSearchParams(), { replace: false });
  };
  const openAllStudents = (metric = null) => {
    const next = new URLSearchParams();
    next.set("scope", "all");
    applyMetric(next, metric);
    setSearchParams(next, { replace: false });
  };
  const openBatch = (batch, metric = null) => {
    const next = new URLSearchParams();
    next.set("batch", String(batch.graduation_year));
    applyMetric(next, metric);
    setSearchParams(next, { replace: false });
  };
  const applyComparedCohorts = (ids) => {
    const next = new URLSearchParams();
    ids.forEach((id) => next.append("cohort_ids", id));
    setSearchParams(next, { replace: false });
  };
  const changeScope = (key, value) => updateParams(setSearchParams, searchParams, (next) => {
    setOrDelete(next, key, value === "all" ? "" : value);
    if (key === "department") {
      next.delete("program");
      next.delete("section");
    }
    if (key === "program") next.delete("section");
    next.delete("cursor");
  }, true);
  const clearDirectoryFilters = () => {
    setQuery("");
    updateParams(setSearchParams, searchParams, (next) => {
      ["q", "readiness", "placement", "sort", "cursor", "department", "program", "section"].forEach((key) => next.delete(key));
    }, true);
  };
  const setMetric = (metric) => updateParams(setSearchParams, searchParams, (next) => {
    applyMetric(next, metric.id);
    next.delete("cursor");
  }, true);
  const openCreate = () => {
    if (hierarchyQuery.isLoading && !hierarchy) return toast.info("Academic structure is still loading");
    if (!(hierarchy?.items || []).length) {
      toast.info("Create a department, program, and batch before admitting students");
      navigate("/app/college?section=structure");
      return;
    }
    updateParams(setSearchParams, searchParams, (next) => next.set("new", "1"), true);
  };
  const closeCreate = (open) => {
    if (open) return;
    updateParams(setSearchParams, searchParams, (next) => next.delete("new"), true);
  };
  const openProfile = (item) => {
    const scroller = document.getElementById("main-content");
    directoryCache.set(pageKey, {
      ...paging.snapshot,
      key: pageKey,
      items: paging.items,
      scrollTop: scroller?.scrollTop || 0,
    });
    while (directoryCache.size > 12) directoryCache.delete(directoryCache.keys().next().value);
    navigate(`/app/clients/${item.client_id}`, {
      state: { profileFrom: `${window.location.pathname}${window.location.search}` },
    });
  };
  const loadMore = () => {
    const cursor = directoryData?.next_cursor;
    if (!cursor) return;
    paging.loadMore(cursor);
    updateParams(setSearchParams, searchParams, (next) => next.set("cursor", cursor), true);
  };

  const metrics = summaryMetrics(summaryData);
  const columns = useMemo(() => studentColumns(capabilities), [capabilities]);
  const isFiltered = Boolean(
    deferredQuery || departmentId || programId || cohortId
    || readiness !== "all" || placement !== "all" || sort !== "name"
  );

  if (hierarchyQuery.isLoading && !hierarchy) return <StudentHubSkeleton />;
  if (hierarchyQuery.isError && !hierarchy) return <PageShell className="reveal"><PageHeader eyebrow="Student intelligence" title="Students" description="Navigate graduation batches and authorized academic groups." /><ErrorStateRow title="Student batches could not be loaded" error={hierarchyQuery.error} retry={hierarchyQuery.refetch} /></PageShell>;
  if (invalidBatch) return <PageShell className="reveal"><PageHeader eyebrow="Students" title={graduationYear ? `Class of ${graduationYear}` : "Batch unavailable"} description="This graduation batch is unavailable or outside your current access." actions={<Button variant="outline" onClick={navigateHub}><ArrowLeft className="mr-2" />Back to batches</Button>} /><EmptyState variant="section" alignment="left" icon={GraduationCap} title="Batch not found" description="Return to the student hub to choose a reachable graduation batch." primaryAction={<Button onClick={navigateHub}>View batches</Button>} /></PageShell>;

  if (mode === "hub") return <PageShell className="reveal">
    <PageHeader
      eyebrow="Student intelligence"
      title="Students"
      description="Start with a graduation batch, then narrow to the academic group responsible for the next action."
      actions={(hierarchy?.items || []).length ? <HubActions hierarchy={hierarchy} canCreate={can("college.students.manage")} onAll={openAllStudents} onCompare={applyComparedCohorts} onCreate={openCreate} /> : null}
    />
    {summaryQuery.isError ? <ErrorStateRow title="Student metrics are unavailable" error={summaryQuery.error} retry={summaryQuery.refetch} /> : <MetricStrip metrics={metrics} loading={summaryQuery.isFetching && !summaryData} onMetric={(metric) => openAllStudents(metric.id)} />}
    {(hierarchy?.items || []).length ? <section aria-labelledby="graduation-batches-heading" className="space-y-3">
      <div className="flex items-end justify-between gap-4"><div><div className="overline">Graduation batches</div><h2 id="graduation-batches-heading" className="mt-1 font-display text-2xl font-semibold">Choose a batch</h2></div><span className="hidden text-xs text-muted-foreground sm:block">{hierarchy.summary?.batch_count || hierarchy.items.length} reachable batches</span></div>
      <ResponsiveCardGrid minWidth="18rem">{hierarchy.items.map((batch) => <BatchCard key={batch.graduation_year} batch={batch} onOpen={() => openBatch(batch)} />)}</ResponsiveCardGrid>
    </section> : <EmptyState
      variant="page" alignment="left" icon={Buildings} title="Set up the academic structure first"
      description="Create a department, program, and graduation batch before admitting students."
      primaryAction={can("college.academics.manage") ? <Button onClick={() => navigate("/app/college?section=structure")}><Plus className="mr-2" />Open academic structure</Button> : null}
      steps={[{ title: "Create department" }, { title: "Add program" }, { title: "Create batch and sections" }]}
    />}
    <AdmissionDrawer open={drawerOpen} onOpenChange={closeCreate} hierarchy={hierarchy} selectedBatch={null} locations={locations} locationId={locationId} canViewContact={can("college.students.contact.view")} onCreated={(created) => navigate(`/app/clients/${created.client_id}`)} />
  </PageShell>;

  const title = mode === "batch" ? selectedBatch.label : mode === "compare" ? "Cohort comparison" : "All students";
  const subtitle = mode === "batch"
    ? `${selectedBatch.department_count} departments and ${selectedBatch.section_count} sections in this graduation batch.`
    : mode === "compare" ? `${cohortIds.length} selected cohorts across the academic structure.` : "Every student reachable through your current access policy.";

  return <PageShell className="reveal">
    <div className="flex items-center gap-2 text-xs text-muted-foreground"><button type="button" onClick={navigateHub} className="font-semibold transition-colors hover:text-foreground">Students</button><ArrowRight size={12} /><span className="truncate text-foreground">{title}</span></div>
    <PageHeader
      eyebrow={mode === "batch" ? `Graduation batch ${graduationYear}` : "Student directory"}
      title={title}
      description={subtitle}
      actions={<div className="flex flex-wrap gap-2">{mode === "compare" && <CohortCompareSheet data={hierarchy} selectedIds={cohortIds} onApply={applyComparedCohorts} trigger={<Button variant="outline"><Scales className="mr-2" />Change cohorts</Button>} />}{can("college.students.manage") && <Button onClick={openCreate}><Plus className="mr-2" />New student</Button>}</div>}
    />
    {summaryQuery.isError ? <ErrorStateRow title="Scoped metrics are unavailable" error={summaryQuery.error} retry={summaryQuery.refetch} /> : <MetricStrip metrics={metrics} loading={summaryQuery.isFetching && !summaryData} onMetric={setMetric} />}
    {mode === "batch" && <ScopeBar batch={selectedBatch} values={{ departmentId, programId, cohortId }} onChange={changeScope} />}
    {mode === "compare" && <SelectedCohorts data={hierarchy} selectedIds={cohortIds} onChange={applyComparedCohorts} />}
    <DirectoryFilters
      query={query} setQuery={setQuery} readiness={readiness} placement={placement} sort={sort}
      capabilities={capabilities} onChange={changeScope} onMobileFilters={() => setFiltersOpen(true)}
    />
    <StudentFiltersSheet
      open={filtersOpen} onOpenChange={setFiltersOpen}
      batch={mode === "batch" ? selectedBatch : null}
      scopeValues={{ departmentId, programId, cohortId }}
      readiness={readiness} placement={placement} sort={sort}
      capabilities={capabilities} onChange={changeScope}
    />
    {directoryQuery.isError && !paging.items.length ? <ErrorStateRow title="Student directory could not be loaded" error={directoryQuery.error} retry={directoryQuery.refetch} /> : <Surface className="overflow-hidden" aria-busy={directoryQuery.isFetching}>
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3.5 sm:px-5"><div><h2 className="font-display text-lg font-semibold">Student directory</h2><p className="mt-0.5 text-xs text-muted-foreground">{directoryData?.total == null ? "Authorized student records" : `${Number(directoryData.total).toLocaleString("en-IN")} students in this view`}</p></div>{directoryQuery.isFetching && paging.items.length > 0 && <span className="text-xs font-medium text-muted-foreground">Refreshing...</span>}</div>
      <DataTable
        className="rounded-none border-0 shadow-none" columns={columns} rows={paging.items}
        loading={directoryQuery.isFetching && !paging.items.length} onRowClick={openProfile}
        mobileColumns={columns.length}
        empty={<EmptyState
          variant={isFiltered ? "filtered" : "section"} alignment="left" icon={UsersThree}
          title={isFiltered ? "No students match this view" : mode === "batch" ? "No students in this batch yet" : "No students in this scope"}
          description={isFiltered ? "Clear the filters while keeping the current batch or comparison." : "Admit a student into an authorized program and cohort to begin this directory."}
          primaryAction={isFiltered ? <Button variant="outline" onClick={clearDirectoryFilters}>Clear filters</Button> : capabilities.create ? <Button onClick={openCreate}>Admit student</Button> : null}
        />}
      />
      {(paging.items.length > 0 || directoryData?.has_more) && <CursorListFooter
        count={paging.items.length} noun="students" hasMore={Boolean(directoryData?.has_more)}
        loading={directoryQuery.isFetching} error={directoryQuery.isError}
        onLoadMore={loadMore} onRetry={directoryQuery.refetch}
      />}
    </Surface>}
    <AdmissionDrawer open={drawerOpen} onOpenChange={closeCreate} hierarchy={hierarchy} selectedBatch={mode === "batch" ? selectedBatch : null} locations={locations} locationId={locationId} canViewContact={capabilities.contact} onCreated={(created) => { toast.success("Student admitted"); closeCreate(false); navigate(`/app/clients/${created.client_id}`); }} />
  </PageShell>;
}

function HubActions({ hierarchy, canCreate, onAll, onCompare, onCreate }) {
  return <div className="flex flex-wrap gap-2">
    <Button variant="outline" onClick={onAll}><UsersThree className="mr-2" />All students</Button>
    <CohortCompareSheet data={hierarchy} selectedIds={[]} onApply={onCompare} trigger={<Button variant="outline"><Scales className="mr-2" />Compare cohorts</Button>} />
    {canCreate && <Button onClick={onCreate}><Plus className="mr-2" />New student</Button>}
  </div>;
}

function BatchCard({ batch, onOpen }) {
  const scopeCount = batch.placement_scope_count;
  const placed = batch.placed_count;
  const percent = scopeCount > 0 && placed != null ? Math.round((placed / scopeCount) * 100) : null;
  const departments = (batch.departments || []).slice(0, 3);
  return <button type="button" onClick={onOpen} className="surface-card surface-interactive group relative overflow-hidden p-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:p-6">
    <div className="absolute inset-y-0 left-0 w-1 bg-accent/85" />
    <div className="flex items-start justify-between gap-4"><div><div className="overline">Graduation batch</div><h3 className="mt-2 font-display text-2xl font-semibold">{batch.label}</h3></div><span className="grid h-10 w-10 place-items-center rounded-xl border bg-card text-muted-foreground transition-colors group-hover:border-primary/25 group-hover:text-primary"><ArrowRight /></span></div>
    <div className="mt-6 flex items-end gap-3"><span className="font-display text-4xl font-semibold tracking-[-0.05em]">{Number(batch.student_count || 0).toLocaleString("en-IN")}</span><span className="pb-1 text-sm text-muted-foreground">students</span></div>
    <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground"><span>{batch.department_count} departments</span><span aria-hidden="true">/</span><span>{batch.section_count} sections</span></div>
    {departments.length > 0 && <div className="mt-4 flex flex-wrap gap-1.5">{departments.map((department) => <span key={department.id} className="rounded-full bg-secondary px-2.5 py-1 text-[11px] font-semibold text-muted-foreground">{department.code}</span>)}{batch.department_count > departments.length && <span className="rounded-full bg-secondary px-2.5 py-1 text-[11px] font-semibold text-muted-foreground">+{batch.department_count - departments.length}</span>}</div>}
    {percent != null && <div className="mt-6 border-t pt-4"><div className="flex items-center justify-between text-xs"><span className="font-medium text-muted-foreground">Placement outcome</span><span className="font-semibold">{placed} of {scopeCount} placed</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-accent transition-all" style={{ width: `${percent}%` }} /></div></div>}
  </button>;
}

function ScopeBar({ batch, values, onChange }) {
  const controls = <ScopeControls batch={batch} values={values} onChange={onChange} />;
  return <Surface className="hidden p-3 md:block"><div className="mb-3 flex items-center justify-between"><div><div className="text-sm font-semibold">Academic scope</div><p className="mt-0.5 text-xs text-muted-foreground">Narrow this batch without leaving its workspace.</p></div><GraduationCap className="text-muted-foreground" /></div><div className="grid gap-3 md:grid-cols-3">{controls}</div></Surface>;
}

function ScopeControls({ batch, values, onChange }) {
  const departments = batch?.departments || [];
  const selectedDepartment = departments.find((row) => row.id === values.departmentId);
  const programs = uniqueById(selectedDepartment ? selectedDepartment.programs : departments.flatMap((row) => row.programs || []));
  const selectedProgram = programs.find((row) => row.id === values.programId);
  const sections = uniqueById(selectedProgram ? selectedProgram.sections : programs.flatMap((row) => row.sections || []));
  return <>
    <CompactSelect label="Department" value={values.departmentId || "all"} onChange={(value) => onChange("department", value)} options={departments.map((row) => [row.id, `${row.code} - ${row.name}`])} allLabel="All departments" />
    <CompactSelect label="Program" value={values.programId || "all"} onChange={(value) => onChange("program", value)} options={programs.map((row) => [row.id, `${row.code} - ${row.name}`])} allLabel="All programs" disabled={!programs.length} />
    <CompactSelect label="Section" value={values.cohortId || "all"} onChange={(value) => onChange("section", value)} options={sections.map((row) => [row.id, `${row.section === "GENERAL" ? "General" : row.section} - ${row.cohort_name}`])} allLabel="All sections" disabled={!sections.length} />
  </>;
}

function DirectoryFilters({ query, setQuery, readiness, placement, sort, capabilities, onChange, onMobileFilters }) {
  return <FilterBar className="sm:flex-wrap xl:flex-nowrap">
    <div className="relative min-w-0 flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} className="border-0 bg-surface-subtle pl-10 shadow-none" placeholder="Search name, admission number, or roll number" /></div>
    <Button type="button" variant="outline" className="md:hidden" onClick={onMobileFilters}><SlidersHorizontal className="mr-2" />Filters</Button>
    {capabilities.readiness && <CompactSelect value={readiness} onChange={(value) => onChange("readiness", value)} options={[["ready", "Placement ready"], ["developing", "Developing"], ["needs_support", "Needs support"], ["insufficient_evidence", "Evidence review"]]} allLabel="All readiness" className="hidden md:block md:w-44" />}
    {capabilities.placements && <CompactSelect value={placement} onChange={(value) => onChange("placement", value)} options={[["placed", "Placed"], ["unplaced", "Not placed"], ["seeking", "Seeking"], ["not_participating", "Not participating"]]} allLabel="All outcomes" className="hidden md:block md:w-44" />}
    {capabilities.assessments && <CompactSelect value={sort === "name" ? "all" : sort} onChange={(value) => onChange("sort", value)} options={[["academics_desc", "Best academics first"]]} allLabel="Sort by name" className="hidden md:block md:w-48" />}
  </FilterBar>;
}

function StudentFiltersSheet({ open, onOpenChange, batch, scopeValues, readiness, placement, sort, capabilities, onChange }) {
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent className="w-[92vw] overflow-y-auto sm:max-w-md"><SheetHeader className="text-left"><SheetTitle>Student filters</SheetTitle><SheetDescription>{batch ? `Narrow Class of ${batch.graduation_year} by its live academic structure and permitted evidence.` : "Narrow the authorized student directory."}</SheetDescription></SheetHeader><div className="mt-6 space-y-5">{batch && <div className="space-y-4"><div className="overline">Academic scope</div><ScopeControls batch={batch} values={scopeValues} onChange={onChange} /></div>}<div className="space-y-4 border-t pt-5"><div className="overline">Directory view</div>{capabilities.readiness && <CompactSelect label="Readiness" value={readiness} onChange={(value) => onChange("readiness", value)} options={[["ready", "Placement ready"], ["developing", "Developing"], ["needs_support", "Needs support"], ["insufficient_evidence", "Evidence review"]]} allLabel="All readiness" />}{capabilities.placements && <CompactSelect label="Placement outcome" value={placement} onChange={(value) => onChange("placement", value)} options={[["placed", "Placed"], ["unplaced", "Not placed"], ["seeking", "Seeking"], ["not_participating", "Not participating"]]} allLabel="All outcomes" />}{capabilities.assessments && <CompactSelect label="Sort" value={sort === "name" ? "all" : sort} onChange={(value) => onChange("sort", value)} options={[["academics_desc", "Best academics first"]]} allLabel="Sort by name" />}</div><Button className="w-full" onClick={() => onOpenChange(false)}>Show students</Button></div></SheetContent></Sheet>;
}

function CompactSelect({ label, value, onChange, options, allLabel, disabled, className = "" }) {
  return <label className={`block min-w-0 ${className}`}><span className={label ? "mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground" : "sr-only"}>{label || allLabel}</span><Select value={value || "all"} onValueChange={onChange} disabled={disabled}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{allLabel}</SelectItem>{options.map(([optionValue, optionLabel]) => <SelectItem key={optionValue} value={optionValue}>{optionLabel}</SelectItem>)}</SelectContent></Select></label>;
}

function SelectedCohorts({ data, selectedIds, onChange }) {
  const rows = flattenSections(data).filter((row) => selectedIds.includes(row.id));
  return <Surface className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><div className="text-sm font-semibold">Selected cohorts</div><div className="mt-2 flex flex-wrap gap-2">{rows.map((row) => <span key={row.id} className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold">{row.department_code} / {row.program_code} / {row.section} / {row.graduation_year}</span>)}</div></div><CohortCompareSheet data={data} selectedIds={selectedIds} onApply={onChange} trigger={<Button variant="outline" size="sm">Change</Button>} /></Surface>;
}

function AdmissionDrawer({ open, onOpenChange, hierarchy, selectedBatch, locations, locationId, canViewContact, onCreated }) {
  const [admitStudent, admitState] = useAdmitCollegeStudentMutation();
  const options = useMemo(() => admissionOptions(hierarchy, selectedBatch?.graduation_year), [hierarchy, selectedBatch]);
  const defaultCohort = options.cohorts.length === 1 ? options.cohorts[0] : null;
  const form = useForm({
    resolver: zodResolver(studentAdmissionSchema),
    defaultValues: {
      ...EMPTY_STUDENT,
      home_location_id: locationId || "",
      program_id: defaultCohort?.program_id || "",
      cohort_id: defaultCohort?.id || "",
    },
    ...FORM_OPTIONS,
  });
  const programId = form.watch("program_id");
  const cohorts = options.cohorts.filter((row) => !programId || row.program_id === programId);
  useEffect(() => {
    if (!open) return;
    const only = options.cohorts.length === 1 ? options.cohorts[0] : null;
    form.reset({
      ...EMPTY_STUDENT,
      home_location_id: locationId || "",
      program_id: only?.program_id || "",
      cohort_id: only?.id || "",
    });
  }, [form, locationId, open, options.cohorts]);
  const submit = form.handleSubmit(async (values) => {
    form.clearErrors("root.server");
    try {
      const created = await admitStudent({ ...values, last_name: values.last_name || "", home_location_id: values.home_location_id || null }).unwrap();
      onCreated(created);
    } catch (error) {
      const normalized = applyApiErrors(error, form.setError, { fallback: "Student could not be admitted" });
      if (!Object.keys(normalized.fieldErrors).length) form.setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <DrawerForm open={open} onOpenChange={(next) => { if (!admitState.isLoading) onOpenChange(next); }} title={selectedBatch ? `Admit to Class of ${selectedBatch.graduation_year}` : "Admit student"} description="Connect the student to the college's live program and cohort structure.">
    <Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
      <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={form.control} name="first_name" label="First name"><Input autoFocus autoComplete="given-name" /></ValidatedField><ValidatedField control={form.control} name="last_name" label="Last name"><Input autoComplete="family-name" /></ValidatedField></div>
      <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={form.control} name="admission_number" label="Admission number"><Input /></ValidatedField><ValidatedField control={form.control} name="roll_number" label="Roll number"><Input /></ValidatedField></div>
      <div className="grid gap-4 sm:grid-cols-2"><FormField control={form.control} name="program_id" render={({ field }) => <FormItem><FormLabel>Program</FormLabel><Select value={field.value || ""} onValueChange={(value) => { field.onChange(value); form.setValue("cohort_id", "", { shouldValidate: true }); }}><FormControl><SelectTrigger><SelectValue placeholder="Choose program" /></SelectTrigger></FormControl><SelectContent>{options.programs.map((row) => <SelectItem key={row.id} value={row.id}>{row.department_code} / {row.code}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} /><FormField control={form.control} name="cohort_id" render={({ field }) => <FormItem><FormLabel>Batch and section</FormLabel><Select value={field.value || ""} onValueChange={field.onChange} disabled={!programId}><FormControl><SelectTrigger><SelectValue placeholder="Choose cohort" /></SelectTrigger></FormControl><SelectContent>{cohorts.map((row) => <SelectItem key={row.id} value={row.id}>{row.label}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} /></div>
      <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={form.control} name="current_semester" label="Current semester"><Input inputMode="numeric" /></ValidatedField><ValidatedField control={form.control} name="admitted_on" label="Admitted on"><Input type="date" /></ValidatedField></div>
      {canViewContact && <div className="grid gap-4 sm:grid-cols-2"><ValidatedField control={form.control} name="email" label="Email"><Input type="email" autoComplete="email" /></ValidatedField><ValidatedField control={form.control} name="phone" label="Phone"><Input inputMode="tel" autoComplete="tel" /></ValidatedField></div>}
      <FormField control={form.control} name="home_location_id" render={({ field }) => <FormItem><FormLabel>Campus</FormLabel><Select value={field.value || ""} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue placeholder="Choose campus" /></SelectTrigger></FormControl><SelectContent>{locations.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />
      <FormRootError error={form.formState.errors.root?.server} />
      <Button type="submit" className="w-full" loading={form.formState.isSubmitting || admitState.isLoading} loadingText="Admitting..." disabled={!form.formState.isValid}>Admit student</Button>
    </form></Form>
  </DrawerForm>;
}

function ValidatedField({ control, name, label, children }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />;
}

function studentColumns(capabilities) {
  const columns = [{
    key: "student", label: "Student", render: (item) => <div className="flex min-w-0 items-center gap-3 lg:min-w-52"><EntityAvatar name={item.name} className="h-10 w-10 shrink-0" /><div className="min-w-0"><div className="truncate font-semibold">{item.name}</div><div className="mt-0.5 text-xs text-muted-foreground">{[item.admission_number, item.roll_number].filter(Boolean).join(" / ") || "Student record"}</div></div></div>,
  }, {
    key: "academic_group", label: "Academic group", render: (item) => <div><div className="font-medium">{item.department?.code || "Department"} / {item.program?.code || "Program"}</div><div className="mt-1 text-xs text-muted-foreground">Class of {item.graduation_year || "-"} / {item.section || "General"}{item.semester ? ` / Sem ${item.semester}` : ""}</div></div>,
  }];
  if (capabilities.assessments || capabilities.attendance || capabilities.coding || capabilities.documents) columns.push({
    key: "evidence", label: "Permitted evidence", render: (item) => <div className="space-y-1 text-xs">{capabilities.assessments && <div><span className="text-muted-foreground">CGPA</span> <span className="font-semibold">{item.cgpa ?? "Not recorded"}</span>{item.active_backlogs > 0 && <span className="ml-2 text-warning">{item.active_backlogs} backlog</span>}</div>}{capabilities.attendance && <div><span className="text-muted-foreground">Attendance</span> <span className={item.attendance_percent != null && item.attendance_percent < 75 ? "font-semibold text-warning" : "font-semibold"}>{item.attendance_percent == null ? "Not recorded" : `${item.attendance_percent}%`}</span></div>}{capabilities.coding && <div><span className="text-muted-foreground">Coding</span> <span className="font-semibold">{item.coding_total == null ? "Not connected" : `${item.coding_total} solved`}</span></div>}{capabilities.documents && <div><span className="text-muted-foreground">Resume</span> <span className="font-semibold">{sentence(item.resume_status || "missing")}</span></div>}</div>,
  });
  if (capabilities.readiness) columns.push({
    key: "readiness", label: "Readiness", render: (item) => <div className="space-y-1.5"><StatusBadge status={readinessTone(item.readiness_band)} label={readinessLabel(item.readiness_band)} />{item.readiness?.score != null && <div className="text-xs text-muted-foreground">{item.readiness.score}% score / {item.readiness.coverage_percent}% evidence</div>}</div>,
  });
  if (capabilities.placements) columns.push({
    key: "placement", label: "Placement outcome", render: (item) => <StatusBadge status={placementTone(item.placement_status)} label={sentence(item.placement_status || "seeking")} />,
  });
  return columns;
}

function summaryMetrics(data) {
  if (!data) return [];
  return [
    { id: "all", label: "Total students", value: data.total_students },
    data.placement_ready == null ? null : { id: "ready", label: "Placement ready", value: data.placement_ready, tone: "positive" },
    data.needs_support == null ? null : { id: "needs_support", label: "Needs support", value: data.needs_support, tone: data.needs_support ? "warning" : "neutral" },
    data.placed_students == null ? null : { id: "placed", label: "Placed", value: data.placed_students, tone: "positive" },
  ].filter(Boolean);
}

function ErrorStateRow({ title, error, retry }) {
  return <Surface className="flex flex-col gap-3 border-warning/25 bg-warning/5 p-4 sm:flex-row sm:items-center"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-warning/10 text-warning"><WarningCircle /></span><div className="min-w-0 flex-1"><div className="font-semibold">{title}</div><p className="mt-0.5 text-xs text-muted-foreground">{error?.data?.detail || "Your current scope is unchanged. Try this section again."}</p></div><Button variant="outline" size="sm" onClick={retry}>Try again</Button></Surface>;
}

function StudentHubSkeleton() {
  return <PageShell aria-label="Loading students"><div><Skeleton className="h-3 w-28" /><Skeleton className="mt-3 h-9 w-44" /><Skeleton className="mt-3 h-4 w-[32rem] max-w-full" /></div><MetricStrip loading /><div className="space-y-3"><Skeleton className="h-7 w-48" /><ResponsiveCardGrid minWidth="18rem">{[1, 2, 3, 4].map((row) => <Surface key={row} className="h-64 p-5"><Skeleton className="h-3 w-24" /><Skeleton className="mt-4 h-8 w-36" /><Skeleton className="mt-10 h-10 w-24" /><Skeleton className="mt-5 h-3 w-40" /></Surface>)}</ResponsiveCardGrid></div></PageShell>;
}

function admissionOptions(hierarchy, graduationYear) {
  const programs = new Map();
  const cohorts = [];
  (hierarchy?.items || []).filter((batch) => !graduationYear || Number(batch.graduation_year) === Number(graduationYear)).forEach((batch) => batch.departments.forEach((department) => department.programs.forEach((program) => {
    programs.set(program.id, { ...program, department_code: department.code });
    program.sections.forEach((section) => cohorts.push({ ...section, program_id: program.id, label: `${program.code} / ${section.section === "GENERAL" ? "General" : section.section} / ${batch.graduation_year}` }));
  })));
  return { programs: [...programs.values()], cohorts };
}

function flattenSections(data) {
  return (data?.items || []).flatMap((batch) =>
    batch.departments.flatMap((department) =>
      department.programs.flatMap((program) =>
        program.sections.map((section) => ({
          ...section,
          graduation_year: batch.graduation_year,
          department_code: department.code,
          program_code: program.code,
        })),
      ),
    ),
  );
}

function collegeStudentsAIContext({
  hierarchy,
  mode,
  selectedBatch,
  cohortIds,
  departmentId,
  programId,
  cohortId,
}) {
  if (!hierarchy) return null;
  if (mode === "compare") {
    const reachable = new Map(flattenSections(hierarchy).map((row) => [row.id, row]));
    const selected = cohortIds.map((id) => reachable.get(id)).filter(Boolean);
    if (!selected.length || selected.length !== cohortIds.length) return null;
    return {
      kind: "college_scope",
      id: `cohorts:${selected.map((row) => row.id).sort().join(",")}`,
      label: `${selected.length} selected cohorts`,
      cohort_ids: selected.map((row) => row.id),
    };
  }
  if (mode !== "batch" || !selectedBatch) return null;

  const departments = selectedBatch.departments || [];
  const department = departmentId
    ? departments.find((row) => row.id === departmentId)
    : null;
  if (departmentId && !department) return null;
  const programs = uniqueById(
    department ? department.programs || [] : departments.flatMap((row) => row.programs || []),
  );
  const program = programId ? programs.find((row) => row.id === programId) : null;
  if (programId && !program) return null;
  const sections = uniqueById(
    program ? program.sections || [] : programs.flatMap((row) => row.sections || []),
  );
  const cohort = cohortId ? sections.find((row) => row.id === cohortId) : null;
  if (cohortId && !cohort) return null;

  const graduationYear = Number(selectedBatch.graduation_year);
  const label = cohort
    ? `${program?.code || "Cohort"} ${graduationYear} / ${cohort.section === "GENERAL" ? "General" : cohort.section}`
    : program
      ? `${program.name} / ${graduationYear}`
      : department
        ? `${department.name} / ${graduationYear}`
        : selectedBatch.label || `${graduationYear} batch`;
  return {
    kind: "college_scope",
    id: cohort
      ? `cohort:${cohort.id}`
      : program
        ? `program:${program.id}:${graduationYear}`
        : department
          ? `department:${department.id}:${graduationYear}`
          : `graduation:${graduationYear}`,
    label,
    graduation_year: graduationYear,
    department_id: department?.id || null,
    program_id: program?.id || null,
    cohort_id: cohort?.id || null,
    cohort_ids: cohort ? [cohort.id] : [],
  };
}

function uniqueById(rows) {
  return [...new Map(rows.map((row) => [row.id, row])).values()];
}

function currentQueryData(query) {
  if (query.currentData !== undefined) return query.currentData;
  if (query.isFetching || query.isError || query.isUninitialized) return undefined;
  return query.data;
}

function applyMetric(params, metric) {
  params.delete("readiness");
  params.delete("placement");
  if (metric === "ready") {
    params.set("readiness", "ready");
    params.set("placement", "unplaced");
  }
  if (metric === "needs_support") {
    params.set("readiness", "needs_support");
    params.set("placement", "unplaced");
  }
  if (metric === "placed") params.set("placement", "placed");
}

function updateParams(setSearchParams, current, mutate, replace) {
  const next = new URLSearchParams(current);
  mutate(next);
  setSearchParams(next, { replace });
}

function setOrDelete(params, key, value) {
  if (value) params.set(key, String(value));
  else params.delete(key);
}

function validYear(value) {
  if (!/^\d{4}$/.test(value || "")) return null;
  const year = Number(value);
  return year >= 2000 && year <= 2200 ? year : null;
}

function sentence(value = "") { return String(value).replaceAll("_", " ").replace(/^./, (match) => match.toUpperCase()); }
function readinessLabel(value) { return value === "insufficient_evidence" ? "Evidence review" : sentence(value || "insufficient_evidence"); }
function readinessTone(value) { return value === "ready" ? "active" : value === "needs_support" ? "warning" : value === "developing" ? "scheduled" : "pending"; }
function placementTone(value) { return ["selected", "offered", "placed", "joined"].includes(value) ? "completed" : value === "not_participating" ? "inactive" : "pending"; }
