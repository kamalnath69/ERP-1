import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check, CheckCircle, Copy, Lock, MagnifyingGlass, Plus, ShieldCheck, SpinnerGap,
  UserFocus, UsersThree, WarningCircle, X,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { EntityAvatar } from "@/components/entities/EntityProfile";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, PageHeader,
  PageShell, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import {
  useGetAccessAuditQuery, useGetAccessCatalogQuery, useGetAccessDelegationQuery,
  useGetAccessPeoplePageQuery, useGetAccessStudentsPageQuery,
  useLazyGetEnterprisePolicyQuery, usePreviewEnterprisePolicyMutation,
  useCreateGuidedRoleTemplateMutation, useSaveAccessDelegationMutation,
  useSaveEnterprisePolicyMutation,
} from "@/features/access/accessApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import { cn } from "@/lib/utils";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";

const LEVELS = ["none", "view", "work", "manage"];
const LEVEL_RANK = Object.fromEntries(LEVELS.map((level, index) => [level, index]));
const LEVEL_LABELS = { none: "No access", view: "View", work: "Work", manage: "Manage" };
const LEVEL_COPY = {
  none: "This area is not visible.",
  view: "View records and scoped analytics.",
  work: "View and complete routine updates.",
  manage: "Create and configure records within reach.",
};
const DOMAIN_COPY = {
  students: "Student directory and profiles",
  academics: "Departments, programs, batches, terms, and courses",
  attendance: "Attendance sessions and registers",
  assessments: "Exams, marks, and assessment registers",
  readiness: "Readiness evidence and interventions",
  coding: "Coding profiles, snapshots, and skills",
  placements: "Drives, applications, interviews, and offers",
  data: "Imports, ERP sync, and data exchange",
  reports: "Placement outcomes and scoped analytics",
  clearance: "Internship clearance status only",
  documents: "Student-linked documents and resumes",
};
const STEPS = ["Responsibilities", "Maximum reach", "Work areas", "Sensitive access", "Review"];

function blankPolicy(catalog) {
  return {
    role_ids: [],
    maximum_reach: [],
    domain_levels: Object.fromEntries((catalog?.domains || []).map((row) => [row.key, "none"])),
    domain_scope_limits: {},
    sensitive_capabilities: [],
    ai_enabled: false,
    expires_at: "",
    review_note: "",
    version: 1,
  };
}

function fromServer(policy, catalog) {
  const base = blankPolicy(catalog);
  return {
    ...base,
    ...policy,
    domain_levels: { ...base.domain_levels, ...(policy?.domain_levels || {}) },
    domain_scope_limits: policy?.domain_scope_limits || {},
    sensitive_capabilities: policy?.sensitive_capabilities || [],
    expires_at: toLocalInput(policy?.expires_at),
    review_note: policy?.review_note || "",
  };
}

function toPayload(draft) {
  return {
    role_ids: draft.role_ids,
    maximum_reach: draft.maximum_reach,
    domain_levels: draft.domain_levels,
    domain_scope_limits: Object.fromEntries(
      Object.entries(draft.domain_scope_limits || {}).filter(([, roots]) => roots?.length),
    ),
    sensitive_capabilities: draft.sensitive_capabilities,
    ai_enabled: draft.ai_enabled,
    expires_at: draft.expires_at ? new Date(draft.expires_at).toISOString() : null,
    review_note: draft.review_note.trim() || null,
    version: draft.version,
  };
}

function toLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function errorText(error, fallback) {
  const detail = error?.data?.detail;
  if (typeof detail === "string") return detail;
  return error?.data?.error?.message || fallback;
}

