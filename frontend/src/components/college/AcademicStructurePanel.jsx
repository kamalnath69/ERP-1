import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import {
  Archive, ArrowRight, Books, Buildings, CalendarBlank, CheckCircle,
  GraduationCap, MagnifyingGlass, PencilSimple, Plus, SquaresFour, Stack,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { ValidatedActionDialog } from "@/components/forms/ValidatedActionDialog";
import AcademicResourceCombobox from "@/components/college/AcademicResourceCombobox";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar,
  SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage,
  FormRootError,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import {
  useCreateCollegeCohortMutation, useCreateCollegeCohortsBulkMutation,
  useCreateCollegeCourseMutation, useCreateCollegeDepartmentMutation,
  useCreateCollegeOfferingMutation, useCreateCollegeProgramMutation,
  useCreateCollegeTermMutation, useGetCollegeAcademicHierarchyQuery,
  useGetCollegeCohortsPageQuery, useGetCollegeCoursesPageQuery,
  useGetCollegeDepartmentsPageQuery, useGetCollegeOfferingsPageQuery,
  useGetCollegeProgramsPageQuery, useGetCollegeTermsPageQuery,
  useSetCollegeAcademicRecordArchivedMutation, useUpdateCollegeAcademicRecordMutation,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import {
  academicLifecycleSchema, applyApiErrors, collegeBulkCohortSchema,
  collegeCohortSchema, collegeCourseSchema, collegeDepartmentSchema,
  collegeOfferingSchema, collegeProgramSchema, collegeTermSchema, FORM_OPTIONS,
} from "@/lib/validation";

const TABS = [
  ["overview", "Overview"],
  ["departments", "Departments"],
  ["programs", "Programs"],
  ["cohorts", "Batches & sections"],
  ["terms", "Academic years & terms"],
  ["courses", "Courses & offerings"],
];

const RESOURCE_META = {
  departments: { singular: "department", title: "Departments", icon: Buildings },
  programs: { singular: "program", title: "Programs", icon: GraduationCap },
  cohorts: { singular: "batch", title: "Batches & sections", icon: SquaresFour },
  terms: { singular: "term", title: "Academic years & terms", icon: CalendarBlank },
  courses: { singular: "course", title: "Courses", icon: Books },
  offerings: { singular: "offering", title: "Course offerings", icon: Stack },
};

function isArchived(resource, row) {
  return resource === "terms" || resource === "offerings"
    ? row.status === "archived"
    : row.is_active === false;
}

function useAcademicPage(resource, search, visibility) {
  const deferredSearch = useDeferredValue(search.trim());
  const filterKey = `${resource}:${deferredSearch}:${visibility}`;
  const paging = useCursorPagination(filterKey);
  const common = { q: deferredSearch || undefined, cursor: paging.cursor || undefined, limit: 25 };
  const active = visibility === "active" ? true : visibility === "archived" ? false : undefined;
  const options = (name) => ({ skip: resource !== name });
  const departments = useGetCollegeDepartmentsPageQuery({ ...common, active }, options("departments"));
  const programs = useGetCollegeProgramsPageQuery({ ...common, active }, options("programs"));
  const cohorts = useGetCollegeCohortsPageQuery({ ...common, active }, options("cohorts"));
  const terms = useGetCollegeTermsPageQuery({ ...common, active }, options("terms"));
  const courses = useGetCollegeCoursesPageQuery({ ...common, active }, options("courses"));
  const offerings = useGetCollegeOfferingsPageQuery({ ...common, active }, options("offerings"));
  const query = { departments, programs, cohorts, terms, courses, offerings }[resource];
  const { accept } = paging;
  useEffect(() => { accept(query.data); }, [accept, query.data]);
  return { query, paging, rows: paging.items, deferredSearch };
}

export default function AcademicStructurePanel() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") || "overview";
  const tab = TABS.some(([value]) => value === requestedTab) ? requestedTab : "overview";
  const chooseTab = (value) => {
    const next = new URLSearchParams(searchParams);
    if (value === "overview") next.delete("tab"); else next.set("tab", value);
    setSearchParams(next, { replace: true });
  };

  return <div className="space-y-5">
    <Surface className="overflow-hidden">
      <div className="border-b px-4 py-4 sm:px-5">
        <div className="overline">Academic foundation</div>
        <div className="mt-1 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-display text-2xl font-semibold">Academic structure</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">Define the institution hierarchy used by students, ERP synchronization, placement filters, attendance, and grounded AI.</p>
          </div>
          <StatusBadge status="active" label="Live source of truth" />
        </div>
      </div>
      <div className="premium-scrollbar overflow-x-auto p-2">
        <SegmentControl className="w-max min-w-full border-0 shadow-none" value={tab} onChange={chooseTab} items={TABS.map(([value, label]) => ({ value, label }))} />
      </div>
    </Surface>

    {tab === "overview" ? <StructureOverview onOpen={chooseTab} />
      : tab === "courses" ? <CourseAndOfferingPanel />
        : <ResourcePanel resource={tab} />}
  </div>;
}

function StructureOverview({ onOpen }) {
  const { can } = useAuth();
  const hierarchy = useGetCollegeAcademicHierarchyQuery();
  const departments = useGetCollegeDepartmentsPageQuery({ active: true, limit: 1 });
  const programs = useGetCollegeProgramsPageQuery({ active: true, limit: 1 });
  const cohorts = useGetCollegeCohortsPageQuery({ active: true, limit: 1 });
  if (hierarchy.isLoading && !hierarchy.data) return <Surface className="h-56 animate-pulse bg-surface-subtle" />;
  if (hierarchy.isError && !hierarchy.data) return <ErrorState title="Academic structure could not be loaded" description="Retry before changing institution structure." retry={hierarchy.refetch} />;
  const summary = hierarchy.data?.summary || {};
  const steps = [
    { id: "departments", title: "Create departments", detail: "Define institution-owned names and codes.", complete: Boolean(departments.data?.items?.length) },
    { id: "programs", title: "Add programs", detail: "Connect each qualification to a department.", complete: Boolean(programs.data?.items?.length) },
    { id: "cohorts", title: "Create batches and sections", detail: "Set graduation year, semester, and sections.", complete: Boolean(cohorts.data?.items?.length) },
  ];
  const setupComplete = steps.every((step) => step.complete);
  return <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(18rem,.6fr)]">
    <Surface className="overflow-hidden">
      <div className="border-b p-5">
        <div className="overline">Guided setup</div>
        <h3 className="mt-1 font-display text-2xl font-semibold">Start with placement essentials</h3>
        <p className="mt-1 text-sm text-muted-foreground">Terms and courses can be added later. Students need a department, program, and graduation batch first.</p>
      </div>
      <div className="divide-y">{steps.map((step, index) => <button key={step.id} type="button" onClick={() => onOpen(step.id)} className="group flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-surface-hover">
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl text-sm font-bold ${step.complete ? "bg-positive/10 text-positive" : "bg-secondary text-muted-foreground"}`}>{step.complete ? <CheckCircle weight="fill" size={20} /> : index + 1}</span>
        <span className="min-w-0 flex-1"><span className="block font-semibold">{step.title}</span><span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{step.detail}</span></span>
        <ArrowRight className="shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </button>)}</div>
    </Surface>
    <div className="space-y-5">
      <Surface className="p-5">
        <div className="flex items-center justify-between"><div className="overline">Active structure</div><StatusBadge status={setupComplete ? "completed" : "pending"} label={setupComplete ? "Ready" : "Setup needed"} /></div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <Metric label="Graduation batches" value={summary.batch_count || 0} />
          <Metric label="Departments" value={summary.department_count || 0} />
          <Metric label="Sections" value={summary.section_count || 0} />
          <Metric label="Students linked" value={summary.student_count || 0} />
        </div>
      </Surface>
      <Surface className="p-5">
        <div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><Stack /></span><div><h3 className="font-semibold">ERP-safe ownership</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">Matching ERP codes require reviewed linking. Source updates respect manual overrides and never delete missing local records.</p></div></div>
        {can("college.integrations.manage") && <Button className="mt-4 w-full" variant="outline" onClick={() => onOpen("departments")}>Review structure</Button>}
      </Surface>
    </div>
  </div>;
}

function Metric({ label, value }) {
  return <div className="rounded-xl border bg-surface-subtle p-3"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 font-display text-2xl font-semibold">{Number(value).toLocaleString("en-IN")}</div></div>;
}

function CourseAndOfferingPanel() {
  const [resource, setResource] = useState("courses");
  return <div className="space-y-4">
    <SegmentControl value={resource} onChange={setResource} items={[{ value: "courses", label: "Course catalog" }, { value: "offerings", label: "Term offerings" }]} />
    <ResourcePanel resource={resource} />
  </div>;
}

function ResourcePanel({ resource }) {
  const { can } = useAuth();
  const canManage = can("college.academics.manage");
  const meta = RESOURCE_META[resource];
  const [search, setSearch] = useState("");
  const [visibility, setVisibility] = useState("active");
  const [editor, setEditor] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [lifecycle, setLifecycle] = useState(null);
  const { query, paging, rows, deferredSearch } = useAcademicPage(resource, search, visibility);
  const [setArchived] = useSetCollegeAcademicRecordArchivedMutation();
  const columns = useMemo(() => columnsFor(resource, canManage, setEditor, setLifecycle), [resource, canManage]);
  const filtered = Boolean(deferredSearch || visibility !== "active");
  const Icon = meta.icon;
  const empty = <EmptyState
    variant={filtered ? "filtered" : "section"}
    alignment="left"
    icon={Icon}
    title={filtered ? `No ${meta.title.toLowerCase()} match this view` : `No ${meta.title.toLowerCase()} yet`}
    description={filtered ? "Clear the search or change the lifecycle filter." : emptyDescription(resource)}
    primaryAction={filtered ? <Button variant="outline" onClick={() => { setSearch(""); setVisibility("active"); }}>Clear filters</Button> : canManage ? <Button onClick={() => setEditor({ resource, row: null })}><Plus className="mr-2" />Add {meta.singular}</Button> : null}
  />;

  return <>
    <Surface className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div><div className="overline">Institution structure</div><h3 className="mt-1 font-display text-xl font-semibold">{meta.title}</h3></div>
        {canManage && <div className="flex flex-col gap-2 sm:flex-row">
          {resource === "cohorts" && <Button variant="outline" onClick={() => setBulkOpen(true)}><SquaresFour className="mr-2" />Create sections</Button>}
          <Button onClick={() => setEditor({ resource, row: null })}><Plus className="mr-2" />Add {meta.singular}</Button>
        </div>}
      </div>
      <FilterBar className="rounded-none border-x-0 border-t-0">
        <div className="relative min-w-0 flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input className="pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${meta.title.toLowerCase()}`} /></div>
        <Select value={visibility} onValueChange={setVisibility}><SelectTrigger className="w-full sm:w-40"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="all">All records</SelectItem><SelectItem value="archived">Archived</SelectItem></SelectContent></Select>
      </FilterBar>
      {query.isError && !query.data ? <ErrorState className="m-4" title={`${meta.title} could not be loaded`} retry={query.refetch} /> : <DataTable className="rounded-none border-0 shadow-none" rows={rows} columns={columns} loading={query.isLoading && !rows.length} empty={empty} />}
      <CursorListFooter count={rows.length} noun={meta.title.toLowerCase()} hasMore={Boolean(query.data?.has_more)} loading={query.isFetching} error={query.isError} onLoadMore={() => paging.loadMore(query.data?.next_cursor)} onRetry={query.refetch} />
    </Surface>
    <AcademicEditor open={Boolean(editor)} editor={editor} onOpenChange={(open) => !open && setEditor(null)} />
    <BulkCohortEditor open={bulkOpen} onOpenChange={setBulkOpen} />
    <ValidatedActionDialog
      open={Boolean(lifecycle)}
      onOpenChange={(open) => !open && setLifecycle(null)}
      title={`${lifecycle?.archived ? "Restore" : "Archive"} ${meta.singular}`}
      description={lifecycle?.archived ? "Restore this record to active academic structure." : "Archive only after reviewing dependent records."}
      impact={lifecycle?.archived ? "The record becomes available to new workflows again." : lifecycle?.row?.dependency_count ? `${lifecycle.row.dependency_count} active dependencies must be handled first.` : "Existing history is retained, but the record is removed from active selectors."}
      schema={academicLifecycleSchema}
      defaultValues={{ reason: "" }}
      fields={[{ name: "reason", label: "Reason", type: "textarea", placeholder: "Explain this lifecycle change" }]}
      submitLabel={lifecycle?.archived ? "Restore record" : "Archive record"}
      loadingText={lifecycle?.archived ? "Restoring..." : "Archiving..."}
      variant={lifecycle?.archived ? "default" : "destructive"}
      onSubmit={async ({ reason }) => {
        await setArchived({ resource, id: lifecycle.row.id, archived: !lifecycle.archived, version: lifecycle.row.version, reason }).unwrap();
        toast.success(lifecycle.archived ? "Academic record restored" : "Academic record archived");
      }}
    />
  </>;
}

function columnsFor(resource, canManage, onEdit, onLifecycle) {
  const identity = { key: "name", label: RESOURCE_META[resource].singular.replace(/^./, (value) => value.toUpperCase()), render: (row) => <div><div className="font-semibold">{row.display_name || row.name || row.course_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.code || row.course_code || row.academic_year || "Institution record"}</div></div> };
  const map = {
    departments: [identity, { key: "programs", label: "Programs", render: (row) => `${row.active_program_count || 0} active / ${row.program_count || 0} total` }],
    programs: [identity, { key: "department", label: "Department", render: (row) => `${row.department_code} / ${row.department_name}` }, { key: "duration", label: "Duration", render: (row) => `${row.duration_semesters} semesters` }, { key: "batches", label: "Batches", render: (row) => `${row.active_cohort_count || 0} active` }],
    cohorts: [identity, { key: "program", label: "Program", render: (row) => `${row.department_code} / ${row.program_code}` }, { key: "class", label: "Class", render: (row) => `Class of ${row.graduation_year} / ${row.section || "GENERAL"}` }, { key: "students", label: "Students", render: (row) => `${row.active_student_count || 0} active` }],
    terms: [identity, { key: "dates", label: "Teaching period", render: (row) => `${shortDate(row.starts_on)} - ${shortDate(row.ends_on)}` }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} label={row.is_current ? "Current" : sentence(row.status)} /> }, { key: "offerings", label: "Offerings", render: (row) => `${row.active_offering_count || 0} active` }],
    courses: [identity, { key: "department", label: "Department", render: (row) => `${row.department_code} / ${row.department_name}` }, { key: "type", label: "Type", render: (row) => `${sentence(row.course_type)} / ${row.credits} credits` }, { key: "offerings", label: "Offerings", render: (row) => `${row.active_offering_count || 0} active` }],
    offerings: [identity, { key: "batch", label: "Batch", render: (row) => `${row.department_code} / ${row.cohort_name}` }, { key: "term", label: "Term", render: (row) => `${row.term_name} / ${row.academic_year}` }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }],
  };
  const columns = map[resource];
  if (canManage) columns.push({ key: "actions", label: "", render: (row) => <div className="flex justify-end gap-1"><Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); onEdit({ resource, row }); }}><PencilSimple className="mr-1.5" />Edit</Button><Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); onLifecycle({ row, archived: isArchived(resource, row) }); }}><Archive className="mr-1.5" />{isArchived(resource, row) ? "Restore" : "Archive"}</Button></div> });
  return columns;
}

