import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowClockwise, ArrowDown, ArrowRight, CheckCircle, CloudArrowDown, CloudArrowUp,
  Code, Database, FileCsv, FileXls, MagnifyingGlass, PencilSimple, WarningCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import {
  CursorListFooter, EmptyState, ErrorState, SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCancelDataExchangeRunMutation, useCommitDataExchangeRunMutation,
  useCreateDataExchangeExportMutation, useCreateDataExchangeImportMutation,
  useCreateDataExchangeTemplateMutation, useDownloadDataExchangeArtifactMutation,
  useGetCollegeExamCyclesPageQuery, useGetDataExchangeResourceSchemaQuery,
  useGetDataExchangeResourcesQuery, useGetDataExchangeRunQuery, useGetDataExchangeRunRowsQuery,
  useGetDataExchangeRunsQuery,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";

const METHOD_META = {
  manual: { label: "Manual entry", icon: PencilSimple },
  excel: { label: "Excel", icon: FileXls },
  csv: { label: "CSV", icon: FileCsv },
  erp_pull: { label: "ERP pull", icon: CloudArrowDown },
  api_push: { label: "API push", icon: CloudArrowUp },
};

const CATEGORY_ORDER = ["Structure", "Students", "Attendance & results", "Assessments", "Placement data", "Exports"];
const ACADEMIC_SCOPE_KEYS = ["academic_year_id", "term_id", "department_id", "program_id", "cohort_id"];

function displayCategory(category) {
  if (category === "Academic structure") return "Structure";
  if (category === "Academic evidence") return "Attendance & results";
  if (["Student enrichment", "Placements", "Restricted"].includes(category)) return "Placement data";
  return category;
}

export default function DataExchangePanel() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const resourcesQuery = useGetDataExchangeResourcesQuery();
  const resources = resourcesQuery.data?.items || [];
  const view = params.get("exchange_view") === "history" ? "history" : "exchange";
  const resourceKey = params.get("resource") || "";
  const selected = resources.find((item) => item.key === resourceKey) || resources[0] || null;
  const [resourceSearch, setResourceSearch] = useState("");
  const deferredSearch = useDeferredValue(resourceSearch.trim().toLowerCase());
  const [cycleId, setCycleId] = useState("");
  const [activeRun, setActiveRun] = useState(null);
  const academicScope = Object.fromEntries(ACADEMIC_SCOPE_KEYS.flatMap((key) => {
    const value = params.get(key);
    return value ? [[key, value]] : [];
  }));
  const [historyMode, setHistoryMode] = useState("all");
  const historyKey = `data-exchange:${historyMode}`;
  const paging = useCursorPagination(historyKey);
  const runsQuery = useGetDataExchangeRunsQuery({ operation: historyMode, cursor: paging.cursor || undefined, limit: 25 }, { skip: !resources.length || view !== "history" });
  const { accept } = paging;
  useEffect(() => { accept(runsQuery.data); }, [accept, runsQuery.data]);
  useEffect(() => {
    if (resourceKey || !resources.length) return;
    const next = new URLSearchParams(params);
    next.set("resource", resources[0].key);
    setParams(next, { replace: true });
  }, [params, resourceKey, resources, setParams]);
  useEffect(() => { setCycleId(""); setActiveRun(null); }, [resourceKey]);

  const categories = useMemo(() => CATEGORY_ORDER.filter((category) => resources.some((item) => displayCategory(item.category) === category)), [resources]);
  const requestedCategory = params.get("category");
  const category = categories.includes(requestedCategory)
    ? requestedCategory
    : selected ? displayCategory(selected.category) : categories[0];
  const visibleResources = useMemo(() => resources.filter((item) => (
    displayCategory(item.category) === category
      && (!deferredSearch || `${item.label} ${item.description || ""}`.toLowerCase().includes(deferredSearch))
  )), [category, deferredSearch, resources]);

  const updateParams = (changes) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => {
      if (value) next.set(key, value); else next.delete(key);
    });
    setParams(next, { replace: true });
  };
  const chooseCategory = (nextCategory) => {
    const first = resources.find((item) => displayCategory(item.category) === nextCategory);
    setResourceSearch("");
    updateParams({ category: nextCategory, resource: first?.key || "" });
  };
  const chooseResource = (key) => {
    const resource = resources.find((item) => item.key === key);
    updateParams({ resource: key, category: resource ? displayCategory(resource.category) : category });
  };
  const chooseView = (nextView) => {
    updateParams({ exchange_view: nextView === "history" ? "history" : "" });
    setActiveRun(null);
  };

  if (resourcesQuery.isLoading && !resources.length) return <DataExchangeSkeleton />;
  if (resourcesQuery.isError && !resources.length) {
    const detail = resourcesQuery.error?.data?.detail;
    return <ErrorState
      title={resourcesQuery.error?.status === 404 ? "Data Exchange is not enabled" : "Data Exchange could not be loaded"}
      description={detail || "Retry before importing or exporting College data."}
      retry={resourcesQuery.refetch}
    />;
  }

  const selectedVisible = selected && displayCategory(selected.category) === category
    && (!deferredSearch || visibleResources.some((item) => item.key === selected.key));

  return <Surface className="overflow-hidden">
    <div className="flex flex-col gap-4 border-b p-4 sm:p-5 lg:flex-row lg:items-end lg:justify-between">
      <div><div className="overline">Schema driven</div><h2 className="mt-1 font-display text-2xl font-semibold">Data Exchange</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">Use institution-aware templates and schemas, preview every change, and commit only validated rows.</p></div>
      <SegmentControl value={view} onChange={chooseView} items={[{ value: "exchange", label: "Exchange" }, { value: "history", label: "Run history" }]} />
    </div>
    {view === "exchange" ? <>
      <div className="premium-scrollbar overflow-x-auto border-b p-2"><SegmentControl className="w-max min-w-full border-0 shadow-none" value={category} onChange={chooseCategory} items={categories.map((value) => ({ value, label: value }))} /></div>
      <div className="border-b bg-surface-subtle/25 p-4 sm:p-5">
        <div className="grid gap-3 lg:grid-cols-[minmax(16rem,.8fr)_minmax(18rem,1.2fr)]">
          <div className="relative"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={resourceSearch} onChange={(event) => setResourceSearch(event.target.value)} className="pl-10" placeholder={`Search ${String(category || "resources").toLowerCase()}`} aria-label="Search Data Exchange resources" /></div>
          <Select value={visibleResources.some((item) => item.key === selected?.key) ? selected.key : ""} onValueChange={chooseResource}><SelectTrigger aria-label="Data resource"><SelectValue placeholder={visibleResources.length ? "Choose a data resource" : "No matching resources"} /></SelectTrigger><SelectContent>{visibleResources.map((item) => <SelectItem key={item.key} value={item.key}>{item.label}</SelectItem>)}</SelectContent></Select>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Only resources and methods permitted by your College access policy are shown.</p>
      </div>
      <div className="min-w-0 p-4 sm:p-5 lg:p-6">
        {selectedVisible ? <ResourceWorkspace resource={selected} academicScope={academicScope} cycleId={cycleId} onCycleChange={setCycleId} activeRun={activeRun} onRunChange={setActiveRun} onOpenManual={() => openManual(selected.key, navigate, academicScope)} onOpenErp={() => navigate(withAcademicScope("integrations", academicScope))} /> : <EmptyState variant="section" alignment="left" icon={Database} title="Choose a data resource" description="Select a permitted resource to open its live schema, templates, imports, and exports." />}
      </div>
    </> : <div className="min-w-0">
      <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5"><div><h3 className="font-semibold">Run history</h3><p className="mt-1 text-xs text-muted-foreground">Templates, previews, commits, and exports remain auditable.</p></div><SegmentControl value={historyMode} onChange={setHistoryMode} items={[{ value: "all", label: "All" }, { value: "import", label: "Imports" }, { value: "export", label: "Exports" }]} /></div>
      {activeRun && <div className="border-b p-4 sm:p-5"><RunPreview key={activeRun.id} run={activeRun} onRunChange={setActiveRun} /></div>}
      <div className="divide-y">{paging.items.map((run) => <RunRow key={run.id} run={run} onOpen={() => setActiveRun(run)} />)}{!runsQuery.isLoading && !paging.items.length && <EmptyState className="m-4" variant="inline" alignment="left" icon={Database} title="No exchange runs yet" description="Downloaded templates and reviewed uploads will appear here." />}</div>
      <CursorListFooter count={paging.items.length} noun="runs" hasMore={Boolean(runsQuery.data?.next_cursor)} loading={runsQuery.isFetching} error={runsQuery.isError && paging.items.length > 0} onLoadMore={() => paging.loadMore(runsQuery.data?.next_cursor)} onRetry={runsQuery.refetch} />
    </div>}
  </Surface>;
}

