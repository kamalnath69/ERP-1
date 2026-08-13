import React, { useDeferredValue, useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import {
  ArrowRight, Calculator, CheckCircle, Copy, Plus, SlidersHorizontal, Target, Trash,
} from "@phosphor-icons/react";
import { z } from "zod";
import { toast } from "sonner";

import AcademicResourceCombobox from "@/components/college/AcademicResourceCombobox";
import {
  CursorListFooter, DrawerForm, EmptyState, ErrorState, StatusBadge, Surface,
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
  useAssignCollegeAssessmentSchemeMutation, useCreateCollegeAssessmentSchemeMutation,
  useCreateCollegeAssessmentSchemeVersionMutation, useGetCollegeAssessmentReadinessMappingsQuery,
  useGetCollegeAssessmentSchemesPageQuery, useSaveCollegeAssessmentReadinessMappingMutation,
  useUpdateCollegeAssessmentSchemeMutation,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import { applyApiErrors, FORM_OPTIONS } from "@/lib/validation";

const optionalNumber = (minimum = 0) => z.preprocess(
  (value) => value === "" || value == null ? undefined : Number(value),
  z.number().finite().min(minimum).optional(),
);

const componentSchema = z.object({
  name: z.string().trim().min(2, "Enter a component name").max(140),
  code: z.string().trim().max(50).optional(),
  component_type: z.string().trim().min(2).max(50),
  metric_type: z.enum(["number", "percentage", "integer", "boolean", "short_text", "grade", "rank", "count"]),
  max_marks: optionalNumber(0.01),
  weightage_percent: optionalNumber(0),
  pass_marks: optionalNumber(0),
  is_required: z.boolean(),
}).superRefine((value, context) => {
  if (value.max_marks != null && value.pass_marks != null && value.pass_marks > value.max_marks) {
    context.addIssue({ code: "custom", path: ["pass_marks"], message: "Pass mark cannot exceed the maximum" });
  }
  if ((value.weightage_percent || 0) > 100) {
    context.addIssue({ code: "custom", path: ["weightage_percent"], message: "Weightage cannot exceed 100%" });
  }
});

const schemeSchema = z.object({
  name: z.string().trim().min(2, "Enter a pattern name").max(180),
  code: z.string().trim().min(2, "Enter a pattern code").max(50),
  domain: z.enum(["academic", "coding", "placement"]),
  description: z.string().trim().max(2000).optional(),
  final_score_max: z.preprocess((value) => Number(value), z.number().finite().positive().max(1000000)),
  calculation_method: z.enum(["weighted_sum", "average", "best_n"]),
  best_n: optionalNumber(1),
  minimum_components: optionalNumber(0),
  activate: z.boolean(),
  components: z.array(componentSchema).min(1, "Add at least one component").max(100),
}).superRefine((value, context) => {
  const numeric = value.components.filter((item) => !["boolean", "short_text", "grade"].includes(item.metric_type));
  if (!numeric.length) context.addIssue({ code: "custom", path: ["components"], message: "Add at least one numeric component" });
  if (value.calculation_method === "weighted_sum" && !numeric.some((item) => Number(item.weightage_percent || 0) > 0)) {
    context.addIssue({ code: "custom", path: ["components"], message: "Set a positive weightage on at least one numeric component" });
  }
  if (value.calculation_method === "best_n" && (!value.best_n || value.best_n > numeric.length)) {
    context.addIssue({ code: "custom", path: ["best_n"], message: `Choose between 1 and ${Math.max(numeric.length, 1)}` });
  }
  if ((value.minimum_components || 0) > numeric.length) {
    context.addIssue({ code: "custom", path: ["minimum_components"], message: "Cannot exceed the numeric component count" });
  }
});

const assignmentSchema = z.object({
  level: z.enum(["institution", "program", "cohort"]),
  program_id: z.string().optional(),
  cohort_id: z.string().optional(),
  term_id: z.string().optional(),
}).superRefine((value, context) => {
  if (value.level === "program" && !value.program_id) context.addIssue({ code: "custom", path: ["program_id"], message: "Select a program" });
  if (value.level === "cohort" && !value.cohort_id) context.addIssue({ code: "custom", path: ["cohort_id"], message: "Select a batch" });
});

const blankComponent = () => ({
  name: "", code: "", component_type: "assessment", metric_type: "number",
  max_marks: "", weightage_percent: "", pass_marks: "", is_required: true,
});

export default function AssessmentPatternsPanel() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [domain, setDomain] = useState("all");
  const [editorOpen, setEditorOpen] = useState(false);
  const [assignmentTarget, setAssignmentTarget] = useState(null);
  const [mappingTarget, setMappingTarget] = useState(null);
  const filterKey = `${deferredSearch}:${domain}`;
  const paging = useCursorPagination(filterKey);
  const query = useGetCollegeAssessmentSchemesPageQuery({
    q: deferredSearch || undefined,
    domain,
    cursor: paging.cursor || undefined,
    limit: 25,
  });
  const { accept } = paging;
  useEffect(() => { accept(query.data); }, [accept, query.data]);

  if (query.isError && !paging.items.length) {
    return <ErrorState title="Assessment patterns could not be loaded" description="Retry before configuring exams or mark templates." retry={query.refetch} />;
  }

  return <div className="space-y-5">
    <Surface className="overflow-hidden">
      <div className="flex flex-col gap-4 border-b p-4 sm:p-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="overline">Institution configured</div>
          <h3 className="mt-1 font-display text-2xl font-semibold">Assessment patterns</h3>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">Define exactly how this college evaluates academics, coding, and placement readiness. Templates and registers follow the selected version automatically.</p>
        </div>
        {can("college.academics.manage") && <Button onClick={() => setEditorOpen(true)}><Plus className="mr-2" />New pattern</Button>}
      </div>
      <div className="grid gap-3 border-b bg-surface-subtle/35 p-3 sm:grid-cols-[minmax(0,1fr)_13rem] sm:p-4">
        <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search pattern name or code" />
        <Select value={domain} onValueChange={setDomain}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>
          <SelectItem value="all">All domains</SelectItem>
          <SelectItem value="academic">Academic</SelectItem>
          <SelectItem value="coding">Coding</SelectItem>
          <SelectItem value="placement">Placement</SelectItem>
        </SelectContent></Select>
      </div>
      <div className="divide-y">
        {paging.items.map((scheme) => <PatternRow
          key={scheme.id}
          scheme={scheme}
          canManage={can("college.academics.manage")}
          canViewReadiness={can("college.readiness.view")}
          onAssign={() => setAssignmentTarget(scheme)}
          onMapReadiness={() => setMappingTarget(scheme)}
        />)}
        {!query.isLoading && !paging.items.length && <EmptyState
          className="m-4"
          variant={deferredSearch || domain !== "all" ? "filtered" : "section"}
          alignment="left"
          icon={SlidersHorizontal}
          title={deferredSearch || domain !== "all" ? "No matching patterns" : "Configure the college's first assessment pattern"}
          description={deferredSearch || domain !== "all" ? "Adjust the search or domain filter." : "Start with the institution default. Program, batch, and term overrides can be added only where the college needs them."}
          primaryAction={can("college.academics.manage") && !deferredSearch && domain === "all" ? <Button onClick={() => setEditorOpen(true)}>Create pattern</Button> : undefined}
        />}
      </div>
      <CursorListFooter
        count={paging.items.length}
        noun="patterns"
        hasMore={Boolean(query.data?.next_cursor)}
        loading={query.isFetching}
        error={query.isError && paging.items.length > 0}
        onLoadMore={() => paging.loadMore(query.data?.next_cursor)}
        onRetry={query.refetch}
      />
    </Surface>
    <PatternEditor open={editorOpen} onOpenChange={setEditorOpen} />
    <AssignmentDrawer scheme={assignmentTarget} onOpenChange={(open) => { if (!open) setAssignmentTarget(null); }} />
    <ReadinessMappingDrawer
      scheme={mappingTarget}
      canManage={can("college.readiness.manage")}
      onOpenChange={(open) => { if (!open) setMappingTarget(null); }}
    />
  </div>;
}

function PatternRow({ scheme, canManage, canViewReadiness, onAssign, onMapReadiness }) {
  const [activate, activateState] = useUpdateCollegeAssessmentSchemeMutation();
  const [cloneVersion, cloneState] = useCreateCollegeAssessmentSchemeVersionMutation();
  const componentSummary = scheme.components.map((item) => item.name).join(", ");
  const makeActive = async () => {
    try {
      await activate({ schemeId: scheme.id, data: { version: scheme.version, activate: true } }).unwrap();
      toast.success("Assessment pattern activated");
    } catch (error) { toast.error(error?.data?.detail || "Pattern could not be activated"); }
  };
  const createVersion = async () => {
    try {
      await cloneVersion({ schemeId: scheme.id, data: { activate: false } }).unwrap();
      toast.success("A new draft version is ready");
    } catch (error) { toast.error(error?.data?.detail || "A new version could not be created"); }
  };
  return <div className="grid gap-4 p-4 sm:p-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="font-semibold">{scheme.name}</h4>
        <StatusBadge status={scheme.status} />
        <span className="rounded-full border px-2 py-0.5 text-[11px] font-medium text-muted-foreground">{sentence(scheme.domain)}</span>
      </div>
      <div className="mt-1 text-xs text-muted-foreground"><code>{scheme.code}</code> / revision {scheme.version_number} / {sentence(scheme.calculation_method)} / final scale {scheme.final_score_max}</div>
      <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{componentSummary || "No components"}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>{scheme.components.length} component{scheme.components.length === 1 ? "" : "s"}</span>
        <span>/</span>
        <span>{scheme.assignments.length ? `${scheme.assignments.length} scope assignment${scheme.assignments.length === 1 ? "" : "s"}` : "Not assigned"}</span>
        {scheme.frozen_at && <><span>/</span><span>Historical version locked</span></>}
      </div>
    </div>
    {canManage && <div className="flex flex-wrap gap-2 xl:justify-end">
      {scheme.status === "draft" && <Button size="sm" variant="outline" onClick={makeActive} loading={activateState.isLoading} loadingText="Activating..."><CheckCircle className="mr-1.5" />Activate</Button>}
      {scheme.status !== "draft" && <Button size="sm" variant="outline" onClick={onAssign}><ArrowRight className="mr-1.5" />Assign scope</Button>}
      {canViewReadiness && <Button size="sm" variant="outline" onClick={onMapReadiness}><Target className="mr-1.5" />Readiness</Button>}
      <Button size="sm" variant="ghost" onClick={createVersion} loading={cloneState.isLoading} loadingText="Creating..."><Copy className="mr-1.5" />New version</Button>
    </div>}
    {!canManage && canViewReadiness && <Button size="sm" variant="outline" onClick={onMapReadiness}><Target className="mr-1.5" />Readiness mapping</Button>}
  </div>;
}

function PatternEditor({ open, onOpenChange }) {
  const form = useForm({
    resolver: zodResolver(schemeSchema),
    defaultValues: {
      name: "", code: "", domain: "academic", description: "", final_score_max: "100",
      calculation_method: "weighted_sum", best_n: "", minimum_components: "", activate: true,
      components: [blankComponent()],
    },
    ...FORM_OPTIONS,
  });
  const { clearErrors, control, formState, handleSubmit, reset, setError, watch } = form;
  const fields = useFieldArray({ control, name: "components" });
  const method = watch("calculation_method");
  const [create, mutation] = useCreateCollegeAssessmentSchemeMutation();
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    const payload = {
      name: values.name,
      code: values.code,
      domain: values.domain,
      description: values.description || null,
      final_score_max: values.final_score_max,
      calculation_method: values.calculation_method,
      calculation_config: {
        ...(values.calculation_method === "best_n" ? { best_n: values.best_n } : {}),
        ...(values.minimum_components ? { minimum_components: values.minimum_components } : {}),
      },
      activate: values.activate,
      components: values.components.map((item, index) => ({
        name: item.name,
        code: item.code || null,
        component_type: item.component_type,
        metric_type: item.metric_type,
        display_order: index + 1,
        max_marks: item.max_marks ?? null,
        weightage_bps: Math.round(Number(item.weightage_percent || 0) * 100),
        pass_marks: item.pass_marks ?? null,
        is_required: item.is_required,
        settings: {},
      })),
    };
    try {
      await create(payload).unwrap();
      toast.success("Assessment pattern created");
      reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Assessment pattern could not be created" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <DrawerForm open={open} onOpenChange={(next) => { if (!next && !mutation.isLoading) onOpenChange(false); }} title="Create assessment pattern" description="Use the college's own terminology. No internal-exam names or counts are imposed by Edvatiq.">
    <Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField control={control} name="name" label="Pattern name" placeholder="Institution terminology" />
        <TextField control={control} name="code" label="Pattern code" placeholder="Unique college code" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField control={control} name="domain" label="Domain" options={[["academic", "Academic"], ["coding", "Coding"], ["placement", "Placement"]]} />
        <SelectField control={control} name="calculation_method" label="Calculation" options={[["weighted_sum", "Weighted sum"], ["average", "Average"], ["best_n", "Best N"]]} />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField control={control} name="final_score_max" label="Final score scale" type="number" min="0.01" step="0.01" />
        {method === "best_n" && <TextField control={control} name="best_n" label="Best components" type="number" min="1" step="1" />}
        <TextField control={control} name="minimum_components" label="Minimum components" type="number" min="0" step="1" />
      </div>
      <FormField control={control} name="description" render={({ field }) => <FormItem><FormLabel>Description</FormLabel><FormControl><Textarea {...field} value={field.value || ""} rows={3} placeholder="Optional policy context" /></FormControl><FormMessage /></FormItem>} />

      <div className="rounded-2xl border">
        <div className="flex items-center justify-between gap-3 border-b p-4">
          <div><h4 className="font-semibold">Components and metrics</h4><p className="mt-1 text-xs text-muted-foreground">Each component becomes a live register, template, ERP field, and report definition.</p></div>
          <Button type="button" size="sm" variant="outline" onClick={() => fields.append(blankComponent())}><Plus className="mr-1.5" />Add</Button>
        </div>
        <div className="divide-y">{fields.fields.map((field, index) => <ComponentFields key={field.id} control={control} index={index} onRemove={() => fields.remove(index)} canRemove={fields.fields.length > 1} />)}</div>
        {formState.errors.components?.root?.message && <p role="alert" className="p-4 text-sm text-destructive">{formState.errors.components.root.message}</p>}
        {typeof formState.errors.components?.message === "string" && <p role="alert" className="p-4 text-sm text-destructive">{formState.errors.components.message}</p>}
      </div>
      <FormField control={control} name="activate" render={({ field }) => <FormItem className="flex items-start gap-3 rounded-xl border p-4"><FormControl><Checkbox checked={field.value} onCheckedChange={field.onChange} /></FormControl><div><FormLabel>Activate after creation</FormLabel><FormDescription>Active patterns can be assigned to institution, program, batch, and term scopes.</FormDescription></div></FormItem>} />
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" className="w-full" disabled={!formState.isValid} loading={formState.isSubmitting || mutation.isLoading} loadingText="Creating pattern...">Create pattern</Button>
    </form></Form>
  </DrawerForm>;
}

function ComponentFields({ control, index, onRemove, canRemove }) {
  return <div className="space-y-4 p-4">
    <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><Calculator /><span className="font-semibold">Component {index + 1}</span></div>{canRemove && <Button type="button" size="icon" variant="ghost" onClick={onRemove} aria-label={`Remove component ${index + 1}`}><Trash /></Button>}</div>
    <div className="grid gap-4 sm:grid-cols-2">
      <TextField control={control} name={`components.${index}.name`} label="Name" />
      <TextField control={control} name={`components.${index}.code`} label="Code" placeholder="Generated from name if blank" />
      <TextField control={control} name={`components.${index}.component_type`} label="Component type" />
      <SelectField control={control} name={`components.${index}.metric_type`} label="Value type" options={[["number", "Number"], ["percentage", "Percentage"], ["integer", "Integer"], ["count", "Count"], ["rank", "Rank"], ["boolean", "Yes / No"], ["grade", "Grade"], ["short_text", "Short text"]]} />
      <TextField control={control} name={`components.${index}.max_marks`} label="Maximum" type="number" min="0" step="0.01" />
      <TextField control={control} name={`components.${index}.weightage_percent`} label="Weightage (%)" type="number" min="0" max="100" step="0.01" />
      <TextField control={control} name={`components.${index}.pass_marks`} label="Pass threshold" type="number" min="0" step="0.01" />
    </div>
    <FormField control={control} name={`components.${index}.is_required`} render={({ field }) => <FormItem className="flex items-center gap-3"><FormControl><Checkbox checked={field.value} onCheckedChange={field.onChange} /></FormControl><FormLabel className="m-0">Required component</FormLabel></FormItem>} />
  </div>;
}

function AssignmentDrawer({ scheme, onOpenChange }) {
  const form = useForm({ resolver: zodResolver(assignmentSchema), defaultValues: { level: "institution", program_id: "", cohort_id: "", term_id: "" }, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, watch } = form;
  const level = watch("level");
  const [assign, mutation] = useAssignCollegeAssessmentSchemeMutation();
  useEffect(() => { if (scheme) reset({ level: "institution", program_id: "", cohort_id: "", term_id: "" }); }, [reset, scheme]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    const data = {
      program_id: values.level === "program" ? values.program_id : null,
      cohort_id: values.level === "cohort" ? values.cohort_id : null,
      term_id: values.level === "institution" ? null : values.term_id || null,
    };
    try {
      await assign({ schemeId: scheme.id, data }).unwrap();
      toast.success("Assessment scope assigned");
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Pattern scope could not be assigned" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <DrawerForm open={Boolean(scheme)} onOpenChange={(open) => { if (!open && !mutation.isLoading) onOpenChange(false); }} title={`Assign ${scheme?.name || "pattern"}`} description="More specific scopes take precedence: batch and term, program and term, batch, program, then institution default.">
    <Form {...form}><form noValidate className="space-y-5" onSubmit={submit}>
      <SelectField control={control} name="level" label="Override level" options={[["institution", "Institution default"], ["program", "Program"], ["cohort", "Graduation batch / section"]]} />
      {level === "program" && <ResourceField control={control} name="program_id" label="Program" resource="programs" />}
      {level === "cohort" && <ResourceField control={control} name="cohort_id" label="Batch and section" resource="cohorts" />}
      {level !== "institution" && <ResourceField control={control} name="term_id" label="Term override (optional)" resource="terms" />}
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" className="w-full" disabled={!formState.isValid} loading={formState.isSubmitting || mutation.isLoading} loadingText="Assigning...">Assign pattern</Button>
    </form></Form>
  </DrawerForm>;
}

function ReadinessMappingDrawer({ scheme, canManage, onOpenChange }) {
  const query = useGetCollegeAssessmentReadinessMappingsQuery(scheme?.id, { skip: !scheme });
  const [saveMapping, mutation] = useSaveCollegeAssessmentReadinessMappingMutation();
  const [drafts, setDrafts] = useState({});
  const [pendingMetric, setPendingMetric] = useState("");
  const numericTypes = new Set(["number", "percentage", "integer", "rank", "count"]);
  const metrics = scheme ? [
    { code: "__CALCULATED__", name: "Calculated pattern score" },
    ...scheme.components.filter((item) => numericTypes.has(item.metric_type)),
  ] : [];

  useEffect(() => {
    if (!scheme || !query.data) return;
    const existing = Object.fromEntries((query.data.items || []).map((item) => [item.metric_code, item]));
    setDrafts(Object.fromEntries(metrics.map((metric) => {
      const row = existing[metric.code];
      return [metric.code, {
        factor_key: row?.factor_key || "assessment",
        is_active: row?.is_active ?? false,
        version: row?.version,
      }];
    })));
  // The scheme identifier and fetched payload are the authoritative reset points.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.data, scheme?.id]);

  const changeDraft = (code, patch) => setDrafts((current) => ({
    ...current,
    [code]: { ...(current[code] || {}), ...patch },
  }));
  const save = async (metric) => {
    const draft = drafts[metric.code] || {};
    setPendingMetric(metric.code);
    try {
      await saveMapping({
        schemeId: scheme.id,
        data: {
          metric_code: metric.code,
          factor_key: draft.factor_key || "assessment",
          is_active: Boolean(draft.is_active),
          version: draft.version || null,
        },
      }).unwrap();
      toast.success(`${metric.name} readiness mapping saved`);
    } catch (error) {
      toast.error(error?.data?.detail || "Readiness mapping could not be saved");
    } finally {
      setPendingMetric("");
    }
  };

  return <DrawerForm
    open={Boolean(scheme)}
    onOpenChange={(open) => { if (!open && !mutation.isLoading) onOpenChange(false); }}
    title={`Readiness evidence for ${scheme?.name || "pattern"}`}
    description="A metric affects readiness only after an authorized mapping is active. Historical source scores remain unchanged."
  >
    {query.isLoading ? <div className="space-y-3">{[1, 2, 3].map((item) => <div key={item} className="h-24 animate-pulse rounded-xl bg-muted" />)}</div> : query.isError ? <ErrorState variant="section" title="Mappings could not be loaded" retry={query.refetch} /> : <div className="space-y-3">
      {metrics.map((metric) => {
        const draft = drafts[metric.code] || { factor_key: "assessment", is_active: false };
        return <div key={metric.code} className="rounded-xl border p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="font-medium">{metric.name}</div>
              <code className="mt-1 block truncate text-xs text-muted-foreground">{metric.code}</code>
            </div>
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox
                checked={Boolean(draft.is_active)}
                disabled={!canManage || mutation.isLoading}
                onCheckedChange={(value) => changeDraft(metric.code, { is_active: Boolean(value) })}
              />
              Use in readiness
            </label>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <Select
              value={draft.factor_key || "assessment"}
              disabled={!canManage || mutation.isLoading}
              onValueChange={(value) => changeDraft(metric.code, { factor_key: value })}
            >
              <SelectTrigger aria-label={`Readiness factor for ${metric.name}`}><SelectValue /></SelectTrigger>
              <SelectContent>
                {["academics", "coding", "assessment", "profile", "attendance", "training"].map((factor) => <SelectItem key={factor} value={factor}>{sentence(factor)}</SelectItem>)}
              </SelectContent>
            </Select>
            {canManage && <Button
              type="button"
              variant="outline"
              onClick={() => save(metric)}
              loading={pendingMetric === metric.code}
              loadingText="Saving..."
              disabled={mutation.isLoading && pendingMetric !== metric.code}
            >Save mapping</Button>}
          </div>
        </div>;
      })}
      {!metrics.length && <EmptyState variant="section" alignment="left" title="No numeric metrics" description="Add a numeric component to a new pattern version before mapping readiness evidence." />}
      {!canManage && <p className="rounded-xl bg-muted/60 p-3 text-sm text-muted-foreground">You can review these mappings. Readiness administration permission is required to change them.</p>}
    </div>}
  </DrawerForm>;
}

function TextField({ control, name, label, ...props }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl><Input {...props} {...field} value={field.value ?? ""} /></FormControl><FormMessage /></FormItem>} />;
}

function SelectField({ control, name, label, options }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><Select value={field.value || ""} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl><SelectContent>{options.map(([value, text]) => <SelectItem key={value} value={value}>{text}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />;
}

function ResourceField({ control, name, label, resource }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl><AcademicResourceCombobox resource={resource} value={field.value || ""} onValueChange={field.onChange} filters={{ active: true }} placeholder={`Choose ${label.toLowerCase()}`} /></FormControl><FormMessage /></FormItem>} />;
}

function sentence(value = "") { return String(value).replaceAll("_", " ").replace(/^./, (match) => match.toUpperCase()); }
