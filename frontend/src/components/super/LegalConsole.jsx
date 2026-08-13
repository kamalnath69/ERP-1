import React, { useDeferredValue, useEffect, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import {
  ArrowSquareOut, EnvelopeSimple, FileText, MagnifyingGlass, PencilSimple,
  Plus, Scales, ShieldCheck, UsersThree, Warning,
} from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { ValidatedActionDialog } from "@/components/forms/ValidatedActionDialog";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, PageHeader,
  SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import {
  Form, FormControl, FormDescription, FormField, FormItem, FormLabel,
  FormMessage, FormRootError,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import api from "@/lib/api";
import { applyApiErrors, FORM_OPTIONS, z } from "@/lib/validation";

const DOCUMENTS = {
  terms: { label: "Terms of Service", path: "/terms" },
  privacy: { label: "Privacy Policy", path: "/privacy" },
  refund: { label: "Refund Policy", path: "/refund-policy" },
};

const profileSchema = z.object({
  brand_name: z.string().trim().min(2, "Enter the public brand name").max(120),
  legal_name: z.string().trim().min(2, "Enter the registered legal name").max(220),
  registered_address: z.string().trim().min(8, "Enter the complete registered address").max(1000),
  country: z.string().trim().min(2, "Enter the country").max(100),
  state: z.string().trim().min(2, "Enter the state or region").max(100),
  jurisdiction: z.string().trim().min(2, "Enter the legal jurisdiction").max(240),
  support_email: z.string().trim().email("Enter a valid support email"),
  privacy_email: z.string().trim().email("Enter a valid privacy email"),
  grievance_contact: z.string().trim().min(3, "Enter the grievance contact").max(300),
  registration_identifiers: z.string().trim().max(500, "Keep identifiers under 500 characters"),
  version: z.number().int().min(1),
});

const draftSchema = z.object({
  title: z.string().trim().min(3, "Enter a document title").max(180),
  content_markdown: z.string().trim().min(100, "Add at least 100 characters of reviewed legal content").max(100000)
    .refine((value) => !/<\s*\/?\s*[a-z][^>]*>/i.test(value), "Raw HTML is not allowed"),
});

function field(name, label, control, { textarea = false, description, type = "text", autoComplete } = {}) {
  return <FormField key={name} control={control} name={name} render={({ field: input }) => <FormItem>
    <FormLabel>{label}</FormLabel>
    <FormControl>{textarea
      ? <Textarea {...input} value={input.value ?? ""} rows={4} />
      : <Input {...input} value={input.value ?? ""} type={type} autoComplete={autoComplete} />}</FormControl>
    {description && <FormDescription>{description}</FormDescription>}
    <FormMessage />
  </FormItem>} />;
}

export default function LegalConsole() {
  const [section, setSection] = useState("documents");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [editing, setEditing] = useState(null);
  const [publishing, setPublishing] = useState(null);
  const [creating, setCreating] = useState(null);
  const [preparingV2, setPreparingV2] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const response = await api.get("/super-admin/legal");
      setData(response.data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const createDraft = async (kind) => {
    const base = data.documents.find((document) => document.type === kind);
    if (!base || creating) return;
    setCreating(kind);
    try {
      const response = await api.post(`/super-admin/legal/documents/${kind}/drafts`, {
        title: base.title,
        content_markdown: base.content_markdown,
      });
      toast.success(`${DOCUMENTS[kind].label} draft created`);
      setEditing(response.data);
      await load();
    } catch (requestError) {
      toast.error(requestError.response?.data?.detail || "The legal draft could not be created");
    } finally {
      setCreating(null);
    }
  };

  const prepareVersionTwo = async () => {
    if (preparingV2) return;
    setPreparingV2(true);
    try {
      const response = await api.post("/super-admin/legal/documents/version-two-drafts");
      const created = response.data.created?.length || 0;
      const blocked = response.data.blocked?.length || 0;
      if (created) toast.success(`${created} detailed Version 2 ${created === 1 ? "draft" : "drafts"} prepared`);
      else toast.info("Version 2 drafts already exist or an earlier draft needs review");
      if (blocked) toast.warning(`${blocked} ${blocked === 1 ? "policy needs" : "policies need"} the existing draft completed first`);
      await load();
    } catch (requestError) {
      toast.error(requestError.response?.data?.detail || "Version 2 drafts could not be prepared");
    } finally {
      setPreparingV2(false);
    }
  };

  if (loading && !data) return <LegalSkeleton />;
  if (error && !data) return <ErrorState title="Legal controls could not be loaded" retry={load} />;

  const counts = data.documents.reduce((result, document) => ({
    ...result, [document.status]: (result[document.status] || 0) + 1,
  }), {});
  const versionTwoReady = Object.keys(DOCUMENTS).every((kind) => data.documents.some((document) => document.type === kind && document.version >= 2));

  return <div className="space-y-6">
    <PageHeader
      eyebrow="Public trust"
      title="Legal publication and demo leads"
      description="Publish authoritative policies, control registration readiness, and follow up on public enquiries from one auditable workspace."
      actions={<div className="flex flex-wrap items-center gap-2">{!versionTwoReady && <Button variant="outline" loading={preparingV2} loadingText="Preparing V2..." onClick={prepareVersionTwo}><Plus className="mr-1.5" />Prepare detailed V2 drafts</Button>}<StatusBadge status={data.ready ? "active" : "pending"} label={data.ready ? "Registration ready" : "Registration blocked"} /></div>}
    />
    {!data.ready && <Surface className="flex items-start gap-3 border-warning/30 bg-warning-soft p-4">
      <Warning className="mt-0.5 shrink-0 text-warning" size={20} />
      <div><div className="text-sm font-semibold">Registration remains safely blocked</div><p className="mt-1 text-sm text-muted-foreground">Complete the operator profile and publish the current Terms, Privacy Policy, and Refund Policy before accepting new accounts.</p></div>
    </Surface>}
    <SegmentControl value={section} onChange={setSection} items={[
      { value: "documents", label: "Legal documents", count: counts.draft || 0 },
      { value: "profile", label: "Operator profile", count: data.missing_profile_fields.length || null },
      { value: "leads", label: "Demo requests" },
    ]} />
    {section === "documents" && <DocumentsPanel data={data} creating={creating} onCreate={createDraft} onEdit={setEditing} onPublish={setPublishing} />}
    {section === "profile" && <OperatorProfile data={data} onSaved={load} />}
    {section === "leads" && <DemoLeads />}
    <DraftEditor document={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await load(); }} />
    <ValidatedActionDialog
      open={Boolean(publishing)}
      onOpenChange={(open) => { if (!open) setPublishing(null); }}
      resetKey={publishing?.id}
      title={publishing ? `Publish ${publishing.title}?` : "Publish legal document"}
      description={publishing ? `Version ${publishing.version} becomes the current ${DOCUMENTS[publishing.type]?.label}.` : ""}
      impact="The published text becomes immutable and the previous current version is retained as historical. New registrations must accept this exact version."
      schema={z.object({})}
      defaultValues={{}}
      fields={[]}
      submitLabel="Publish version"
      loadingText="Publishing..."
      onSubmit={async () => {
        await api.post(`/super-admin/legal/documents/${publishing.id}/publish`, { version_lock: publishing.version_lock });
        toast.success("Legal version published");
        await load();
      }}
    />
  </div>;
}

function DocumentsPanel({ data, creating, onCreate, onEdit, onPublish }) {
  return <div className="grid items-start gap-4 xl:grid-cols-3">{Object.entries(DOCUMENTS).map(([kind, definition]) => {
    const versions = data.documents.filter((document) => document.type === kind);
    const draft = versions.find((document) => document.status === "draft");
    const current = versions.find((document) => document.status === "published");
    return <Surface key={kind} className="overflow-hidden">
      <div className="flex items-start justify-between gap-3 p-5">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary"><FileText size={20} /></span>
        <StatusBadge status={current ? "active" : "pending"} label={current ? `Published v${current.version}` : "Not published"} />
      </div>
      <div className="px-5 pb-5"><h2 className="font-display text-xl font-semibold">{definition.label}</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">{draft ? `Draft version ${draft.version} is waiting for review.` : current ? "The current public version is immutable." : "Review and publish the seeded draft."}</p></div>
      <div className="divide-y border-t">
        {versions.slice(0, 4).map((document) => <div key={document.id} className="flex items-center gap-3 px-5 py-3">
          <div className="min-w-0 flex-1"><div className="text-sm font-medium">Version {document.version}</div><div className="mt-0.5 text-xs text-muted-foreground">{document.status === "published" ? `Published ${dateTime(document.published_at)}` : document.status === "retired" ? "Historical version" : "Editable draft"}</div></div>
          <StatusBadge status={document.status} />
          {document.status === "draft" && <Button size="sm" variant="ghost" onClick={() => onEdit(document)} aria-label={`Edit ${definition.label} version ${document.version}`}><PencilSimple /></Button>}
        </div>)}
      </div>
      <div className="flex flex-col gap-2 border-t bg-secondary/20 p-4 sm:flex-row">
        {draft ? <><Button size="sm" variant="outline" onClick={() => onEdit(draft)}>Edit draft</Button><Button size="sm" onClick={() => onPublish(draft)}>Review and publish</Button></>
          : <Button size="sm" variant="outline" loading={creating === kind} loadingText="Creating..." disabled={!versions.length} onClick={() => onCreate(kind)}><Plus className="mr-1.5" />New version</Button>}
        {current && <Button asChild size="sm" variant="ghost"><Link target="_blank" to={definition.path}>View public <ArrowSquareOut className="ml-1.5" /></Link></Button>}
      </div>
    </Surface>;
  })}</div>;
}

function OperatorProfile({ data, onSaved }) {
  const form = useForm({ resolver: zodResolver(profileSchema), defaultValues: { ...data.profile, version: data.profile_version }, ...FORM_OPTIONS });
  useEffect(() => { form.reset({ ...data.profile, registration_identifiers: data.profile.registration_identifiers || "", version: data.profile_version }); }, [data, form]);
  const submit = form.handleSubmit(async (values) => {
    form.clearErrors("root.server");
    try {
      await api.put("/super-admin/legal/profile", { ...values, registration_identifiers: values.registration_identifiers || null });
      toast.success("Legal operator profile saved");
      await onSaved();
    } catch (requestError) {
      applyApiErrors(requestError, form.setError);
    }
  });
  return <Surface className="max-w-5xl p-5 sm:p-6">
    <div className="flex items-start gap-3 border-b pb-5"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary"><Scales /></span><div><h2 className="font-display text-xl font-semibold">Authoritative operator details</h2><p className="mt-1 text-sm text-muted-foreground">These details are inserted into legal publications. Use only reviewed business information.</p></div></div>
    <Form {...form}><form noValidate onSubmit={submit} className="mt-5 space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">{field("brand_name", "Public brand", form.control)}{field("legal_name", "Registered legal name", form.control)}</div>
      {field("registered_address", "Registered address", form.control, { textarea: true })}
      <div className="grid gap-4 sm:grid-cols-2">{field("country", "Country", form.control)}{field("state", "State or region", form.control)}</div>
      {field("jurisdiction", "Governing jurisdiction", form.control, { description: "Use the reviewed court or dispute jurisdiction wording." })}
      <div className="grid gap-4 sm:grid-cols-2">{field("support_email", "Support email", form.control, { type: "email", autoComplete: "email" })}{field("privacy_email", "Privacy email", form.control, { type: "email", autoComplete: "email" })}</div>
      {field("grievance_contact", "Grievance contact", form.control, { description: "Name, designation, and a monitored contact channel." })}
      {field("registration_identifiers", "Registration identifiers (optional)", form.control)}
      <FormRootError error={form.formState.errors.root?.server} />
      <div className="flex justify-end border-t pt-5"><Button type="submit" loading={form.formState.isSubmitting} loadingText="Saving...">Save operator profile</Button></div>
    </form></Form>
  </Surface>;
}

function DraftEditor({ document, onClose, onSaved }) {
  const form = useForm({ resolver: zodResolver(draftSchema), defaultValues: { title: "", content_markdown: "" }, ...FORM_OPTIONS });
  useEffect(() => { if (document) form.reset({ title: document.title, content_markdown: document.content_markdown }); }, [document, form]);
  const submit = form.handleSubmit(async (values) => {
    form.clearErrors("root.server");
    try {
      await api.put(`/super-admin/legal/documents/${document.id}`, { ...values, version_lock: document.version_lock });
      toast.success("Legal draft saved");
      await onSaved();
    } catch (requestError) {
      applyApiErrors(requestError, form.setError);
    }
  });
  return <DrawerForm open={Boolean(document)} onOpenChange={(open) => { if (!open && !form.formState.isSubmitting) onClose(); }} title={document ? `${DOCUMENTS[document.type]?.label} / Version ${document.version}` : "Legal draft"} description="Markdown is supported. Raw HTML is intentionally blocked.">
    <Form {...form}><form noValidate onSubmit={submit} className="space-y-5">
      {field("title", "Document title", form.control)}
      <FormField control={form.control} name="content_markdown" render={({ field: input }) => <FormItem><FormLabel>Reviewed Markdown</FormLabel><FormControl><Textarea {...input} value={input.value ?? ""} className="min-h-[55dvh] font-mono text-xs leading-6" /></FormControl><FormDescription>Placeholders such as {"{{legal_name}}"} are resolved only when the version is published.</FormDescription><FormMessage /></FormItem>} />
      <FormRootError error={form.formState.errors.root?.server} />
      <div className="sticky bottom-0 flex justify-end gap-2 border-t bg-card/95 py-4 backdrop-blur"><Button type="button" variant="outline" disabled={form.formState.isSubmitting} onClick={onClose}>Cancel</Button><Button type="submit" loading={form.formState.isSubmitting} loadingText="Saving...">Save draft</Button></div>
    </form></Form>
  </DrawerForm>;
}

function DemoLeads() {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [items, setItems] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState(null);
  const [pending, setPending] = useState(null);
  const requestRef = useRef(0);

  const fetchPage = async ({ append = false, cursor = null } = {}) => {
    const requestId = ++requestRef.current;
    setLoading(true);
    setError(false);
    try {
      const response = await api.get("/super-admin/legal/demo-requests", { params: { status, q: q || undefined, cursor: cursor || undefined, limit: 25 } });
      if (requestId !== requestRef.current) return;
      setItems((current) => append ? [...current, ...response.data.items.filter((row) => !current.some((item) => item.id === row.id))] : response.data.items);
      setNextCursor(response.data.next_cursor);
      setHasMore(response.data.has_more);
    } catch {
      if (requestId === requestRef.current) setError(true);
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  };
  useEffect(() => { fetchPage(); }, [status, q]);

  const updateStatus = async (lead, value) => {
    setPending(lead.id);
    try {
      const response = await api.patch(`/super-admin/legal/demo-requests/${lead.id}`, { status: value });
      setItems((current) => current.map((item) => item.id === lead.id ? response.data : item));
      setSelected((current) => current?.id === lead.id ? response.data : current);
      toast.success("Demo request updated");
    } catch (requestError) {
      toast.error(requestError.response?.data?.detail || "The lead could not be updated");
    } finally {
      setPending(null);
    }
  };
  const columns = [
    { key: "organization", label: "Organization", render: (row) => <div><div className="font-semibold">{row.organization_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.name} / {row.work_email}</div></div> },
    { key: "industry", label: "Industry", render: (row) => sentence(row.industry) },
    { key: "received", label: "Received", render: (row) => dateTime(row.created_at) },
    { key: "status", label: "Status", render: (row) => <select aria-label={`Status for ${row.organization_name}`} className="h-9 rounded-lg border bg-background px-2 text-xs" value={row.status} disabled={pending === row.id} onClick={(event) => event.stopPropagation()} onChange={(event) => updateStatus(row, event.target.value)}>{["new", "contacted", "qualified", "closed"].map((value) => <option value={value} key={value}>{sentence(value)}</option>)}</select> },
  ];
  return <div className="space-y-4">
    <Surface className="p-3"><div className="flex flex-col gap-3 sm:flex-row"><div className="relative min-w-0 flex-1"><MagnifyingGlass className="absolute left-3 top-2.5 text-muted-foreground" /><Input className="pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, email, or organization" /></div><SegmentControl className="w-full sm:w-auto" value={status} onChange={setStatus} items={["all", "new", "contacted", "qualified", "closed"].map((value) => ({ value, label: sentence(value) }))} /></div></Surface>
    <Surface className="overflow-hidden"><div className="flex items-center gap-3 border-b p-4"><span className="grid h-9 w-9 place-items-center rounded-lg bg-secondary"><UsersThree /></span><div><h2 className="font-semibold">Public demo enquiries</h2><p className="text-xs text-muted-foreground">Persisted before notification and isolated from marketing consent.</p></div></div>
      {error && !items.length ? <ErrorState className="m-4" title="Demo requests could not be loaded" retry={() => fetchPage()} /> : <DataTable className="rounded-none border-0 shadow-none" columns={columns} rows={items} loading={loading && !items.length} onRowClick={setSelected} empty={<EmptyState variant={q || status !== "all" ? "filtered" : "section"} alignment="left" icon={EnvelopeSimple} title={q || status !== "all" ? "No matching demo requests" : "No demo requests yet"} description={q || status !== "all" ? "Change the search or status filter." : "New enquiries from the public site will appear here."} />} />}
      <CursorListFooter count={items.length} hasMore={hasMore} loading={loading} error={error && items.length > 0} onLoadMore={() => fetchPage({ append: true, cursor: nextCursor })} onRetry={() => fetchPage({ append: Boolean(items.length), cursor: items.length ? nextCursor : null })} noun="requests" />
    </Surface>
    <DrawerForm open={Boolean(selected)} onOpenChange={(open) => { if (!open && pending !== selected?.id) setSelected(null); }} title={selected?.organization_name || "Demo request"} description={selected ? `Received ${dateTime(selected.created_at)}` : ""}>
      {selected && <div className="space-y-5"><div className="grid gap-3 sm:grid-cols-2"><LeadValue label="Contact" value={selected.name} /><LeadValue label="Work email" value={selected.work_email} /><LeadValue label="Industry" value={sentence(selected.industry)} /><LeadValue label="Role" value={selected.role || "Not provided"} /><LeadValue label="Phone" value={selected.phone || "Not provided"} /><LeadValue label="Notification" value={selected.notified_at ? "Delivered" : "Pending or unavailable"} /></div><div><div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Message</div><p className="mt-2 whitespace-pre-wrap rounded-xl bg-secondary/45 p-4 text-sm leading-6">{selected.message || "No additional message."}</p></div><div><label className="text-sm font-medium" htmlFor="lead-status">Follow-up status</label><select id="lead-status" className="mt-2 h-10 w-full rounded-lg border bg-background px-3 text-sm" value={selected.status} disabled={pending === selected.id} onChange={(event) => updateStatus(selected, event.target.value)}>{["new", "contacted", "qualified", "closed"].map((value) => <option value={value} key={value}>{sentence(value)}</option>)}</select></div></div>}
    </DrawerForm>
  </div>;
}

function LeadValue({ label, value }) { return <div className="rounded-xl border p-3"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 break-words text-sm font-medium">{value}</div></div>; }
function LegalSkeleton() { return <div className="animate-pulse space-y-5"><div className="h-12 w-80 max-w-full rounded-xl bg-secondary" /><div className="h-11 w-96 max-w-full rounded-xl bg-secondary" /><div className="grid gap-4 xl:grid-cols-3">{[1, 2, 3].map((item) => <div key={item} className="h-72 rounded-2xl bg-card" />)}</div></div>; }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not available"; }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