function ResourceWorkspace({ resource, academicScope, cycleId, onCycleChange, activeRun, onRunChange, onOpenManual, onOpenErp }) {
  const needsCycle = resource.key === "assessment_marks";
  const [cohortIds, setCohortIds] = useState([]);
  const scopedCohortIds = cohortIds.length
    ? cohortIds
    : academicScope.cohort_id
      ? [academicScope.cohort_id]
      : [];
  const cycles = useGetCollegeExamCyclesPageQuery({ termId: academicScope.term_id, limit: 100 }, { skip: !needsCycle });
  const scopeReady = !needsCycle || Boolean(cycleId);
  const schema = useGetDataExchangeResourceSchemaQuery({ resourceKey: resource.key, cycleId }, { skip: !scopeReady });
  useEffect(() => { setCohortIds([]); }, [cycleId, resource.key]);
  return <div className="space-y-5">
    <div>
      <div className="flex flex-wrap items-center gap-2"><h3 className="font-display text-2xl font-semibold">{resource.label}</h3>{!resource.importable && <StatusBadge status="managed" label="Export only" />}</div>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">{resource.description || defaultDescription(resource)}</p>
      <div className="mt-3 flex flex-wrap gap-2">{resource.methods.map((method) => <MethodChip key={method} method={method} />)}</div>
    </div>

    {needsCycle && <div className="rounded-2xl border bg-surface-subtle/35 p-4">
      <Label htmlFor="exchange-cycle">Exam or assessment cycle</Label>
      <Select value={cycleId} onValueChange={onCycleChange}><SelectTrigger id="exchange-cycle" className="mt-2 max-w-xl"><SelectValue placeholder="Choose the cycle that defines the workbook columns" /></SelectTrigger><SelectContent>{(cycles.data?.items || []).map((cycle) => <SelectItem key={cycle.id} value={cycle.id}>{cycle.name} / {cycle.code}</SelectItem>)}</SelectContent></Select>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">The selected cycle locks the pattern revision, component names, value types, maximums, and calculation rules used by every entry method.</p>
      {schema.data?.effective_configuration?.available_cohorts?.length > 1 && <CohortScopePicker
        cohorts={schema.data.effective_configuration.available_cohorts}
        value={cohortIds}
        onChange={setCohortIds}
      />}
    </div>}

    {!scopeReady ? <EmptyState variant="section" alignment="left" icon={FileXls} title="Select a cycle to continue" description="Marks templates cannot be guessed. Choose the cycle whose frozen assessment pattern should define the columns." />
      : schema.isError ? <ErrorState title="The live schema could not be generated" description={schema.error?.data?.detail || "Check the selected scope and try again."} retry={schema.refetch} />
        : <>
          <ExchangeActions resource={resource} scope={{ ...academicScope, ...(cycleId ? { cycle_id: cycleId } : {}), ...(scopedCohortIds.length ? { cohort_ids: scopedCohortIds } : {}) }} schema={schema.data} onRunChange={onRunChange} onOpenManual={onOpenManual} onOpenErp={onOpenErp} />
          {schema.data && <SchemaSummary schema={schema.data} />}
        </>}

    {activeRun && <RunPreview key={activeRun.id} run={activeRun} onRunChange={onRunChange} />}
  </div>;
}