function AcademicEditor({ open, editor, onOpenChange }) {
  const resource = editor?.resource;
  const row = editor?.row;
  if (!resource) return null;
  return <DrawerForm open={open} onOpenChange={onOpenChange} title={`${row ? "Edit" : "Add"} ${RESOURCE_META[resource].singular}`} description="Changes become available to student workflows, filters, ERP linking, and Edvatiq AI immediately.">
    <AcademicRecordForm key={`${resource}:${row?.id || "new"}`} resource={resource} row={row} onSaved={() => onOpenChange(false)} />
  </DrawerForm>;
}

function AcademicRecordForm({ resource, row, onSaved }) {
  const schema = schemas[resource];
  const form = useForm({ resolver: zodResolver(schema), defaultValues: defaultsFor(resource, row), ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, setError } = form;
  const [createDepartment, departmentState] = useCreateCollegeDepartmentMutation();
  const [createProgram, programState] = useCreateCollegeProgramMutation();
  const [createCohort, cohortState] = useCreateCollegeCohortMutation();
  const [createTerm, termState] = useCreateCollegeTermMutation();
  const [createCourse, courseState] = useCreateCollegeCourseMutation();
  const [createOffering, offeringState] = useCreateCollegeOfferingMutation();
  const [updateRecord, updateState] = useUpdateCollegeAcademicRecordMutation();
  const creators = { departments: createDepartment, programs: createProgram, cohorts: createCohort, terms: createTerm, courses: createCourse, offerings: createOffering };
  const loading = updateState.isLoading || [departmentState, programState, cohortState, termState, courseState, offeringState].some((state) => state.isLoading);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    const payload = resource === "offerings" && !row
      ? { ...values, weekly_schedule: [] }
      : values;
    try {
      if (row) await updateRecord({ resource, id: row.id, data: { ...payload, version: row.version } }).unwrap();
      else await creators[resource](payload).unwrap();
      toast.success(`${RESOURCE_META[resource].singular.replace(/^./, (value) => value.toUpperCase())} ${row ? "updated" : "created"}`);
      onSaved();
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Academic structure could not be saved" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
    <FieldsFor resource={resource} control={control} row={row} />
    <FormRootError error={formState.errors.root?.server} />
    <Button type="submit" className="w-full" loading={formState.isSubmitting || loading} loadingText="Saving..." disabled={!formState.isValid}>Save {RESOURCE_META[resource].singular}</Button>
  </form></Form>;
}

function FieldsFor({ resource, control, row }) {
  if (resource === "departments") return <><TextField control={control} name="name" label="Department name" autoFocus /><TextField control={control} name="code" label="Department code" description="Use the institution's official code. AI resolves against live codes and names." /><TextAreaField control={control} name="description" label="Description" /></>;
  if (resource === "programs") return <><AcademicSelectField control={control} name="department_id" label="Department" resource="departments" selectedItem={row ? { id: row.department_id, name: row.department_name, code: row.department_code } : null} /><TextField control={control} name="name" label="Program name" autoFocus /><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="code" label="Program code" /><SelectField control={control} name="degree_type" label="Qualification type" options={[["undergraduate", "Undergraduate"], ["postgraduate", "Postgraduate"], ["diploma", "Diploma"], ["certificate", "Certificate"]]} /></div><TextField control={control} name="duration_semesters" label="Duration in semesters" inputMode="numeric" /></>;
  if (resource === "cohorts") return <><AcademicSelectField control={control} name="program_id" label="Program" resource="programs" selectedItem={row ? { id: row.program_id, name: row.program_name, code: row.program_code } : null} /><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="name" label="Batch name" autoFocus /><TextField control={control} name="code" label="Batch code" /></div><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="admission_year" label="Admission year" inputMode="numeric" /><TextField control={control} name="graduation_year" label="Graduation year" inputMode="numeric" /></div><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="current_semester" label="Current semester" inputMode="numeric" /><TextField control={control} name="section" label="Section" placeholder="GENERAL" description="A blank section is stored as GENERAL." /></div></>;
  if (resource === "terms") return <><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="name" label="Term name" autoFocus /><TextField control={control} name="academic_year" label="Academic year" placeholder="2026-27" /></div><TextField control={control} name="term_number" label="Term number" inputMode="numeric" /><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="starts_on" label="Starts on" type="date" /><TextField control={control} name="ends_on" label="Ends on" type="date" /></div><SelectField control={control} name="status" label="Lifecycle status" options={[["planned", "Planned"], ["active", "Active"], ["closed", "Closed"]]} /><BooleanField control={control} name="is_current" label="Use as the current academic term" description="Only one term can be current." /></>;
  if (resource === "courses") return <><AcademicSelectField control={control} name="department_id" label="Department" resource="departments" selectedItem={row ? { id: row.department_id, name: row.department_name, code: row.department_code } : null} /><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="name" label="Course name" autoFocus /><TextField control={control} name="code" label="Course code" /></div><div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="credits" label="Credits" inputMode="numeric" /><SelectField control={control} name="course_type" label="Course type" options={[["core", "Core"], ["elective", "Elective"], ["lab", "Lab"], ["project", "Project"], ["audit", "Audit"]]} /></div></>;
  return <><AcademicSelectField control={control} name="term_id" label="Academic term" resource="terms" selectedItem={row ? { id: row.term_id, name: row.term_name, academic_year: row.academic_year } : null} /><AcademicSelectField control={control} name="course_id" label="Course" resource="courses" selectedItem={row ? { id: row.course_id, name: row.course_name, code: row.course_code } : null} /><AcademicSelectField control={control} name="cohort_id" label="Batch and section" resource="cohorts" selectedItem={row ? { id: row.cohort_id, name: row.cohort_name, section: row.section, graduation_year: row.graduation_year } : null} /><TextField control={control} name="room" label="Room or venue" /></>;
}

function BulkCohortEditor({ open, onOpenChange }) {
  const form = useForm({ resolver: zodResolver(collegeBulkCohortSchema), defaultValues: defaultsFor("bulk"), ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError } = form;
  const idempotencyKey = useRef(crypto.randomUUID());
  const [createBulk, mutation] = useCreateCollegeCohortsBulkMutation();
  useEffect(() => {
    if (open) idempotencyKey.current = crypto.randomUUID();
  }, [open]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await createBulk({ ...values, idempotency_key: idempotencyKey.current }).unwrap();
      toast.success("Batch sections created");
      reset(defaultsFor("bulk"));
      idempotencyKey.current = crypto.randomUUID();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Sections could not be created" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Create batch sections" description="Create several sections for one program and graduation year in a single transaction."><Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
    <AcademicSelectField control={control} name="program_id" label="Program" resource="programs" enabled={open} />
    <div className="grid gap-4 sm:grid-cols-2"><TextField control={control} name="admission_year" label="Admission year" inputMode="numeric" /><TextField control={control} name="graduation_year" label="Graduation year" inputMode="numeric" /></div>
    <TextField control={control} name="current_semester" label="Current semester" inputMode="numeric" />
    <TextField control={control} name="sections" label="Sections" placeholder="A, B, C" description="Separate section names with commas. Use GENERAL for a batch without named sections." />
    <TextField control={control} name="code_prefix" label="Code prefix" placeholder="Optional; generated from the program and year" />
    <FormRootError error={formState.errors.root?.server} />
    <Button type="submit" className="w-full" loading={formState.isSubmitting || mutation.isLoading} loadingText="Creating sections..." disabled={!formState.isValid}>Create sections</Button>
  </form></Form></DrawerForm>;
}

const schemas = { departments: collegeDepartmentSchema, programs: collegeProgramSchema, cohorts: collegeCohortSchema, terms: collegeTermSchema, courses: collegeCourseSchema, offerings: collegeOfferingSchema };

function defaultsFor(resource, row = null) {
  const year = new Date().getFullYear();
  const values = {
    departments: { name: "", code: "", description: "" },
    programs: { department_id: "", name: "", code: "", degree_type: "undergraduate", duration_semesters: "8" },
    cohorts: { program_id: "", name: "", code: "", admission_year: String(year), graduation_year: String(year + 4), current_semester: "1", section: "GENERAL" },
    terms: { name: "", academic_year: `${year}-${String(year + 1).slice(-2)}`, term_number: "1", starts_on: "", ends_on: "", status: "planned", is_current: false },
    courses: { department_id: "", name: "", code: "", credits: "3", course_type: "core" },
    offerings: { term_id: "", course_id: "", cohort_id: "", room: "" },
    bulk: { program_id: "", admission_year: String(year), graduation_year: String(year + 4), current_semester: "1", sections: "A, B", code_prefix: "" },
  }[resource];
  if (!row) return values;
  return Object.fromEntries(Object.keys(values).map((key) => [key, row[key] ?? values[key]]));
}

function TextField({ control, name, label, description, ...inputProps }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl><Input {...inputProps} {...field} value={field.value ?? ""} /></FormControl>{description && <FormDescription>{description}</FormDescription>}<FormMessage /></FormItem>} />;
}

function TextAreaField({ control, name, label }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl><Textarea {...field} value={field.value ?? ""} rows={4} /></FormControl><FormMessage /></FormItem>} />;
}

function SelectField({ control, name, label, options = [] }) {
  const resolved = options;
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><Select value={field.value || ""} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue placeholder={`Choose ${label.toLowerCase()}`} /></SelectTrigger></FormControl><SelectContent>{resolved.map(([value, text]) => <SelectItem key={value} value={value}>{text}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />;
}

function AcademicSelectField({ control, name, label, resource, selectedItem, enabled = true }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl><AcademicResourceCombobox resource={resource} value={field.value || ""} selectedItem={selectedItem} onValueChange={field.onChange} filters={{ active: true }} enabled={enabled} placeholder={`Choose ${label.toLowerCase()}`} /></FormControl><FormMessage /></FormItem>} />;
}

function BooleanField({ control, name, label, description }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem className="flex items-start gap-3 rounded-xl border p-4"><FormControl><Checkbox checked={Boolean(field.value)} onCheckedChange={field.onChange} /></FormControl><div><FormLabel>{label}</FormLabel>{description && <FormDescription>{description}</FormDescription>}<FormMessage /></div></FormItem>} />;
}

function emptyDescription(resource) {
  return {
    departments: "Create the first department to begin the institution hierarchy.",
    programs: "Add a program after creating its department.",
    cohorts: "Create graduation batches and sections before admitting students.",
    terms: "Terms are optional until attendance or academic evidence needs a teaching period.",
    courses: "Courses are optional until attendance and assessments use offerings.",
    offerings: "Connect a course, academic term, and batch when teaching evidence is required.",
  }[resource];
}

function sentence(value = "") { return String(value).replaceAll("_", " ").replace(/^./, (match) => match.toUpperCase()); }
function shortDate(value) { return value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "Not set"; }