export default function CollegeAccessConsole() {
  const navigate = useNavigate();
  const { user: currentUser, can } = useAuth();
  const catalogQuery = useGetAccessCatalogQuery(undefined, QUERY_POLICIES.collaborative);
  const catalog = catalogQuery.data;
  const [tab, setTab] = useState("people");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const peoplePaging = useCursorPagination(JSON.stringify({ q: deferredSearch }));
  const peopleQuery = useGetAccessPeoplePageQuery(
    { q: deferredSearch, cursor: peoplePaging.cursor, limit: 25 },
    QUERY_POLICIES.collaborative,
  );
  const auditPaging = useCursorPagination("college-access-audit");
  const auditQuery = useGetAccessAuditQuery(
    { cursor: auditPaging.cursor, limit: 50 },
    withSkip(QUERY_POLICIES.operational, tab !== "audit"),
  );
  const { accept: acceptPeople } = peoplePaging;
  const { accept: acceptAudit } = auditPaging;
  useEffect(() => { acceptPeople(peopleQuery.data); }, [acceptPeople, peopleQuery.data]);
  useEffect(() => { acceptAudit(auditQuery.data); }, [acceptAudit, auditQuery.data]);

  const [target, setTarget] = useState(null);
  const [draft, setDraft] = useState(null);
  const [step, setStep] = useState(0);
  const [editorError, setEditorError] = useState("");
  const [previewFingerprint, setPreviewFingerprint] = useState("");
  const [loadPolicy, loadPolicyState] = useLazyGetEnterprisePolicyQuery();
  const [previewPolicy, previewState] = usePreviewEnterprisePolicyMutation();
  const [savePolicy, saveState] = useSaveEnterprisePolicyMutation();
  const [delegationTarget, setDelegationTarget] = useState(null);
  const delegationQuery = useGetAccessDelegationQuery(
    delegationTarget?.id,
    withSkip(QUERY_POLICIES.operational, !delegationTarget),
  );
  const [saveDelegation, saveDelegationState] = useSaveAccessDelegationMutation();
  const [templateEditor, setTemplateEditor] = useState(null);
  const [createTemplate, createTemplateState] = useCreateGuidedRoleTemplateMutation();

  if (catalogQuery.isError && !catalog) {
    return <PageShell><ErrorState title="Access policy could not be loaded" description={errorText(catalogQuery.error)} retry={catalogQuery.refetch} /></PageShell>;
  }

  const openEditor = async (person) => {
    setTarget(person); setDraft(null); setStep(0); setEditorError(""); setPreviewFingerprint("");
    previewState.reset();
    try {
      const policy = await loadPolicy(person.id, true).unwrap();
      setDraft(fromServer(policy, catalog));
    } catch (error) {
      toast.error(errorText(error, "Could not load this access policy"));
      setTarget(null);
    }
  };

  const updateDraft = (updater) => {
    setDraft((current) => typeof updater === "function" ? updater(current) : { ...current, ...updater });
    setPreviewFingerprint("");
    previewState.reset();
    setEditorError("");
  };

  const validateStep = () => {
    if (step === 0 && !draft.role_ids.length) return "Choose at least one responsibility template.";
    if (step === 1 && !draft.maximum_reach.length) return "Choose the furthest data reach this person may receive.";
    const selectedRoles = (catalog?.role_templates || []).filter((role) => draft.role_ids.includes(role.id));
    const administrationOnly = selectedRoles.length > 0 && selectedRoles.every((role) => role.slug === "access-admin");
    if (step === 2 && !administrationOnly && !Object.values(draft.domain_levels).some((level) => level !== "none")) return "Enable at least one work area.";
    if (step === 3) {
      if (draft.expires_at && new Date(draft.expires_at) <= new Date()) return "Temporary access must expire in the future.";
      const issues = policyCapabilityIssues(catalog, draft);
      if (issues.length) return issues[0];
    }
    return "";
  };

  const next = () => {
    const error = validateStep();
    if (error) { setEditorError(error); return; }
    setEditorError(""); setStep((value) => Math.min(value + 1, STEPS.length - 1));
  };

  const runPreview = async () => {
    const payload = toPayload(draft);
    const fingerprint = JSON.stringify(payload);
    setEditorError("");
    try {
      await previewPolicy({ userId: target.id, policy: payload }).unwrap();
      setPreviewFingerprint(fingerprint);
    } catch (error) {
      setPreviewFingerprint("");
      setEditorError(errorText(error, "This policy could not be previewed"));
    }
  };

  const save = async () => {
    const payload = toPayload(draft);
    if (previewFingerprint !== JSON.stringify(payload)) {
      setEditorError("Preview the current policy before activating it.");
      return;
    }
    try {
      await savePolicy({ userId: target.id, policy: payload }).unwrap();
      toast.success(`Access activated for ${target.first_name}`);
      setTarget(null); setDraft(null);
    } catch (error) {
      setEditorError(errorText(error, "Could not save this policy"));
    }
  };

  const peopleColumns = [
    { key: "person", label: "Person", render: (row) => <div className="flex items-center gap-3"><EntityAvatar name={`${row.first_name} ${row.last_name}`} size="md" /><div className="min-w-0"><div className="truncate font-semibold">{row.first_name} {row.last_name}{row.id === currentUser.id && <span className="ml-2 text-xs text-muted-foreground">You</span>}</div><div className="mt-1 truncate text-xs text-muted-foreground">{row.email}</div></div></div> },
    { key: "responsibility", label: "Responsibility", render: (row) => row.roles?.length ? <div className="flex flex-wrap gap-1.5">{row.roles.map((role) => <StatusBadge key={role.id} status="neutral" label={role.name} />)}</div> : <span className="text-muted-foreground">Not assigned</span> },
    { key: "policy", label: "Data policy", render: (row) => <StatusBadge status={row.policy_status === "active" ? "active" : row.policy_status === "expired" ? "inactive" : "pending"} label={row.policy_status === "active" ? "Reviewed" : row.policy_status === "expired" ? "Expired" : "Needs review"} /> },
    { key: "account", label: "Account", render: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} /> },
    { key: "action", label: "", render: (row) => {
      const owner = row.roles?.some((role) => role.slug === "owner");
      const accessAdmin = row.roles?.some((role) => role.slug === "access-admin");
      const protectedFromDelegate = !catalog?.can_manage_delegations && (owner || accessAdmin);
      return <div className="flex flex-wrap justify-end gap-2">
        <Button size="sm" variant="outline" disabled={row.id === currentUser.id || protectedFromDelegate} onClick={(event) => { event.stopPropagation(); openEditor(row); }}>Review access</Button>
        {catalog?.can_manage_delegations && accessAdmin && row.id !== currentUser.id && !owner && <Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); setDelegationTarget(row); }}>Admin ceiling</Button>}
      </div>;
    } },
  ];

  return <PageShell className="reveal">
    <PageHeader eyebrow="People and data boundaries" title="Access" description="Give every person the work they need and only the student data they are responsible for." actions={can("employees.manage") ? <Button onClick={() => navigate("/app/team?new=1")}><Plus className="mr-2" />Add faculty or staff</Button> : null} />
    <Surface className="overflow-hidden">
      <div className="flex flex-col gap-4 border-b px-4 py-4 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-xl sm:w-fit">
            <TabsTrigger value="people">People</TabsTrigger>
            <TabsTrigger value="templates">Role templates</TabsTrigger>
            <TabsTrigger value="audit">Audit</TabsTrigger>
          </TabsList>
        </Tabs>
        {tab === "people" && <div className="relative w-full lg:max-w-sm"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="pl-10" placeholder="Search people or roles" /></div>}
      </div>

      {tab === "people" && <div>
        <DataTable className="rounded-none border-0 shadow-none" loading={peopleQuery.isLoading && !peoplePaging.items.length} rows={peoplePaging.items} columns={peopleColumns} mobileColumns={4} empty={<EmptyState variant={search ? "filtered" : "section"} alignment="left" icon={UsersThree} title={search ? "No people match this search" : "No staff accounts yet"} description={search ? "Clear the search to see all accounts." : "Create staff accounts, then return here to assign responsibilities and data reach."} primaryAction={search ? <Button variant="outline" onClick={() => setSearch("")}>Clear search</Button> : can("employees.manage") ? <Button onClick={() => navigate("/app/team?new=1")}>Add faculty or staff</Button> : null} />} />
        <CursorListFooter count={peoplePaging.items.length} noun="people" hasMore={Boolean(peopleQuery.data?.has_more)} loading={peopleQuery.isFetching} error={peopleQuery.isError} onLoadMore={() => peoplePaging.loadMore(peopleQuery.data?.next_cursor)} onRetry={peopleQuery.refetch} />
      </div>}

      {tab === "templates" && <TemplateDirectory
        templates={catalog?.role_templates || []}
        domains={catalog?.domains || []}
        canManage={catalog?.can_manage_role_templates}
        onCreate={() => setTemplateEditor({ source: null })}
        onClone={(source) => setTemplateEditor({ source })}
      />}

      {tab === "audit" && <div><DataTable className="rounded-none border-0 shadow-none" loading={auditQuery.isLoading && !auditPaging.items.length} rows={auditPaging.items} columns={[
        { key: "summary", label: "Change", render: (row) => <div><div className="font-semibold">{row.summary || humanize(row.action)}</div><div className="mt-1 text-xs text-muted-foreground">{humanize(row.action)}</div></div> },
        { key: "actor", label: "Changed by" },
        { key: "created_at", label: "Time", render: (row) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(row.created_at)) },
      ]} empty={<EmptyState variant="section" alignment="left" icon={ShieldCheck} title="No access changes yet" description="Policy reviews, delegation changes, and role updates will appear here." />} /><CursorListFooter count={auditPaging.items.length} noun="changes" hasMore={Boolean(auditQuery.data?.has_more)} loading={auditQuery.isFetching} error={auditQuery.isError} onLoadMore={() => auditPaging.loadMore(auditQuery.data?.next_cursor)} onRetry={auditQuery.refetch} /></div>}
    </Surface>

    <DrawerForm open={Boolean(target)} onOpenChange={(open) => { if (!open && !saveState.isLoading) { setTarget(null); setDraft(null); } }} title={target ? `Access for ${target.first_name} ${target.last_name}` : "Review access"} description="Nothing changes until the final policy is previewed and activated." className="sm:max-w-3xl">
      {!draft || loadPolicyState.isFetching ? <EditorSkeleton /> : <div className="space-y-6">
        <WizardProgress step={step} setStep={setStep} />
        {step === 0 && <ResponsibilitiesStep catalog={catalog} draft={draft} update={updateDraft} people={peoplePaging.items} target={target} loadPolicy={loadPolicy} />}
        {step === 1 && <ReachStep catalog={catalog} roots={draft.maximum_reach} onChange={(maximum_reach) => updateDraft({ ...draft, maximum_reach })} />}
        {step === 2 && <DomainsStep catalog={catalog} draft={draft} update={updateDraft} />}
        {step === 3 && <SensitiveStep catalog={catalog} draft={draft} update={updateDraft} />}
        {step === 4 && <ReviewStep target={target} draft={draft} catalog={catalog} preview={previewState.data} loading={previewState.isLoading} onPreview={runPreview} />}
        {editorError && <div role="alert" className="flex gap-2 rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger"><WarningCircle className="mt-0.5 shrink-0" />{editorError}</div>}
        <div className="sticky bottom-0 -mx-5 flex flex-col-reverse gap-2 border-t bg-card/95 px-5 pb-1 pt-4 backdrop-blur sm:-mx-6 sm:flex-row sm:justify-between sm:px-6">
          <Button variant="outline" disabled={step === 0 || saveState.isLoading} onClick={() => { setEditorError(""); setStep((value) => value - 1); }}>Back</Button>
          {step < STEPS.length - 1 ? <Button onClick={next}>Continue</Button> : <Button loading={saveState.isLoading} loadingText="Activating access..." disabled={previewState.isLoading || previewFingerprint !== JSON.stringify(toPayload(draft))} onClick={save}>Activate access</Button>}
        </div>
      </div>}
    </DrawerForm>
    <DelegationDrawer
      target={delegationTarget}
      catalog={catalog}
      query={delegationQuery}
      saving={saveDelegationState.isLoading}
      onClose={() => !saveDelegationState.isLoading && setDelegationTarget(null)}
      onSave={async (delegation) => {
        try {
          await saveDelegation({ userId: delegationTarget.id, delegation }).unwrap();
          toast.success(`Administration ceiling updated for ${delegationTarget.first_name}`);
          setDelegationTarget(null);
        } catch (error) {
          toast.error(errorText(error, "Could not save this delegation ceiling"));
        }
      }}
    />
    <RoleTemplateDrawer
      open={Boolean(templateEditor)}
      source={templateEditor?.source}
      domains={catalog?.domains || []}
      canGrantAi={catalog?.can_grant_ai !== false}
      saving={createTemplateState.isLoading}
      onClose={() => !createTemplateState.isLoading && setTemplateEditor(null)}
      onSave={async (template) => {
        try {
          const created = await createTemplate(template).unwrap();
          toast.success(`${created.name} is ready to use`);
          setTemplateEditor(null);
        } catch (error) {
          throw new Error(errorText(error, "Could not create this responsibility"));
        }
      }}
    />
  </PageShell>;
}