function CohortScopePicker({ cohorts, value, onChange }) {
  const selected = new Set(value);
  const toggle = (id) => onChange(selected.has(id) ? value.filter((item) => item !== id) : [...value, id]);
  return <div className="mt-4 border-t pt-4">
    <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between"><div><div className="text-sm font-medium">Workbook scope</div><p className="mt-0.5 text-xs text-muted-foreground">Leave all unselected for the full cycle, or combine any sections and cohorts.</p></div>{value.length > 0 && <Button size="sm" variant="ghost" onClick={() => onChange([])}>Use full cycle</Button>}</div>
    <div className="mt-3 flex max-h-36 flex-wrap gap-2 overflow-auto">{cohorts.map((cohort) => <button
      key={cohort.id}
      type="button"
      aria-pressed={selected.has(cohort.id)}
      onClick={() => toggle(cohort.id)}
      className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${selected.has(cohort.id) ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-surface-hover"}`}
    >{cohort.program_code} / {cohort.graduation_year} / {cohort.section || cohort.code}</button>)}</div>
  </div>;
}

function ExchangeActions({ resource, scope, schema, onRunChange, onOpenManual, onOpenErp }) {
  const [template, templateState] = useCreateDataExchangeTemplateMutation();
  const [createImport, importState] = useCreateDataExchangeImportMutation();
  const [createExport, exportState] = useCreateDataExchangeExportMutation();
  const [download, downloadState] = useDownloadDataExchangeArtifactMutation();
  const [file, setFile] = useState(null);
  const inputRef = useRef(null);
  const [mode, setMode] = useState("create");
  const [format, setFormat] = useState(resource.methods.includes("excel") ? "xlsx" : "csv");
  useEffect(() => {
    setFile(null);
    setMode("create");
    setFormat(resource.methods.includes("excel") ? "xlsx" : "csv");
    if (inputRef.current) inputRef.current.value = "";
  }, [resource.key, resource.methods]);

  const downloadRunArtifact = async (run, kind, extension) => {
    try {
      const blob = await download({ runId: run.id, kind }).unwrap();
      saveBlob(blob, `${resource.key}-${run.operation}.${extension}`);
    } catch (error) { toast.error(error?.data?.detail || "The file could not be downloaded"); }
  };
  const generateTemplate = async () => {
    try {
      const run = await template({ resource_key: resource.key, format, mode, scope }).unwrap();
      onRunChange(run);
      await downloadRunArtifact(run, "template", format === "xlsx" ? "xlsx" : resource.key === "academic_structure" ? "zip" : "csv");
      toast.success(mode === "update" ? "Prefilled update template downloaded" : "Blank create template downloaded");
    } catch (error) { toast.error(error?.data?.detail || "Template could not be generated"); }
  };
  const upload = async () => {
    if (!file) return;
    try {
      const run = await createImport({ file, resourceKey: resource.key, scope, idempotencyKey: crypto.randomUUID() }).unwrap();
      onRunChange(run);
      toast.success(run.status === "queued" ? "Large file queued for validation" : "Preview is ready for review");
    } catch (error) { toast.error(error?.data?.detail || "File could not be validated"); }
  };
  const exportRecords = async () => {
    try {
      const run = await createExport({ resource_key: resource.key, format, selection: "filtered", selected_ids: [], scope }).unwrap();
      onRunChange(run);
      if (run.status === "queued") {
        toast.success("Large export queued. It will be available in this run when ready.");
      } else {
        await downloadRunArtifact(run, "export", format);
        toast.success("Authorized records exported");
      }
    } catch (error) { toast.error(error?.data?.detail || "Export could not be generated"); }
  };
  const supportsFiles = resource.methods.includes("excel") || resource.methods.includes("csv");
  const selectedFormatSupported = format === "xlsx" ? resource.methods.includes("excel") : resource.methods.includes("csv");

  return <div className="grid items-start gap-4 xl:grid-cols-2">
    {resource.importable && supportsFiles && <Surface className="overflow-hidden border shadow-none">
      <div className="border-b p-4"><h4 className="font-semibold">Template and upload</h4><p className="mt-1 text-xs text-muted-foreground">Use the current college structure and selected assessment definition.</p></div>
      <div className="space-y-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Select value={format} onValueChange={setFormat}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{resource.methods.includes("excel") && <SelectItem value="xlsx">Excel workbook</SelectItem>}{resource.methods.includes("csv") && <SelectItem value="csv">CSV file</SelectItem>}</SelectContent></Select>
          <Select value={mode} onValueChange={setMode}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="create">Blank create template</SelectItem>{resource.update_supported && <SelectItem value="update">Prefilled update template</SelectItem>}</SelectContent></Select>
        </div>
        <Button variant="outline" className="w-full" onClick={generateTemplate} disabled={!selectedFormatSupported} loading={templateState.isLoading || downloadState.isLoading} loadingText="Preparing file..."><ArrowDown className="mr-2" />Download template</Button>
        <div className="border-t pt-4">
          <Label htmlFor="exchange-upload">Completed template</Label>
          <Input ref={inputRef} id="exchange-upload" className="mt-2" type="file" accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <Button className="mt-3 w-full" onClick={upload} disabled={!file} loading={importState.isLoading} loadingText="Validating file..."><CloudArrowUp className="mr-2" />Upload and preview</Button>
        </div>
      </div>
    </Surface>}
    <Surface className="overflow-hidden border shadow-none">
      <div className="border-b p-4"><h4 className="font-semibold">Other entry paths</h4><p className="mt-1 text-xs text-muted-foreground">Only methods supported by this resource are shown.</p></div>
      <div className="divide-y">
        {resource.methods.includes("manual") && <ActionRow icon={PencilSimple} title="Manual entry" detail="Open the paged form or register using the same validation rules." action="Open" onClick={onOpenManual} />}
        {resource.methods.includes("erp_pull") && <ActionRow icon={CloudArrowDown} title="ERP pull" detail="Map the college ERP response into this live resource schema." action="Configure" onClick={onOpenErp} />}
        {resource.methods.includes("api_push") && <ActionRow icon={Code} title="API push" detail="Use an organization-scoped credential and idempotent batch payload." action="Open guide" onClick={() => window.open("/docs/erp-push", "_blank", "noopener,noreferrer")} />}
        {resource.exportable && <ActionRow icon={CloudArrowDown} title="Export authorized records" detail="Download records visible to your role and current resource scope." action="Export" loading={exportState.isLoading || downloadState.isLoading} onClick={exportRecords} />}
        {!resource.methods.length && !resource.exportable && <div className="p-4 text-sm text-muted-foreground">No exchange method is available for this role.</div>}
      </div>
    </Surface>
  </div>;
}

function SchemaSummary({ schema }) {
  const fields = schema.fields || [];
  return <Surface className="overflow-hidden border shadow-none">
    <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between"><div><h4 className="font-semibold">Live schema</h4><p className="mt-1 text-xs text-muted-foreground">{fields.length} fields / {schema.clear_sentinel} explicitly clears permitted optional values.</p></div>{schema.effective_configuration && <StatusBadge status="active" label={`${schema.effective_configuration.scheme_code} / revision ${schema.effective_configuration.scheme_version}`} />}</div>
    <div className="grid gap-px bg-border sm:grid-cols-2 xl:grid-cols-3">{fields.map((field) => <div key={field.key} className="bg-card p-3"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="truncate text-sm font-medium">{field.label}</div><code className="mt-1 block truncate text-[10px] text-muted-foreground">{field.key}</code></div><span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[10px]">{field.type}</span></div><div className="mt-2 text-[11px] text-muted-foreground">{field.required ? "Required" : "Optional"}{field.writable === false ? " / reference only" : ""}{field.description ? ` / ${field.description}` : ""}</div></div>)}</div>
  </Surface>;
}

function RunPreview({ run, onRunChange }) {
  const processing = ["queued", "validating", "exporting"].includes(run.status);
  const runQuery = useGetDataExchangeRunQuery(run.id, { pollingInterval: processing ? 2000 : 0 });
  const liveRun = runQuery.data || run;
  useEffect(() => {
    if (runQuery.data && runQuery.data.status !== run.status) onRunChange(runQuery.data);
  }, [onRunChange, run.status, runQuery.data]);
  const rowsQuery = useGetDataExchangeRunRowsQuery(
    { runId: run.id, status: "all", limit: 50 },
    { skip: !["ready", "invalid", "committed"].includes(liveRun.status) },
  );
  const current = rowsQuery.data?.run || liveRun;
  const [reason, setReason] = useState("");
  const [commit, commitState] = useCommitDataExchangeRunMutation();
  const [cancel, cancelState] = useCancelDataExchangeRunMutation();
  const [download, downloadState] = useDownloadDataExchangeArtifactMutation();
  const commitRun = async () => {
    try {
      const updated = await commit({ runId: current.id, correctionReason: reason }).unwrap();
      onRunChange(updated);
      toast.success(`${updated.committed_count} validated rows committed`);
    } catch (error) { toast.error(error?.data?.detail || "Validated rows could not be committed"); }
  };
  const cancelRun = async () => {
    try { onRunChange(await cancel(current.id).unwrap()); toast.success("Exchange run cancelled"); }
    catch (error) { toast.error(error?.data?.detail || "Run could not be cancelled"); }
  };
  const downloadCorrections = async () => {
    try { saveBlob(await download({ runId: current.id, kind: "corrections" }).unwrap(), `${current.resource_key}-corrections.xlsx`); }
    catch (error) { toast.error(error?.data?.detail || "Correction workbook could not be downloaded"); }
  };
  const downloadExport = async () => {
    try { saveBlob(await download({ runId: current.id, kind: "export" }).unwrap(), `${current.resource_key}-export.${current.file_format || "xlsx"}`); }
    catch (error) { toast.error(error?.data?.detail || "Export could not be downloaded"); }
  };
  const rows = rowsQuery.data?.items || [];
  return <Surface className="overflow-hidden border shadow-none">
    <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h4 className="font-semibold">Review run</h4><StatusBadge status={current.status} /></div><p className="mt-1 text-xs text-muted-foreground">{current.source_filename || sentence(current.operation)} / created {dateTime(current.created_at)}</p></div>{["queued", "validating", "exporting"].includes(current.status) && <Button size="sm" variant="outline" onClick={() => runQuery.refetch()} loading={runQuery.isFetching} loadingText="Checking..."><ArrowClockwise className="mr-1.5" />Refresh</Button>}</div>
    <div className="grid gap-px bg-border sm:grid-cols-3 lg:grid-cols-6">{[
      ["Rows", current.row_count], ["Creates", current.create_count], ["Updates", current.update_count],
      ["Unchanged", current.unchanged_count], ["Invalid", current.invalid_count], ["Conflicts", current.conflict_count],
    ].map(([label, value]) => <div key={label} className="bg-card p-3"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div><div className="mt-1 text-xl font-semibold">{value || 0}</div></div>)}</div>
    {rows.length > 0 && <div className="max-h-80 divide-y overflow-auto">{rows.slice(0, 50).map((row) => <div key={row.id} className="flex items-start gap-3 p-3"><span className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full ${row.status === "valid" || row.status === "committed" ? "bg-positive/10 text-positive" : "bg-destructive/10 text-destructive"}`}>{row.status === "valid" || row.status === "committed" ? <CheckCircle /> : <WarningCircle />}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap gap-2 text-sm"><strong>Row {row.row_number}</strong><span className="text-muted-foreground">{sentence(row.action)}</span></div>{row.errors?.length > 0 && <p className="mt-1 text-xs leading-5 text-destructive">{row.errors.join("; ")}</p>}{row.warnings?.length > 0 && <p className="mt-1 text-xs leading-5 text-warning-foreground">{row.warnings.join("; ")}</p>}</div></div>)}</div>}
    {current.invalid_count > 0 && <div className="border-t bg-warning-soft p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><div className="font-medium">{current.invalid_count} row(s) need correction</div><p className="mt-1 text-xs text-muted-foreground">Valid rows remain staged. Fix the workbook and upload it as a new reviewed run.</p></div><Button variant="outline" onClick={downloadCorrections} loading={downloadState.isLoading} loadingText="Downloading...">Download corrections</Button></div></div>}
    {current.operation === "export" && current.status === "completed" && <div className="flex flex-col gap-3 border-t bg-positive/5 p-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="font-medium">Export is ready</div><p className="mt-1 text-xs text-muted-foreground">The file contains {current.row_count || 0} authorized rows from the requested scope.</p></div><Button onClick={downloadExport} loading={downloadState.isLoading} loadingText="Downloading..."><ArrowDown className="mr-2" />Download export</Button></div>}
    {current.status === "ready" && <div className="space-y-3 border-t p-4">
      {current.resource_key === "assessment_marks" && <div><Label htmlFor="correction-reason">Published-mark correction reason (when applicable)</Label><Textarea id="correction-reason" value={reason} onChange={(event) => setReason(event.target.value)} className="mt-2" rows={2} placeholder="Required only when this upload changes published results" /></div>}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><Button variant="ghost" onClick={cancelRun} loading={cancelState.isLoading} loadingText="Cancelling...">Cancel run</Button><Button onClick={commitRun} disabled={!current.valid_count} loading={commitState.isLoading} loadingText="Committing...">Commit {current.valid_count} valid row{current.valid_count === 1 ? "" : "s"}</Button></div>
    </div>}
  </Surface>;
}

function MethodChip({ method }) {
  const meta = METHOD_META[method] || { label: sentence(method), icon: Database };
  const Icon = meta.icon;
  return <span className="inline-flex items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 text-xs text-muted-foreground"><Icon />{meta.label}</span>;
}

function ActionRow({ icon: Icon, title, detail, action, onClick, loading }) {
  return <div className="flex items-start gap-3 p-4"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary"><Icon /></span><div className="min-w-0 flex-1"><div className="font-medium">{title}</div><p className="mt-0.5 text-xs leading-5 text-muted-foreground">{detail}</p></div><Button size="sm" variant="ghost" onClick={onClick} loading={loading} loadingText="Working...">{action}<ArrowRight className="ml-1.5" /></Button></div>;
}

function RunRow({ run, onOpen }) {
  return <button type="button" onClick={onOpen} className="flex w-full flex-col gap-3 p-4 text-left transition-colors hover:bg-surface-hover sm:flex-row sm:items-center sm:p-5"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary"><Database /></span><span className="min-w-0 flex-1"><span className="block font-medium">{sentence(run.resource_key)} / {sentence(run.operation)}</span><span className="mt-1 block text-xs text-muted-foreground">{run.row_count || 0} rows / {dateTime(run.created_at)}</span></span><StatusBadge status={run.status} /><ArrowRight className="shrink-0 text-muted-foreground" /></button>;
}

function DataExchangeSkeleton() {
  return <Surface className="overflow-hidden"><div className="h-28 animate-pulse border-b bg-surface-subtle" /><div className="h-14 animate-pulse border-b bg-surface-subtle/60" /><div className="space-y-4 p-5"><div className="h-11 animate-pulse rounded-xl bg-secondary" /><div className="h-64 animate-pulse rounded-2xl bg-secondary" /></div></Surface>;
}

function withAcademicScope(section, scope, extra = {}) {
  const params = new URLSearchParams({ ...scope, ...extra });
  if (section !== "overview") params.set("section", section);
  return `/app/academics${params.toString() ? `?${params}` : ""}`;
}

function openManual(resourceKey, navigate, scope) {
  if (["academic_structure", "departments", "programs", "cohorts", "terms", "courses", "offerings"].includes(resourceKey)) navigate(withAcademicScope("structure", scope));
  else if (resourceKey === "assessment_schemes") navigate(withAcademicScope("assessments", scope, { view: "patterns" }));
  else if (["assessment_marks", "exam_cycles"].includes(resourceKey)) navigate(withAcademicScope("assessments", scope));
  else if (resourceKey === "term_results") navigate(withAcademicScope("results", scope));
  else if (resourceKey === "attendance") navigate(withAcademicScope("attendance", scope));
  else if (resourceKey === "students") navigate("/app/clients?new=1");
  else if (["companies", "drives", "applications"].includes(resourceKey)) navigate(`/app/college?section=${resourceKey === "drives" ? "drives" : resourceKey}`);
}

function defaultDescription(resource) {
  return resource.importable ? "Create, update, and export this resource through validated institution-aware schemas." : "Download an authorized snapshot for review or reporting.";
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function sentence(value = "") { return String(value).replaceAll("_", " ").replace(/^./, (match) => match.toUpperCase()); }
function dateTime(value) { return value ? new Date(value).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }) : "Not available"; }