function DelegationDrawer({ target, catalog, query, saving, onClose, onSave }) {
  const [draft, setDraft] = useState(null);

  useEffect(() => {
    setDraft(null);
  }, [target?.id]);

  useEffect(() => {
    if (!target || !query.data) return;
    setDraft({
      active: query.data.active,
      maximum_reach: query.data.maximum_reach || [],
      domain_levels: Object.fromEntries(
        (catalog?.domains || []).map((domain) => [domain.key, query.data.domain_levels?.[domain.key] || "none"]),
      ),
      sensitive_capabilities: query.data.sensitive_capabilities || [],
      expires_at: toLocalInput(query.data.expires_at),
      version: query.data.version,
    });
  }, [catalog?.domains, query.data, target]);

  const toggleCapability = (code) => setDraft((current) => ({
    ...current,
    sensitive_capabilities: current.sensitive_capabilities.includes(code)
      ? current.sensitive_capabilities.filter((item) => item !== code)
      : [...current.sensitive_capabilities, code],
  }));
  const hasGrantableDomain = draft && Object.values(draft.domain_levels).some((level) => level !== "none");
  const delegationCapabilities = [
    ...(catalog?.sensitive_capabilities || []),
    { code: "ai.use", label: "May grant Edvatiq AI access", grantable: true, requires_any_domain: true },
  ];
  const delegationIssues = draft
    ? capabilitySelectionIssues(catalog, draft.domain_levels, draft.sensitive_capabilities, delegationCapabilities)
    : [];
  const expiryInvalid = Boolean(draft?.expires_at && new Date(draft.expires_at) <= new Date());
  const ready = draft
    && draft.maximum_reach.length > 0
    && (!draft.active || hasGrantableDomain)
    && !delegationIssues.length
    && !expiryInvalid;
  const payload = draft ? {
    ...draft,
    expires_at: draft.expires_at ? new Date(draft.expires_at).toISOString() : null,
  } : null;

  return <DrawerForm
    open={Boolean(target)}
    onOpenChange={(open) => !open && onClose()}
    title={target ? `Administration ceiling for ${target.first_name}` : "Administration ceiling"}
    description="This limits what the Access Admin may grant. It does not give them access to student records."
    className="sm:max-w-3xl"
  >
    {!draft || query.isFetching ? <EditorSkeleton /> : <div className="space-y-6">
      <label className="flex items-start justify-between gap-4 rounded-2xl border bg-secondary/30 p-4">
        <span><span className="block font-semibold">Delegated Access Admin</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">Turning this off immediately removes delegated administration.</span></span>
        <input type="checkbox" checked={draft.active} onChange={(event) => setDraft({ ...draft, active: event.target.checked })} aria-label="Delegated Access Admin" />
      </label>

      <section className="space-y-3">
        <StepHeading number="1" title="Maximum grantable reach" copy="They may grant only this boundary or a smaller one. They do not automatically see the underlying student data." />
        <ScopePicker catalog={catalog} roots={draft.maximum_reach} onChange={(maximum_reach) => setDraft({ ...draft, maximum_reach })} />
      </section>

      <section className="space-y-3">
        <StepHeading number="2" title="Maximum grantable work" copy="Choose the highest level this administrator may assign in each work area." />
        <div className="divide-y overflow-hidden rounded-2xl border">{(catalog?.domains || []).map((domain) => <div key={domain.key} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center"><div className="min-w-0 flex-1"><div className="font-semibold">{domain.label}</div><div className="mt-1 text-xs text-muted-foreground">{DOMAIN_COPY[domain.key]}</div></div><div className="grid grid-cols-2 gap-1 rounded-xl bg-secondary p-1 sm:grid-cols-4">{LEVELS.map((level) => <button key={level} type="button" onClick={() => setDraft({ ...draft, domain_levels: { ...draft.domain_levels, [domain.key]: level } })} className={cn("rounded-lg px-2.5 py-2 text-xs font-semibold", draft.domain_levels[domain.key] === level ? "bg-card shadow-sm" : "text-muted-foreground")}>{LEVEL_LABELS[level]}</button>)}</div></div>)}</div>
      </section>

      <section className="space-y-3">
        <StepHeading number="3" title="Maximum grantable safeguards" copy="Select only the sensitive capabilities this administrator may grant to other people." />
        <div className="grid gap-2 sm:grid-cols-2">{delegationCapabilities.map((item) => {
          const selected = draft.sensitive_capabilities.includes(item.code);
          const availability = capabilityAvailability(item, draft.domain_levels, draft.sensitive_capabilities, catalog);
          const disabled = !selected && !availability.available;
          return <label key={item.code} aria-disabled={disabled} className={cn("flex gap-3 rounded-xl border p-3 text-sm", selected && "border-primary bg-primary/[0.04]", disabled && "cursor-not-allowed opacity-55")}>
            <input type="checkbox" checked={selected} disabled={disabled} onChange={() => toggleCapability(item.code)} />
            <span><span className="block font-medium">{item.label}</span>{!availability.available && <span className={cn("mt-1 block text-xs", selected ? "text-danger" : "text-muted-foreground")}>{availability.reason}</span>}</span>
          </label>;
        })}</div>
      </section>

      <label className="block text-sm font-semibold">Optional delegation expiry<Input type="datetime-local" className="mt-2" value={draft.expires_at} onChange={(event) => setDraft({ ...draft, expires_at: event.target.value })} /></label>
      {!draft.maximum_reach.length && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger">Choose a maximum reach before saving this delegation.</div>}
      {draft.active && !hasGrantableDomain && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger">Choose at least one work-area ceiling before enabling delegated administration.</div>}
      {expiryInvalid && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger">Delegated access must expire in the future.</div>}
      {delegationIssues.length > 0 && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger">{delegationIssues[0]}</div>}
      <div className="sticky bottom-0 -mx-5 flex flex-col-reverse gap-2 border-t bg-card/95 px-5 pt-4 backdrop-blur sm:-mx-6 sm:flex-row sm:justify-end sm:px-6">
        <Button variant="outline" disabled={saving} onClick={onClose}>Cancel</Button>
        <Button loading={saving} loadingText="Saving ceiling..." disabled={!ready} onClick={() => onSave(payload)}>Save ceiling</Button>
      </div>
    </div>}
  </DrawerForm>;
}


function WizardProgress({ step, setStep }) {
  return <ol className="premium-scrollbar flex max-w-full gap-2 overflow-x-auto pb-1" aria-label="Access review steps">{STEPS.map((label, index) => <li key={label}><button type="button" onClick={() => index < step && setStep(index)} disabled={index > step} className={cn("flex min-w-max items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold", index === step ? "border-primary bg-primary text-primary-foreground" : index < step ? "bg-secondary text-foreground" : "text-muted-foreground opacity-65")}><span className="grid h-5 w-5 place-items-center rounded-full bg-background/15">{index < step ? <Check size={12} weight="bold" /> : index + 1}</span>{label}</button></li>)}</ol>;
}

function ResponsibilitiesStep({ catalog, draft, update, people, target, loadPolicy }) {
  const templates = catalog?.role_templates || [];
  const applyTemplate = (template) => {
    const selected = draft.role_ids.includes(template.id);
    if (selected) {
      update({ ...draft, role_ids: draft.role_ids.filter((id) => id !== template.id) });
      return;
    }
    const domain_levels = { ...draft.domain_levels };
    Object.entries(template.suggested_domain_levels || {}).forEach(([domain, level]) => {
      if (LEVELS.indexOf(level) > LEVELS.indexOf(domain_levels[domain] || "none")) domain_levels[domain] = level;
    });
    update({ ...draft, role_ids: [...draft.role_ids, template.id], domain_levels, ai_enabled: draft.ai_enabled || template.suggested_ai_enabled });
  };
  const copyFrom = async (event) => {
    const userId = event.target.value;
    if (!userId) return;
    try {
      const source = await loadPolicy(userId, true).unwrap();
      const copied = fromServer(source, catalog);
      update({ ...copied, version: draft.version, expires_at: "", review_note: `Copied as a draft from ${source.user.first_name} ${source.user.last_name}` });
      toast.success("Access copied into this draft. Review every step before activating.");
    } catch (error) { toast.error(errorText(error, "Could not copy that access policy")); }
  };
  return <section className="space-y-4"><StepHeading number="1" title="Choose responsibilities" copy="Templates suggest routine work. They do not choose data reach or activate sensitive access." />
    <div className="grid gap-3 sm:grid-cols-2">{templates.map((template) => <button type="button" key={template.id} onClick={() => applyTemplate(template)} className={cn("rounded-2xl border p-4 text-left transition-colors", draft.role_ids.includes(template.id) ? "border-primary bg-primary/[0.04] ring-1 ring-primary" : "hover:bg-secondary/60")}><div className="flex items-start justify-between gap-3"><div className="font-semibold">{template.name}</div><span className={cn("grid h-5 w-5 place-items-center rounded border text-xs", draft.role_ids.includes(template.id) ? "border-primary bg-primary text-primary-foreground" : "bg-card")}>{draft.role_ids.includes(template.id) ? <Check size={12} weight="bold" /> : null}</span></div><p className="mt-2 text-xs leading-5 text-muted-foreground">{template.description}</p></button>)}</div>
    {people.filter((person) => person.id !== target.id && !person.roles?.some((role) => ["owner", "access-admin"].includes(role.slug))).length > 0 && <div className="rounded-2xl border bg-secondary/35 p-4"><label className="text-sm font-semibold" htmlFor="copy-policy">Start from another person</label><p className="mt-1 text-xs text-muted-foreground">Copies a reviewable draft only. It never changes either account automatically.</p><select id="copy-policy" defaultValue="" onChange={copyFrom} className="mt-3 h-10 w-full rounded-xl border bg-card px-3 text-sm"><option value="">Choose a person</option>{people.filter((person) => person.id !== target.id && !person.roles?.some((role) => ["owner", "access-admin"].includes(role.slug))).map((person) => <option key={person.id} value={person.id}>{person.first_name} {person.last_name}</option>)}</select></div>}
  </section>;
}

function ReachStep({ catalog, roots, onChange }) {
  return <section className="space-y-4"><StepHeading number="2" title="Set maximum reach" copy="This is the furthest boundary any work area may use. Parent selections include current and future descendants." /><ScopePicker catalog={catalog} roots={roots} onChange={onChange} includeStudents /></section>;
}

function DomainsStep({ catalog, draft, update }) {
  const [expanded, setExpanded] = useState(null);
  const setLevel = (domain, level) => update({ ...draft, domain_levels: { ...draft.domain_levels, [domain]: level }, domain_scope_limits: level === "none" ? { ...draft.domain_scope_limits, [domain]: [] } : draft.domain_scope_limits });
  const setRoots = (domain, roots) => update({ ...draft, domain_scope_limits: { ...draft.domain_scope_limits, [domain]: roots } });
  return <section className="space-y-4"><StepHeading number="3" title="Choose work areas" copy="Set what the person can do. A narrower work-area reach can never exceed the maximum boundary." /><div className="divide-y overflow-hidden rounded-2xl border">{(catalog?.domains || []).map((domain) => {
    const level = draft.domain_levels[domain.key] || "none";
    const limited = draft.domain_scope_limits[domain.key]?.length;
    const maximumLevel = domain.maximum_level || "manage";
    return <div key={domain.key} className="p-4"><div className="flex flex-col gap-3 lg:flex-row lg:items-center"><div className="min-w-0 flex-1"><div className="font-semibold">{domain.label}</div><div className="mt-1 text-xs leading-5 text-muted-foreground">{DOMAIN_COPY[domain.key] || "Scoped College work"}</div>{maximumLevel !== "manage" && <div className="mt-1 text-xs font-medium text-warning">Your delegation ceiling allows up to {LEVEL_LABELS[maximumLevel]}.</div>}</div><div className="grid grid-cols-2 gap-1 rounded-xl bg-secondary p-1 sm:grid-cols-4">{LEVELS.map((item) => {
      const unavailable = LEVEL_RANK[item] > LEVEL_RANK[maximumLevel];
      return <button type="button" key={item} disabled={unavailable} title={unavailable ? `Your administration ceiling permits up to ${LEVEL_LABELS[maximumLevel]}` : undefined} onClick={() => setLevel(domain.key, item)} className={cn("rounded-lg px-2.5 py-2 text-xs font-semibold", level === item ? "bg-card text-foreground shadow-sm" : "text-muted-foreground", unavailable && "cursor-not-allowed opacity-35")}>{LEVEL_LABELS[item]}</button>;
    })}</div></div>{level !== "none" && <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3"><span className="text-xs text-muted-foreground">{LEVEL_COPY[level]} {limited ? `${limited} narrower scope ${limited === 1 ? "root" : "roots"}.` : "Uses maximum reach."}</span><Button size="sm" variant="ghost" onClick={() => setExpanded(expanded === domain.key ? null : domain.key)}>{expanded === domain.key ? "Close scope" : "Narrow scope"}</Button></div>}{expanded === domain.key && level !== "none" && <div className="mt-4 rounded-xl bg-secondary/35 p-3"><ScopePicker catalog={catalog} roots={draft.domain_scope_limits[domain.key] || []} onChange={(roots) => setRoots(domain.key, roots)} maximumRoots={draft.maximum_reach} compact /><Button className="mt-3" size="sm" variant="ghost" onClick={() => setRoots(domain.key, [])}>Use maximum reach</Button></div>}</div>;
  })}</div></section>;
}

function SensitiveStep({ catalog, draft, update }) {
  const toggle = (code) => update({ ...draft, sensitive_capabilities: draft.sensitive_capabilities.includes(code) ? draft.sensitive_capabilities.filter((item) => item !== code) : [...draft.sensitive_capabilities, code] });
  const issues = policyCapabilityIssues(catalog, draft);
  const hasDomain = Object.values(draft.domain_levels).some((level) => level !== "none");
  return <section className="space-y-5"><StepHeading number="4" title="Sensitive access and safeguards" copy="These privileges are separate from routine work and should be granted only when the responsibility requires them." /><div className="grid gap-3 sm:grid-cols-2">{(catalog?.sensitive_capabilities || []).map((item) => {
    const selected = draft.sensitive_capabilities.includes(item.code);
    const availability = capabilityAvailability(item, draft.domain_levels, draft.sensitive_capabilities, catalog);
    const disabled = !selected && !availability.available;
    return <label key={item.code} aria-disabled={disabled} className={cn("flex gap-3 rounded-2xl border p-4", selected && "border-primary bg-primary/[0.04]", disabled ? "cursor-not-allowed opacity-55" : "cursor-pointer")}><input type="checkbox" className="mt-1" checked={selected} disabled={disabled} onChange={() => toggle(item.code)} /><span><span className="block text-sm font-semibold">{item.label}</span><span className={cn("mt-1 block text-xs leading-5", !availability.available && selected ? "text-danger" : "text-muted-foreground")}>{availability.available ? sensitiveCopy(item.code) : availability.reason}</span></span></label>;
  })}</div><label aria-disabled={!hasDomain && !draft.ai_enabled} className={cn("flex items-start gap-3 rounded-2xl border p-4", !hasDomain && !draft.ai_enabled && "cursor-not-allowed opacity-55")}><input type="checkbox" className="mt-1" checked={draft.ai_enabled} disabled={!hasDomain && !draft.ai_enabled} onChange={(event) => update({ ...draft, ai_enabled: event.target.checked })} /><span><span className="block text-sm font-semibold">Use Edvatiq AI</span><span className={cn("mt-1 block text-xs leading-5", draft.ai_enabled && !hasDomain ? "text-danger" : "text-muted-foreground")}>{draft.ai_enabled && !hasDomain ? "Remove AI access or enable at least one work area." : "AI inherits the same work areas, data reach, and sensitive-field rules. It never expands access."}</span></span></label>{issues.length > 0 && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger">{issues[0]}</div>}<div className="grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Optional expiry<Input type="datetime-local" className="mt-2" value={draft.expires_at} onChange={(event) => update({ ...draft, expires_at: event.target.value })} /></label><label className="text-sm font-semibold">Review note<Textarea className="mt-2 min-h-24" value={draft.review_note} maxLength={500} onChange={(event) => update({ ...draft, review_note: event.target.value })} placeholder="Why this access is appropriate" /></label></div></section>;
}

function ReviewStep({ target, draft, catalog, preview, loading, onPreview }) {
  const roleNames = (catalog?.role_templates || []).filter((row) => draft.role_ids.includes(row.id)).map((row) => row.name);
  const enabled = (catalog?.domains || []).filter((row) => draft.domain_levels[row.key] !== "none");
  return <section className="space-y-4"><StepHeading number="5" title="Review before activation" copy={`Confirm exactly what ${target.first_name} can see and do. Access changes take effect immediately.`} /><div className="grid gap-3 sm:grid-cols-2"><ReviewCard label="Responsibilities" value={roleNames.join(", ") || "None"} /><ReviewCard label="Maximum reach" value={reachText(draft.maximum_reach, catalog)} /><ReviewCard label="Work areas" value={enabled.map((row) => `${row.label}: ${LEVEL_LABELS[draft.domain_levels[row.key]]}`).join("; ") || "None"} /><ReviewCard label="Sensitive access" value={draft.sensitive_capabilities.length ? `${draft.sensitive_capabilities.length} explicit safeguards` : "None"} /><ReviewCard label="Edvatiq AI" value={draft.ai_enabled ? "Enabled within this policy" : "Not available"} /><ReviewCard label="Expiry" value={draft.expires_at ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(draft.expires_at)) : "No expiry"} /></div><Surface className={cn("p-5", preview && "border-positive/35 bg-positive/[0.04]")}><div className="flex items-start gap-3">{loading ? <SpinnerGap className="animate-spin" size={22} /> : preview ? <CheckCircle className="text-positive" size={22} /> : <UserFocus size={22} />}<div className="min-w-0 flex-1"><div className="font-semibold">Preview as this person</div><p className="mt-1 text-sm leading-6 text-muted-foreground">{preview?.summary || "Run the policy evaluator to verify reach, role ceilings, and conflicts before activation."}</p>{preview?.warnings?.map((warning) => <p key={warning} className="mt-2 flex gap-2 text-xs text-warning"><WarningCircle className="shrink-0" />{warning}</p>)}</div><Button size="sm" variant="outline" loading={loading} loadingText="Checking..." onClick={onPreview}>Preview</Button></div></Surface></section>;
}

function ScopePicker({ catalog, roots, onChange, maximumRoots, compact = false, includeStudents = false }) {
  const [search, setSearch] = useState("");
  const options = useMemo(() => scopeOptions(catalog).filter((option) => isWithinMaximum(option, maximumRoots, catalog)), [catalog, maximumRoots]);
  const visible = options.filter((option) => `${option.label} ${option.meta || ""}`.toLowerCase().includes(search.toLowerCase()));
  const selectedKeys = new Set(roots.map(scopeKey));
  const toggle = (option) => {
    const key = scopeKey(option);
    if (selectedKeys.has(key)) { onChange(roots.filter((root) => scopeKey(root) !== key)); return; }
    if (option.scope_type === "organization") onChange([option]);
    else onChange([...roots.filter((root) => root.scope_type !== "organization"), { scope_type: option.scope_type, scope_value: option.scope_value }]);
  };
  return <div className="space-y-3"><div className="relative"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="pl-10" placeholder="Search campuses, departments, programs, or sections" /></div>{roots.length > 0 && <div className="flex flex-wrap gap-2">{roots.map((root) => <button type="button" key={scopeKey(root)} onClick={() => onChange(roots.filter((item) => scopeKey(item) !== scopeKey(root)))} className="inline-flex items-center gap-1 rounded-full border bg-card px-3 py-1.5 text-xs font-semibold">{scopeLabel(root, catalog)} <X size={11} className="text-muted-foreground" /></button>)}</div>}<div className={cn("premium-scrollbar grid gap-2 overflow-y-auto", compact ? "max-h-64" : "max-h-80 sm:grid-cols-2")}>{visible.map((option) => <button type="button" key={scopeKey(option)} onClick={() => toggle(option)} className={cn("rounded-xl border p-3 text-left", selectedKeys.has(scopeKey(option)) ? "border-primary bg-primary/[0.04]" : "bg-card hover:bg-secondary/60")}><div className="flex items-center gap-2"><span className={cn("grid h-4 w-4 place-items-center rounded border text-[10px]", selectedKeys.has(scopeKey(option)) && "border-primary bg-primary text-primary-foreground")}>{selectedKeys.has(scopeKey(option)) ? <Check size={10} weight="bold" /> : null}</span><span className="text-sm font-semibold">{option.label}</span></div><div className="mt-1 pl-6 text-[11px] text-muted-foreground">{option.meta}</div></button>)}</div>{includeStudents && <StudentScopePicker selected={roots.filter((root) => root.scope_type === "student")} onToggle={(root) => toggle(root)} maximumRoots={maximumRoots} />}</div>;
}

function StudentScopePicker({ selected, onToggle, maximumRoots }) {
  const [search, setSearch] = useState("");
  const deferred = useDeferredValue(search.trim());
  const paging = useCursorPagination(JSON.stringify({ q: deferred }));
  const query = useGetAccessStudentsPageQuery({ q: deferred || undefined, cursor: paging.cursor, limit: 25 }, withSkip(QUERY_POLICIES.collaborative, Boolean(maximumRoots) || deferred.length < 2));
  const { accept } = paging;
  useEffect(() => { accept(query.data); }, [accept, query.data]);
  return <div className="rounded-2xl border bg-card p-3"><div className="text-sm font-semibold">Individual students</div><p className="mt-1 text-xs text-muted-foreground">Use only for exceptional person-specific access. Department, program, and section reach is easier to maintain.</p><Input className="mt-3" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Type at least 2 characters" />{deferred.length >= 2 && <div className="mt-2 divide-y">{paging.items.map((student) => <button type="button" key={student.id} onClick={() => onToggle({ scope_type: "student", scope_value: student.id, label: student.name })} className="flex w-full items-center justify-between gap-3 py-2 text-left"><span><span className="block text-sm font-semibold">{student.name}</span><span className="text-xs text-muted-foreground">{student.admission_number} / {student.department} / {student.graduation_year} {student.section}</span></span><span className="text-xs font-semibold text-primary">{selected.some((root) => root.scope_value === student.id) ? "Selected" : "Add"}</span></button>)}</div>}{query.data?.has_more && <Button size="sm" variant="ghost" className="mt-2" loading={query.isFetching} onClick={() => paging.loadMore(query.data.next_cursor)}>Load more</Button>}</div>;
}

function TemplateDirectory({ templates, domains, canManage, onCreate, onClone }) {
  return <div className="space-y-5 p-4 sm:p-5">
    <div className="flex flex-col gap-3 rounded-2xl bg-secondary/45 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div><h2 className="font-display text-xl font-semibold">Responsibility library</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">Start with a familiar college responsibility, then review each person’s data reach separately.</p></div>
      {canManage && <Button onClick={onCreate}><Plus className="mr-2" />Create responsibility</Button>}
    </div>
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{templates.map((template) => {
      const enabled = domains.filter((domain) => template.suggested_domain_levels?.[domain.key] !== "none");
      return <article key={template.id} className="flex min-h-full flex-col rounded-2xl border bg-card p-5"><div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary"><ShieldCheck size={20} /></span><StatusBadge status="neutral" label={template.is_template ? "Built-in starting point" : "Institution responsibility"} /></div><h2 className="mt-4 font-display text-xl font-semibold">{template.name}</h2><p className="mt-2 text-sm leading-5 text-muted-foreground">{template.description || "A workspace-specific responsibility created for this institution."}</p><div className="mt-4 flex flex-wrap gap-1.5">{enabled.slice(0, 5).map((domain) => <span key={domain.key} className="rounded-full bg-secondary px-2.5 py-1 text-[10px] font-semibold">{domain.label}: {LEVEL_LABELS[template.suggested_domain_levels[domain.key]]}</span>)}</div><div className="mt-auto pt-4"><p className="border-t pt-3 text-xs leading-5 text-muted-foreground">This suggests work areas only. Data reach and sensitive fields are always reviewed per person.</p>{canManage && <Button className="mt-3 w-full" size="sm" variant="outline" onClick={() => onClone(template)}><Copy className="mr-2" />Customize a copy</Button>}</div></article>;
    })}</div>
  </div>;
}

function RoleTemplateDrawer({ open, source, domains, canGrantAi, saving, onClose, onSave }) {
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) { setDraft(null); setError(""); return; }
    const suggestedName = source ? `${source.name} - Custom`.slice(0, 100) : "";
    setDraft({
      name: suggestedName,
      description: source?.description || "",
      domain_levels: Object.fromEntries(domains.map((domain) => [
        domain.key, source?.suggested_domain_levels?.[domain.key] || "none",
      ])),
      ai_enabled: Boolean(canGrantAi && source?.suggested_ai_enabled),
      source_role_id: source?.id || null,
    });
    setError("");
  }, [canGrantAi, domains, open, source]);

  const enabled = draft && Object.values(draft.domain_levels).some((level) => level !== "none");
  const nameValid = Boolean(draft?.name.trim().length >= 2 && draft.name.trim().length <= 100);
  const submit = async () => {
    if (!nameValid || !enabled) return;
    setError("");
    try {
      await onSave({ ...draft, name: draft.name.trim(), description: draft.description.trim() || null });
    } catch (nextError) {
      setError(nextError.message);
    }
  };

  return <DrawerForm open={open} onOpenChange={(next) => !next && onClose()} title={source ? `Customize ${source.name}` : "Create responsibility"} description="Build a reusable starting point with plain-language work levels. Sensitive access is never included in a template." className="sm:max-w-3xl">
    {!draft ? <EditorSkeleton /> : <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-semibold">Responsibility name<Input className="mt-2" value={draft.name} maxLength={100} aria-invalid={draft.name.length > 0 && !nameValid} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="For example, ECE Academic Coordinator" /></label>
        <label className="block text-sm font-semibold sm:col-span-2">Short description<Textarea className="mt-2 min-h-20" value={draft.description} maxLength={500} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="Explain when an administrator should choose this responsibility." /></label>
      </div>
      <section className="space-y-3"><StepHeading number="1" title="Suggested work levels" copy="These choices prefill the person’s review. They never select a department, batch, section, course, or student." /><div className="divide-y overflow-hidden rounded-2xl border">{domains.map((domain) => {
        const maximum = domain.maximum_level || "manage";
        return <div key={domain.key} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center"><div className="min-w-0 flex-1"><div className="font-semibold">{domain.label}</div><div className="mt-1 text-xs text-muted-foreground">{DOMAIN_COPY[domain.key]}</div></div><div className="grid grid-cols-2 gap-1 rounded-xl bg-secondary p-1 sm:grid-cols-4">{LEVELS.map((level) => {
          const unavailable = LEVEL_RANK[level] > LEVEL_RANK[maximum];
          return <button key={level} type="button" disabled={unavailable} title={unavailable ? "Outside your administration ceiling" : undefined} onClick={() => setDraft({ ...draft, domain_levels: { ...draft.domain_levels, [domain.key]: level } })} className={cn("rounded-lg px-2.5 py-2 text-xs font-semibold", draft.domain_levels[domain.key] === level ? "bg-card shadow-sm" : "text-muted-foreground", unavailable && "cursor-not-allowed opacity-35")}>{LEVEL_LABELS[level]}</button>;
        })}</div></div>;
      })}</div></section>
      <label aria-disabled={!canGrantAi} className={cn("flex items-start justify-between gap-4 rounded-2xl border bg-secondary/30 p-4", !canGrantAi && "opacity-55")}><span><span className="block font-semibold">Suggest Edvatiq AI</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{canGrantAi ? "AI still inherits the final person-level domains, reach, and field safeguards." : "AI grants are outside your administration ceiling."}</span></span><input type="checkbox" disabled={!canGrantAi} checked={draft.ai_enabled} onChange={(event) => setDraft({ ...draft, ai_enabled: event.target.checked })} aria-label="Suggest Edvatiq AI" /></label>
      {!enabled && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger">Choose at least one work area.</div>}
      {error && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 p-3 text-sm text-danger">{error}</div>}
      <div className="sticky bottom-0 -mx-5 flex flex-col-reverse gap-2 border-t bg-card/95 px-5 pt-4 backdrop-blur sm:-mx-6 sm:flex-row sm:justify-end sm:px-6"><Button variant="outline" disabled={saving} onClick={onClose}>Cancel</Button><Button loading={saving} loadingText="Creating responsibility..." disabled={!nameValid || !enabled} onClick={submit}>Create responsibility</Button></div>
    </div>}
  </DrawerForm>;
}

function StepHeading({ number, title, copy }) { return <div className="flex items-start gap-3"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary text-xs font-bold text-primary-foreground">{number}</span><div><h2 className="font-display text-xl font-semibold">{title}</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">{copy}</p></div></div>; }
function ReviewCard({ label, value }) { return <div className="rounded-2xl border p-4"><div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</div><div className="mt-2 text-sm font-semibold leading-6">{value}</div></div>; }
function EditorSkeleton() { return <div className="space-y-4" aria-label="Loading access policy">{[1, 2, 3, 4].map((item) => <div key={item} className="h-24 animate-pulse rounded-2xl bg-secondary" />)}</div>; }
function scopeKey(root) { return `${root.scope_type}:${root.scope_value}`; }
function humanize(value) { return String(value || "").replaceAll("_", " ").replaceAll(".", " / ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function capabilityAvailability(item, domainLevels, selectedCapabilities, catalog) {
  if (item.grantable === false) return { available: false, reason: "This safeguard is outside your administration ceiling." };
  if (item.requires_any_domain && !Object.values(domainLevels || {}).some((level) => level !== "none")) {
    return { available: false, reason: "Enable at least one work area first." };
  }
  if (item.requires_domain && LEVEL_RANK[domainLevels?.[item.requires_domain] || "none"] < LEVEL_RANK[item.requires_level || "view"]) {
    const domain = (catalog?.domains || []).find((row) => row.key === item.requires_domain);
    return { available: false, reason: `Requires ${domain?.label || humanize(item.requires_domain)} ${LEVEL_LABELS[item.requires_level || "view"]}.` };
  }
  const missingCapability = (item.requires_capabilities || []).find((code) => !selectedCapabilities.includes(code));
  if (missingCapability) {
    const dependency = (catalog?.sensitive_capabilities || []).find((row) => row.code === missingCapability);
    return { available: false, reason: `Also select ${dependency?.label || humanize(missingCapability)}.` };
  }
  if ((item.requires_any_work_domains || []).length && !item.requires_any_work_domains.some(
    (domain) => LEVEL_RANK[domainLevels?.[domain] || "none"] >= LEVEL_RANK.work,
  )) {
    const labels = item.requires_any_work_domains.map(
      (domain) => (catalog?.domains || []).find((row) => row.key === domain)?.label || humanize(domain),
    );
    return { available: false, reason: `Requires Work access to ${labels.join(", ")}.` };
  }
  return { available: true, reason: "" };
}

function capabilitySelectionIssues(catalog, domainLevels, selectedCapabilities, items = catalog?.sensitive_capabilities || []) {
  return selectedCapabilities.flatMap((code) => {
    const item = items.find((row) => row.code === code);
    if (!item) return [`${humanize(code)} is not available in this access catalog.`];
    const availability = capabilityAvailability(item, domainLevels, selectedCapabilities, catalog);
    return availability.available ? [] : [`${item.label}: ${availability.reason}`];
  });
}

function policyCapabilityIssues(catalog, draft) {
  const issues = capabilitySelectionIssues(
    catalog,
    draft.domain_levels,
    draft.sensitive_capabilities,
  );
  if (draft.ai_enabled && !Object.values(draft.domain_levels).some((level) => level !== "none")) {
    issues.push("Edvatiq AI requires at least one work area.");
  }
  return issues;
}

function sensitiveCopy(code) {
  if (code.includes("fees")) return "Shows or changes financial amounts. Clearance status alone does not need this.";
  if (code.includes("export")) return "Allows authorized College data to leave the workspace.";
  if (code.includes("correct") || code.includes("override")) return "Allows an audited exception to published or calculated evidence.";
  if (code.includes("integrations")) return "Controls credentials and external data connections.";
  if (code.includes("send")) return "Allows communication to students through configured channels.";
  return "Reveals or manages information hidden from routine work.";
}

function scopeOptions(catalog) {
  const hierarchy = catalog?.hierarchy || {};
  const departments = new Map((hierarchy.departments || []).map((row) => [row.id, row]));
  const programs = new Map((hierarchy.programs || []).map((row) => [row.id, row]));
  const cohorts = new Map((hierarchy.cohorts || []).map((row) => [row.id, row]));
  return [
    { scope_type: "organization", scope_value: "*", label: "Whole institution", meta: "Includes every current and future academic branch" },
    ...(hierarchy.locations || []).map((row) => ({ scope_type: "location", scope_value: row.id, label: row.name, meta: `Campus / ${row.code || "No code"}` })),
    ...(hierarchy.departments || []).map((row) => ({ scope_type: "department", scope_value: row.id, label: row.name, meta: `Department / ${row.code}` })),
    ...(hierarchy.programs || []).map((row) => ({ scope_type: "program", scope_value: row.id, label: row.name, meta: `Program / ${departments.get(row.department_id)?.code || "Department"}` })),
    ...(hierarchy.cohorts || []).map((row) => ({ scope_type: "cohort", scope_value: row.id, label: `${row.name}${row.section && row.section !== "GENERAL" ? ` / ${row.section}` : ""}`, meta: `Cohort / ${programs.get(row.program_id)?.code || "Program"} / ${row.graduation_year}` })),
    ...(hierarchy.course_offerings || []).map((row) => ({ scope_type: "course_offering", scope_value: row.id, label: row.name, meta: `Course offering / ${cohorts.get(row.cohort_id)?.name || "Cohort"}` })),
  ];
}

function scopeLabel(root, catalog) {
  if (root.label) return root.label;
  return scopeOptions(catalog).find((option) => scopeKey(option) === scopeKey(root))?.label || `${humanize(root.scope_type)} / ${String(root.scope_value).slice(0, 8)}`;
}

function reachText(roots, catalog) {
  if (roots.some((root) => root.scope_type === "organization")) return "Whole institution, including future descendants";
  return roots.map((root) => scopeLabel(root, catalog)).join(", ") || "No reach selected";
}

function isWithinMaximum(option, maximumRoots, catalog) {
  if (!maximumRoots?.length || maximumRoots.some((root) => root.scope_type === "organization")) return true;
  if (maximumRoots.some((root) => scopeKey(root) === scopeKey(option))) return true;
  const hierarchy = catalog?.hierarchy || {};
  const programs = new Map((hierarchy.programs || []).map((row) => [row.id, row]));
  const cohorts = new Map((hierarchy.cohorts || []).map((row) => [row.id, row]));
  const offerings = new Map((hierarchy.course_offerings || []).map((row) => [row.id, row]));
  const departments = new Map((hierarchy.departments || []).map((row) => [row.id, row]));
  const ancestors = [];
  if (option.scope_type === "department") ancestors.push(["location", departments.get(option.scope_value)?.location_id]);
  if (option.scope_type === "program") { const row = programs.get(option.scope_value); ancestors.push(["department", row?.department_id], ["location", departments.get(row?.department_id)?.location_id]); }
  if (option.scope_type === "cohort") { const row = cohorts.get(option.scope_value); const program = programs.get(row?.program_id); ancestors.push(["program", row?.program_id], ["department", program?.department_id], ["location", departments.get(program?.department_id)?.location_id]); }
  if (option.scope_type === "course_offering") { const row = offerings.get(option.scope_value); const cohort = cohorts.get(row?.cohort_id); const program = programs.get(cohort?.program_id); ancestors.push(["cohort", row?.cohort_id], ["program", cohort?.program_id], ["department", program?.department_id], ["location", departments.get(program?.department_id)?.location_id]); }
  return maximumRoots.some((root) => ancestors.some(([type, id]) => root.scope_type === type && root.scope_value === id));
}
