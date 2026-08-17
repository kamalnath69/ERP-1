import React, { useCallback, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import BrandLogo from "@/components/brand/BrandLogo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ValidatedActionDialog } from "@/components/forms/ValidatedActionDialog";
import LegalConsole from "@/components/super/LegalConsole";
import { usePendingAction, useStableIdempotencyKey } from "@/hooks/usePendingAction";
import {
  approvalDecisionSchema, organizationDeletionSchema, ownerTransferSchema,
  platformTeamSchema, refundSchema, walletRechargeSchema, z,
} from "@/lib/validation";
import {
  ArrowClockwise, Buildings, CaretRight, ChartLineUp, CheckCircle, CreditCard,
  Gear, Lifebuoy, ListMagnifyingGlass, MagnifyingGlass, Pulse, Robot, Scroll,
  ShieldCheck, SignOut, Stack, Users, Wallet, Warning, X,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const sections = [
  ["overview", "Overview", ChartLineUp], ["organizations", "Organizations", Buildings],
  ["plans", "Plans", Stack], ["billing", "Billing", CreditCard], ["wallet", "AI Wallet", Wallet],
  ["team", "Platform Team", Users], ["support", "Support", Lifebuoy],
  ["operations", "Operations", Pulse], ["audit", "Audit", Scroll],
  ["legal", "Legal & leads", ShieldCheck], ["settings", "Settings", Gear],
];

export default function SuperAdmin() {
  const { user, logout } = useAuth();
  const location = useLocation(); const navigate = useNavigate();
  const active = location.pathname.split("/")[2] || "overview";
  const [identity, setIdentity] = useState(null);
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { api.get("/super-admin/me").then(({ data }) => setIdentity(data)).catch(() => toast.error("Could not open the control center")); }, []);
  if (!user?.is_super_admin) return <Navigate to="/app" replace />;
  const current = sections.find(([key]) => key === active) || sections[0];
  const open = (key) => { navigate(key === "overview" ? "/super" : `/super/${key}`); setNavOpen(false); };
  return <div className="flex min-h-screen bg-background text-foreground">
    <aside className={`${navOpen ? "flex" : "hidden"} fixed inset-y-0 left-0 z-50 w-72 flex-col bg-sidebar text-sidebar-foreground lg:sticky lg:flex`}>
      <div className="flex h-20 items-center justify-between border-b border-sidebar-foreground/10 px-6"><button onClick={() => open("overview")}><BrandLogo markClassName="h-9 w-9" nameClassName="font-display text-xl text-sidebar-foreground" /></button><button className="lg:hidden" onClick={() => setNavOpen(false)}><X /></button></div>
      <div className="px-6 pb-3 pt-6"><div className="text-[10px] uppercase tracking-[.2em] text-accent">Platform Control</div><p className="mt-1 text-xs text-sidebar-muted">Business health and operations</p></div>
      <nav className="premium-scrollbar flex-1 space-y-1 overflow-y-auto px-3">{sections.map(([key, label, Icon]) => <button key={key} onClick={() => open(key)} className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm ${active === key ? "bg-background text-foreground" : "text-sidebar-muted hover:bg-sidebar-foreground/10 hover:text-sidebar-foreground"}`}><Icon size={19} weight="duotone" />{label}</button>)}</nav>
      <div className="border-t border-sidebar-foreground/10 p-4"><div className="rounded-xl bg-sidebar-foreground/5 p-3"><div className="text-sm font-medium">{user.first_name} {user.last_name}</div><div className="mt-1 truncate text-xs text-sidebar-muted">{user.email}</div><button onClick={async () => { await logout(); navigate("/login"); }} className="mt-3 flex items-center gap-2 text-xs text-sidebar-muted"><SignOut />Sign out</button></div></div>
    </aside>
    {navOpen && <button aria-label="Close navigation" className="fixed inset-0 z-40 bg-foreground/35 lg:hidden" onClick={() => setNavOpen(false)} />}
    <main className="flex-1 min-w-0">
      <header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b bg-background/90 px-4 backdrop-blur md:px-8"><div className="flex items-center gap-3"><button className="grid h-10 w-10 place-items-center rounded-xl border lg:hidden" onClick={() => setNavOpen(true)}><ListMagnifyingGlass /></button><div><div className="overline text-accent">Control Center</div><h1 className="font-display text-2xl font-bold">{current[1]}</h1></div></div><div className="flex items-center gap-2"><StatusDot good={identity?.mfa?.enrolled} label={identity?.mfa?.enrolled ? "Account protected" : "Protection setup due"} /></div></header>
      <div className="p-4 md:p-8 max-w-[1600px] mx-auto"><Section name={active} /></div>
    </main>
    {identity?.mfa?.enrollment_required && <MfaSetup onComplete={() => setIdentity((value) => ({ ...value, mfa: { enrolled: true, enrollment_required: false } }))} />}
  </div>;
}

function Section({ name }) {
  if (name === "organizations") return <Organizations />;
  if (name === "plans") return <Plans />;
  if (name === "billing") return <Billing />;
  if (name === "wallet") return <Wallets />;
  if (name === "team") return <PlatformTeam />;
  if (name === "support") return <Support />;
  if (name === "operations") return <Operations />;
  if (name === "audit") return <Audit />;
  if (name === "legal") return <LegalConsole />;
  if (name === "settings") return <Settings />;
  return <Overview />;
}

function useLoad(path, initial) {
  const [data, setData] = useState(initial); const [loading, setLoading] = useState(true); const [error, setError] = useState(false);
  const load = useCallback(async () => { setLoading(true); setError(false); try { const response = await api.get(path); setData(response.data); } catch { setError(true); } finally { setLoading(false); } }, [path]);
  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load };
}

function Overview() {
  const { data, loading, error, reload } = useLoad("/super-admin/overview", {});
  if (loading) return <PageSkeleton />; if (error) return <LoadError retry={reload} />;
  const metrics = data.metrics || {}; const orgs = data.organizations || {};
  return <div className="space-y-7 reveal"><PageIntro eyebrow="Today" title="The platform at a glance" text="Revenue, client health, approvals, and operations in one place." />
    <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4"><Metric label="Monthly recurring revenue" value={money(metrics.mrr_paise)} accent /><Metric label="Annual run rate" value={money(metrics.arr_paise)} note={`${orgs.churned_this_month || 0} churned this month`} /><Metric label="Organizations" value={orgs.total} note={`${orgs.new_this_month || 0} joined this month`} /><Metric label="Approvals waiting" value={data.approvals} warn={data.approvals > 0} /></div>
    <div className="grid lg:grid-cols-3 gap-5"><Panel title="Billing attention"><Signal label="Outstanding" value={money(metrics.outstanding_paise)} state={metrics.outstanding_paise > 0 ? "warn" : "good"} /><Signal label="Failed payments" value={metrics.failed_payments || 0} state={metrics.failed_payments ? "warn" : "good"} /><Signal label="Trials" value={orgs.trials || 0} /></Panel><Panel title="AI consumption"><Signal label="Estimated provider cost" value={money(metrics.ai_cost_paise)} /><Signal label="Credits used this month" value={format(metrics.ai_credits_used)} /><Signal label="Tokens processed" value={format(metrics.ai_tokens)} /></Panel><Panel title="Operations"><Signal label="Work waiting" value={metrics.queued_jobs || 0} /><Signal label="Incidents" value={metrics.incidents || 0} state={metrics.incidents ? "warn" : "good"} /><Signal label="Suspended organizations" value={orgs.suspended || 0} /></Panel></div>
  </div>;
}

function Organizations() {
  const [query, setQuery] = useState(""); const [status, setStatus] = useState(""); const [selected, setSelected] = useState(null); const [workspace, setWorkspace] = useState(null); const [loadingDetail, setLoadingDetail] = useState(false);
  const path = `/super-admin/organizations?limit=50${query ? `&q=${encodeURIComponent(query)}` : ""}${status ? `&status=${status}` : ""}`;
  const { data, loading, error, reload } = useLoad(path, { items: [] });
  const open = async (org) => { setSelected(org); setLoadingDetail(true); try { const { data: detail } = await api.get(`/super-admin/organizations/${org.id}`); setWorkspace(detail); } catch { toast.error("Could not open this organization"); } finally { setLoadingDetail(false); } };
  const toggle = async () => { const action = workspace.organization.status === "suspended" ? "restore" : "suspend"; try { await api.post(`/super-admin/organizations/${workspace.organization.id}/${action}`); toast.success(action === "restore" ? "Organization restored" : "Organization suspended"); await open(workspace.organization); reload(); } catch (error) { toast.error(message(error)); } };
  return <div className="space-y-6"><PageIntro eyebrow="Organizations" title="Every business, clearly understood" text="Review plan, usage, payment health, users, locations, and access without leaving this workspace." />
    <div className="flex flex-col gap-3 sm:flex-row"><div className="relative max-w-xl flex-1"><MagnifyingGlass className="absolute left-3 top-3 text-muted-foreground" /><Input className="bg-card pl-10" placeholder="Search business name, ID, or email" value={query} onChange={(event) => setQuery(event.target.value)} /></div><select className="h-10 rounded-md border bg-card px-3 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="trial">Trial</option><option value="suspended">Suspended</option></select></div>
    {loading ? <TableSkeleton /> : error ? <LoadError retry={reload} /> : <div className="overflow-hidden rounded-2xl border bg-card"><div className="overflow-x-auto"><table className="w-full min-w-[900px] text-sm"><thead><tr className="bg-secondary text-left"><Th>Business</Th><Th>Industry</Th><Th>Plan & payment</Th><Th>Usage</Th><Th>AI credits</Th><Th>Status</Th><Th /></tr></thead><tbody>{data.items?.map((org) => <tr className="border-t hover:bg-surface-hover" key={org.id}><Td><div className="font-semibold">{org.name}</div><div className="text-xs text-muted-foreground">{org.slug}</div></Td><Td><Pill>{title(org.industry)}</Pill></Td><Td><div className="font-medium">{title(org.subscription?.plan || org.plan)}</div><div className="text-xs text-muted-foreground">{title(org.subscription?.status || "Not started")}</div></Td><Td>{org.usage?.users || 0} users · {org.usage?.locations || 0} locations</Td><Td>{format(org.wallet?.available_credits)}</Td><Td><State value={org.status} /></Td><Td><button onClick={() => open(org)} className="grid h-9 w-9 place-items-center rounded-lg border hover:bg-secondary"><CaretRight /></button></Td></tr>)}</tbody></table></div>{!data.items?.length && <Empty text="No organizations match these filters." />}</div>}
    {selected && <Drawer title={selected.name} close={() => { setSelected(null); setWorkspace(null); }}>{loadingDetail || !workspace ? <PageSkeleton /> : <OrgWorkspace data={workspace} toggle={toggle} refresh={() => open(workspace.organization)} />}</Drawer>}
  </div>;
}

function OrgWorkspace({ data, toggle, refresh }) {
  const { organization: org, subscription, usage, wallet } = data; const [tab, setTab] = useState("summary");
  const pending = usePendingAction(); const [action, setAction] = useState(null);
  const revoke = (user) => pending.run(`revoke:${user.id}`, async () => { try { await api.post(`/super-admin/organizations/${org.id}/users/${user.id}/revoke-sessions`); toast.success("Sessions closed"); } catch (error) { toast.error(message(error)); } });
  const toggleUser = (person) => pending.run(`user:${person.id}`, async () => { try { await api.post(`/super-admin/organizations/${org.id}/users/${person.id}/${person.is_active ? "suspend" : "restore"}`); toast.success(person.is_active ? "User suspended" : "User restored"); refresh(); } catch (error) { toast.error(message(error)); } });
  return <div><div className="rounded-2xl bg-primary p-5 text-primary-foreground"><div className="flex justify-between gap-3"><div><div className="text-xs uppercase tracking-widest text-primary-foreground/55">{title(org.industry)} · {org.slug}</div><div className="mt-2 font-display text-3xl">{org.name}</div><div className="mt-3"><State value={org.status} dark /></div></div><Button variant="outline" className="border-primary-foreground/25 bg-transparent text-primary-foreground hover:bg-primary-foreground/10" onClick={toggle}>{org.status === "suspended" ? "Restore" : "Suspend"}</Button></div></div>
    <div className="flex gap-1 overflow-x-auto py-4">{["summary", "users", "invoices", "access", "history"].map((item) => <button key={item} onClick={() => setTab(item)} className={`rounded-lg px-3 py-2 text-xs font-medium capitalize ${tab === item ? "bg-accent text-accent-foreground" : "bg-secondary"}`}>{item}</button>)}</div>
    {tab === "summary" && <div className="space-y-4"><div className="grid grid-cols-2 gap-3"><SmallMetric label="Current plan" value={title(subscription?.plan || org.plan)} /><SmallMetric label="AI credits" value={format(wallet.available_credits)} /><SmallMetric label="Clients" value={format(usage.clients)} /><SmallMetric label="Team" value={format(usage.employees)} /><SmallMetric label="Locations" value={format(usage.locations)} /><SmallMetric label="Storage" value={bytes(usage.storage_bytes)} /></div><Panel title="Included access"><div className="grid grid-cols-2 gap-2">{Object.entries(data.entitlements?.values || {}).filter(([key, value]) => key.startsWith("module.") && value).map(([key]) => <div key={key} className="flex items-center gap-2 text-sm"><CheckCircle className="text-positive" />{title(key.split(".")[1])}</div>)}</div></Panel></div>}
    {tab === "users" && <div className="space-y-2">{data.users.map((person) => <div key={person.id} className="rounded-xl border p-3"><div className="flex items-center justify-between"><div><div className="font-medium">{person.first_name} {person.last_name}</div><div className="text-xs text-muted-foreground">{person.email}</div></div><State value={person.is_active ? "active" : "suspended"} /></div><div className="mt-3 flex flex-wrap gap-2"><Button variant="outline" size="sm" loading={pending.isPending(`revoke:${person.id}`)} loadingText="Closing..." onClick={() => revoke(person)}>Close sessions</Button><Button variant="outline" size="sm" loading={pending.isPending(`user:${person.id}`)} loadingText="Updating..." onClick={() => toggleUser(person)}>{person.is_active ? "Suspend" : "Restore"}</Button>{person.is_active && <Button variant="outline" size="sm" onClick={() => setAction({ type: "transfer", person })}>Make owner</Button>}</div></div>)}</div>}
    {tab === "invoices" && <div className="space-y-2">{data.invoices.map((invoice) => <div className="flex justify-between rounded-xl border p-3" key={invoice.id}><div><div className="font-medium">{invoice.invoice_number || "Invoice"}</div><div className="text-xs text-muted-foreground">{date(invoice.created_at)}</div></div><div className="text-right"><div className="font-semibold">{money(invoice.amount_paise)}</div><State value={invoice.status} /></div></div>)}{!data.invoices.length && <Empty text="No invoices yet." />}</div>}
    {tab === "access" && <div className="space-y-3"><Panel title="Current plan version"><Signal label="Billing interval" value={title(subscription?.billing_interval)} /><Signal label="Plan version" value={data.entitlements?.plan?.version || "Original"} /><Signal label="Temporary adjustments" value={data.overrides?.filter((row) => row.is_active).length || 0} /></Panel><PlanAssignmentPanel organization={org} subscription={subscription} refresh={refresh} /></div>}
    {tab === "history" && <div className="space-y-2">{data.audit.map((event) => <Event key={event.id} event={event} />)}<div className="mt-6 rounded-2xl border border-danger/30 bg-danger/5 p-4"><div className="font-display text-lg font-bold text-danger">Organization removal</div><p className="mt-1 text-xs text-muted-foreground">Access stops immediately. Permanent removal requires another authorized person to approve it, and required records remain sealed until their retention period ends.</p><Button variant="destructive" size="sm" className="mt-4" onClick={() => setAction({ type: "delete" })}>Shut down and request removal</Button></div></div>}
    <OrganizationActionDialog action={action} organization={org} close={() => setAction(null)} refresh={refresh} />
  </div>;
}

function OrganizationActionDialog({ action, organization, close, refresh }) {
  const idempotency = useStableIdempotencyKey();
  useEffect(() => { if (action) idempotency.reset(); }, [action, idempotency.reset]);
  if (!action) return null;
  const transfer = action.type === "transfer";
  const baseSchema = transfer ? ownerTransferSchema : organizationDeletionSchema;
  const schema = baseSchema.superRefine((values, context) => {
    if (values.confirmation !== organization.slug) {
      context.addIssue({ code: "custom", path: ["confirmation"], message: `Type ${organization.slug} exactly` });
    }
  });
  const submit = async (values) => {
    if (transfer) {
      await api.post(`/super-admin/organizations/${organization.id}/transfer-owner`, {
        new_owner_user_id: action.person.id, reason: values.reason, mfa_code: values.mfa_code,
      });
      toast.success("Ownership transferred and sessions closed");
    } else {
      await api.post(`/super-admin/organizations/${organization.id}/deletion`, {
        reason: values.reason, mfa_code: values.mfa_code, idempotency_key: idempotency.current(),
      });
      toast.success("Organization shut down; deletion is waiting for approval");
    }
    await refresh();
  };
  return <ValidatedActionDialog
    open
    onOpenChange={(open) => { if (!open) close(); }}
    resetKey={`${action.type}:${action.person?.id || organization.id}`}
    title={transfer ? `Transfer ownership to ${action.person.first_name}` : `Shut down ${organization.name}`}
    description={transfer ? "The new owner receives full organization authority." : "This starts the independently approved organization-removal workflow."}
    impact={transfer ? "The current owner loses ownership and all active sessions are closed." : "Workspace access stops immediately. Retained records are not silently erased."}
    variant="destructive"
    schema={schema}
    defaultValues={{
      ...(transfer ? { new_owner_user_id: action.person.id } : {}), reason: "", mfa_code: "", confirmation: "",
    }}
    fields={[
      { name: "reason", label: transfer ? "Transfer reason" : "Removal reason", type: "textarea", maxLength: transfer ? 1000 : 2000 },
      { name: "mfa_code", label: "Authenticator code", type: "password", inputMode: "numeric", autoComplete: "one-time-code", maxLength: 64 },
      { name: "confirmation", label: `Type ${organization.slug} to confirm`, autoComplete: "off" },
    ]}
    submitLabel={transfer ? "Transfer ownership" : "Shut down and request removal"}
    loadingText={transfer ? "Transferring..." : "Submitting..."}
    onSubmit={submit}
  />;
}

function PlanAssignmentPanel({ organization, subscription, refresh }) {
  const plans = useLoad("/super-admin/plans", []); const features = useLoad("/super-admin/features", []);
  const published = plans.data.flatMap((plan) => { const version = plan.versions?.find((item) => item.status === "published"); return version ? [[version.id, `${plan.name} · Version ${version.version}`]] : []; });
  const [planId, setPlanId] = useState(""); const [interval, setInterval] = useState("monthly"); const [timing, setTiming] = useState("immediate"); const [reason, setReason] = useState("");
  const [featureCode, setFeatureCode] = useState(""); const [overrideValue, setOverrideValue] = useState(""); const [overrideReason, setOverrideReason] = useState("");
  const selectedFeature = features.data.find((item) => item.code === featureCode);
  const assignmentValid = Boolean(planId && reason.trim().length >= 5);
  const overrideValid = Boolean(
    featureCode
    && overrideReason.trim().length >= 8
    && (selectedFeature?.value_type === "boolean" ? ["true", "false"].includes(overrideValue) : isValidNumber(overrideValue, { optional: true })),
  );
  const assign = async () => { if (!assignmentValid) return; try { await api.post(`/super-admin/organizations/${organization.id}/plan`, { plan_version_id: planId, billing_interval: interval, change_timing: timing, reason: reason.trim(), version: subscription?.version || 1, idempotency_key: crypto.randomUUID() }); toast.success(timing === "cycle_end" ? "Plan change scheduled" : "Plan updated"); refresh(); } catch (error) { toast.error(message(error)); } };
  const override = async () => { if (!overrideValid) return; const value = selectedFeature?.value_type === "boolean" ? overrideValue === "true" : overrideValue === "" ? null : Number(overrideValue); try { await api.post(`/super-admin/organizations/${organization.id}/overrides`, { feature_code: featureCode, value, reason: overrideReason.trim(), starts_at: new Date().toISOString(), ends_at: new Date(Date.now() + 30 * 86400000).toISOString(), version: 1 }); toast.success("Temporary adjustment granted for 30 days"); refresh(); } catch (error) { toast.error(message(error)); } };
  return <><Panel title="Change plan"><FormSelect label="Plan version" value={planId} set={setPlanId} options={published} /><div className="grid grid-cols-2 gap-3"><FormSelect label="Billing" value={interval} set={setInterval} options={[["monthly", "Monthly"], ["annual", "Annual"]]} /><FormSelect label="When" value={timing} set={setTiming} options={[["immediate", "Immediately"], ["cycle_end", "At cycle end"]]} /></div><FieldLabel text="Business reason"><Input value={reason} onChange={(event) => setReason(event.target.value)} /></FieldLabel><Button className="w-full mt-4" disabled={!assignmentValid} onClick={assign}>Apply plan change</Button></Panel><Panel title="Temporary adjustment"><FormSelect label="Feature or limit" value={featureCode} set={(value) => { setFeatureCode(value); setOverrideValue(""); }} options={features.data.map((item) => [item.code, item.name])} />{selectedFeature?.value_type === "boolean" ? <FormSelect label="Availability" value={overrideValue} set={setOverrideValue} options={[["true", "Included"], ["false", "Not included"]]} /> : <FieldLabel text="Temporary limit"><Input type="number" min="0" value={overrideValue} onChange={(event) => setOverrideValue(event.target.value)} placeholder="Leave blank for unlimited" /></FieldLabel>}<FieldLabel text="Reason"><Input value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} /></FieldLabel><Button variant="outline" className="w-full mt-4" disabled={!overrideValid} onClick={override}>Grant for 30 days</Button></Panel></>;
}

function Plans() {
  const { data, loading, error, reload } = useLoad("/super-admin/plans", []);
  const features = useLoad("/super-admin/features", []);
  const [editing, setEditing] = useState(null);
  const [updating, setUpdating] = useState("");
  const [confirmation, setConfirmation] = useState(null);
  const publishKey = useStableIdempotencyKey();
  useEffect(() => { if (confirmation?.type === "publish") publishKey.reset(); }, [confirmation, publishKey.reset]);
  const clone = async (plan) => {
    const latest = plan.versions?.[0];
    try {
      await api.post(`/super-admin/plans/${plan.id}/versions`, {
        monthly_price_paise: latest?.monthly_price_paise,
        annual_price_paise: latest?.annual_price_paise,
        annual_discount_bps: latest?.annual_discount_bps || 0,
        tax_enabled: latest?.tax_enabled ?? true,
        gst_rate_bps: latest?.gst_rate_bps || 1800,
        included_ai_credits: latest?.included_ai_credits || 0,
        support_level: latest?.support_level || "standard",
        ai_tier: latest?.ai_tier || "basic",
        entitlements: latest?.entitlements || {},
      });
      toast.success("Draft version created"); reload();
    } catch (error) { toast.error(message(error)); }
  };
  const publish = (version) => setConfirmation({ type: "publish", version });
  const updateAvailability = async (plan, field, value) => {
    setUpdating(`${plan.id}:${field}`);
    try {
      await api.patch(`/super-admin/plans/${plan.id}`, { [field]: value });
      api.invalidate("billing");
      toast.success(plan.slug === "trial" && value === false ? "Trial disabled for new accounts" : "Plan availability updated");
      await reload();
    }
    finally { setUpdating(""); }
  };
  const setAvailability = async (plan, field, value) => {
    if (plan.slug === "trial" && value === false) {
      setConfirmation({ type: "disable_trial", plan, field, value });
      return;
    }
    try { await updateAvailability(plan, field, value); } catch (error) { toast.error(message(error)); }
  };
  const confirmPlanAction = async () => {
    if (confirmation.type === "publish") {
      const { version } = confirmation;
      await api.post(`/super-admin/plans/versions/${version.id}/publish`, { version_lock: version.version_lock, idempotency_key: publishKey.current() });
      api.invalidate("billing");
      toast.success("Plan version published");
      await reload();
      return;
    }
    await updateAvailability(confirmation.plan, confirmation.field, confirmation.value);
  };
  if (loading) return <PageSkeleton />;
  if (error) return <LoadError retry={reload} />;
  return <div className="space-y-6">
    <PageIntro eyebrow="Plans & Features" title="Build offers without breaking promises" text="Control which plans new customers can see and purchase. Published versions remain unchanged for existing subscribers." />
    <div className="grid gap-5 xl:grid-cols-2">{data.map((plan) => {
      const latest = plan.versions?.[0];
      return <div key={plan.id} className="rounded-2xl border bg-card p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div><div className="flex items-center gap-2"><div className="font-display text-2xl font-bold">{plan.name}</div><State value={plan.is_active && plan.is_public ? "live" : "hidden"} /></div><p className="mt-1 text-sm text-muted-foreground">{plan.description}</p></div>
          <Button variant="outline" onClick={() => clone(plan)}>New version</Button>
        </div>
        <PlanAvailabilityControls plan={plan} updating={updating} setAvailability={setAvailability} />
        <div className="mt-5 grid grid-cols-2 gap-3"><SmallMetric label="Monthly" value={latest?.monthly_price_paise == null ? "Custom" : money(latest.monthly_price_paise)} /><SmallMetric label="Annual" value={latest?.annual_price_paise == null ? "Custom" : money(latest.annual_price_paise)} /><SmallMetric label="AI credits" value={format(latest?.included_ai_credits)} /><SmallMetric label="Support" value={title(latest?.support_level)} /></div>
        <div className="mt-4 space-y-2">{plan.versions?.slice(0, 4).map((version) => <div key={version.id} className="flex items-center justify-between rounded-xl bg-surface-subtle px-3 py-2"><div className="text-sm">Version {version.version} <State value={version.status} /></div>{version.status === "draft" && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setEditing({ plan, version })}>Edit</Button><Button size="sm" onClick={() => publish(version)}>Publish</Button></div>}</div>)}</div>
      </div>;
    })}</div>
    {editing && <Drawer title={`${editing.plan.name} / Version ${editing.version.version}`} close={() => setEditing(null)}><PlanEditor version={editing.version} features={features.data} onSaved={() => { setEditing(null); reload(); }} /></Drawer>}
    <ValidatedActionDialog
      open={Boolean(confirmation)}
      onOpenChange={(open) => { if (!open) setConfirmation(null); }}
      resetKey={confirmation?.type}
      title={confirmation?.type === "publish" ? "Publish this plan version?" : "Disable Trial for new accounts?"}
      description={confirmation?.type === "publish" ? "Published pricing and entitlements become available for future assignments." : "New users will need to complete payment before their workspace account is created."}
      impact={confirmation?.type === "publish" ? "Existing customers remain on the version they purchased." : "Existing trial workspaces are unchanged; only future account creation is affected."}
      schema={z.object({})}
      defaultValues={{}}
      submitLabel={confirmation?.type === "publish" ? "Publish version" : "Disable Trial"}
      loadingText={confirmation?.type === "publish" ? "Publishing..." : "Updating..."}
      variant={confirmation?.type === "disable_trial" ? "destructive" : "default"}
      onSubmit={confirmPlanAction}
    />
  </div>;
}

function PlanAvailabilityControls({ plan, updating, setAvailability }) {
  const control = (field, titleText, help) => <label className="flex items-center justify-between gap-3 rounded-lg bg-card px-3 py-2.5 text-sm"><span><span className="block font-medium">{titleText}</span><span className="block text-xs text-muted-foreground">{help}</span></span><input aria-label={`${plan.name} ${titleText.toLowerCase()}`} type="checkbox" className="h-5 w-5 accent-[hsl(var(--primary))]" checked={plan[field]} disabled={updating === `${plan.id}:${field}`} onChange={(event) => setAvailability(plan, field, event.target.checked)} /></label>;
  return <><div className="mt-4 grid gap-2 rounded-xl border bg-surface-subtle p-3 sm:grid-cols-2">{control("is_active", "New signups", "Allow new accounts on this plan")}{control("is_public", "Public pricing", "Show on the landing page")}</div>{plan.slug === "trial" && (!plan.is_active || !plan.is_public) && <div className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-xs text-foreground">Paid checkout is required before any new workspace account is created.</div>}</>;
}

function LegacyPlans() {
  const { data, loading, error, reload } = useLoad("/super-admin/plans", []);
  const features = useLoad("/super-admin/features", []); const [editing, setEditing] = useState(null); const [updating, setUpdating] = useState("");
  const clone = async (plan) => { const latest = plan.versions?.[0]; try { await api.post(`/super-admin/plans/${plan.id}/versions`, { monthly_price_paise: latest?.monthly_price_paise, annual_price_paise: latest?.annual_price_paise, annual_discount_bps: latest?.annual_discount_bps || 0, tax_enabled: latest?.tax_enabled ?? true, gst_rate_bps: latest?.gst_rate_bps || 1800, included_ai_credits: latest?.included_ai_credits || 0, support_level: latest?.support_level || "standard", ai_tier: latest?.ai_tier || "basic", entitlements: latest?.entitlements || {} }); toast.success("Draft version created"); reload(); } catch (error) { toast.error(message(error)); } };
  const publish = async () => { toast.error("The retired plan editor cannot publish versions. Use the current Plans screen."); };
  const setAvailability = async (plan, field, value) => {
    if (plan.slug === "trial" && value === false) { toast.error("Use the current Plans screen to disable Trial safely."); return; }
    setUpdating(`${plan.id}:${field}`);
    try {
      await api.patch(`/super-admin/plans/${plan.id}`, { [field]: value });
      toast.success(plan.slug === "trial" && value === false ? "Trial disabled for new accounts" : "Plan availability updated");
      reload();
    } catch (error) { toast.error(message(error)); }
    finally { setUpdating(""); }
  };
  if (loading) return <PageSkeleton />; if (error) return <LoadError retry={reload} />;
  return <div className="space-y-6"><PageIntro eyebrow="Plans & Features" title="Build offers without breaking promises" text="Published versions stay unchanged for existing subscribers. New versions can be prepared safely as drafts." /><div className="grid gap-5 xl:grid-cols-2">{data.map((plan) => { const latest = plan.versions?.[0]; return <div key={plan.id} className="rounded-2xl border bg-card p-5"><div className="flex justify-between"><div><div className="font-display text-2xl font-bold">{plan.name}</div><p className="mt-1 text-sm text-muted-foreground">{plan.description}</p></div><Button variant="outline" onClick={() => clone(plan)}>New version</Button></div><div className="mt-5 grid grid-cols-2 gap-3"><SmallMetric label="Monthly" value={latest?.monthly_price_paise == null ? "Custom" : money(latest.monthly_price_paise)} /><SmallMetric label="Annual" value={latest?.annual_price_paise == null ? "Custom" : money(latest.annual_price_paise)} /><SmallMetric label="AI credits" value={format(latest?.included_ai_credits)} /><SmallMetric label="Support" value={title(latest?.support_level)} /></div><div className="mt-4 space-y-2">{plan.versions?.slice(0, 4).map((version) => <div key={version.id} className="flex items-center justify-between rounded-xl bg-surface-subtle px-3 py-2"><div className="text-sm">Version {version.version} <State value={version.status} /></div>{version.status === "draft" && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setEditing({ plan, version })}>Edit</Button><Button size="sm" onClick={() => publish(version)}>Publish</Button></div>}</div>)}</div></div>; })}</div>{editing && <Drawer title={`${editing.plan.name} · Version ${editing.version.version}`} close={() => setEditing(null)}><PlanEditor version={editing.version} features={features.data} onSaved={() => { setEditing(null); reload(); }} /></Drawer>}</div>;
}

function PlanEditor({ version, features, onSaved }) {
  const [form, setForm] = useState({ monthly: version.monthly_price_paise == null ? "" : version.monthly_price_paise / 100, annual: version.annual_price_paise == null ? "" : version.annual_price_paise / 100, tax_enabled: version.tax_enabled ?? true, gst_rate: (version.gst_rate_bps || 1800) / 100, included_ai_credits: version.included_ai_credits || 0, support_level: version.support_level || "standard", ai_tier: version.ai_tier || "basic", entitlements: { ...(version.entitlements || {}) } });
  const [saving, setSaving] = useState(false); const set = (key, value) => setForm((current) => ({ ...current, [key]: value })); const setFeature = (code, value) => setForm((current) => ({ ...current, entitlements: { ...current.entitlements, [code]: value } }));
  const valid = isValidNumber(form.monthly, { optional: true })
    && isValidNumber(form.annual, { optional: true })
    && isValidNumber(form.included_ai_credits, { integer: true })
    && (!form.tax_enabled || isValidNumber(form.gst_rate, { max: 100 }))
    && Object.values(form.entitlements).every((value) => typeof value === "boolean" || value == null || isValidNumber(value, { integer: true }));
  const save = async () => { if (!valid || saving) return; setSaving(true); try { await api.patch(`/super-admin/plans/versions/${version.id}`, { monthly_price_paise: form.monthly === "" ? null : Math.round(Number(form.monthly) * 100), annual_price_paise: form.annual === "" ? null : Math.round(Number(form.annual) * 100), annual_discount_bps: version.annual_discount_bps || 0, tax_enabled: form.tax_enabled, gst_rate_bps: Math.round(Number(form.gst_rate || 0) * 100), included_ai_credits: Number(form.included_ai_credits), support_level: form.support_level, ai_tier: form.ai_tier, entitlements: form.entitlements, version_lock: version.version_lock }); toast.success("Plan draft saved"); onSaved(); } catch (error) { toast.error(message(error)); } finally { setSaving(false); } };
  const groups = features.reduce((result, feature) => ({ ...result, [feature.category]: [...(result[feature.category] || []), feature] }), {});
  return <div className="space-y-5">
    <div className="rounded-xl bg-positive/10 p-4 text-sm"><ShieldCheck className="mr-2 inline text-positive" />Changes affect only Clients assigned after this version is published.</div>
    <div className="grid sm:grid-cols-2 gap-3">
      <FieldLabel text="Monthly price before GST"><Input type="number" min="0" value={form.monthly} onChange={(event) => set("monthly", event.target.value)} placeholder="Custom price" /></FieldLabel>
      <FieldLabel text="Annual price before GST"><Input type="number" min="0" value={form.annual} onChange={(event) => set("annual", event.target.value)} placeholder="Custom price" /></FieldLabel>
      <FieldLabel text="Included AI credits"><Input type="number" min="0" value={form.included_ai_credits} onChange={(event) => set("included_ai_credits", event.target.value)} /></FieldLabel>
      <FormSelect label="Support level" value={form.support_level} set={(value) => set("support_level", value)} options={[["self-service", "Self-service"], ["standard", "Standard"], ["priority", "Priority"], ["dedicated", "Dedicated"]]} />
      <FormSelect label="AI capability" value={form.ai_tier} set={(value) => set("ai_tier", value)} options={[["basic", "Everyday assistant"], ["advanced", "Advanced assistant"], ["actions", "Assistant with actions"], ["enterprise", "Enterprise assistant"]]} />
    </div>
    <section className="rounded-2xl border bg-accent/5 p-4">
      <div className="flex items-start justify-between gap-4"><div><h3 className="font-display text-lg font-bold">GST for this plan</h3><p className="mt-1 text-xs text-muted-foreground">This switch belongs only to this version and does not affect other plans.</p></div><input aria-label="Charge GST" className="h-5 w-5 accent-[hsl(var(--accent))]" type="checkbox" checked={form.tax_enabled} onChange={(event) => set("tax_enabled", event.target.checked)} /></div>
      {form.tax_enabled && <div className="mt-4 grid gap-3 sm:grid-cols-2"><FieldLabel text="GST rate (%)"><Input type="number" min="0" max="100" step="0.01" value={form.gst_rate} onChange={(event) => set("gst_rate", event.target.value)} /></FieldLabel><div className="rounded-xl border bg-card p-3 text-sm"><div className="text-xs text-muted-foreground">Monthly total preview</div><div className="mt-1 font-semibold">{form.monthly === "" ? "Custom" : money(Math.round(Number(form.monthly) * 100 * (1 + Number(form.gst_rate || 0) / 100)))}</div></div></div>}
    </section>
    {Object.entries(groups).map(([category, items]) => <section key={category} className="rounded-2xl border p-4"><h3 className="font-display text-lg font-bold">{category}</h3><div className="mt-3 space-y-2">{items.map((feature) => feature.value_type === "boolean" ? <label key={feature.code} className="flex items-center justify-between gap-4 border-b py-2 last:border-0"><div><div className="text-sm font-medium">{feature.name}</div><div className="text-xs text-muted-foreground">{feature.description}</div></div><input className="h-5 w-5 accent-[hsl(var(--accent))]" type="checkbox" checked={Boolean(form.entitlements[feature.code])} onChange={(event) => setFeature(feature.code, event.target.checked)} /></label> : <div key={feature.code} className="flex items-center justify-between gap-4 border-b py-2 last:border-0"><div><div className="text-sm font-medium">{feature.name}</div><div className="text-xs text-muted-foreground">Leave blank for unlimited</div></div><Input className="w-32" type="number" min="0" value={form.entitlements[feature.code] ?? ""} onChange={(event) => setFeature(feature.code, event.target.value === "" ? null : Number(event.target.value))} /></div>)}</div></section>)}
    <div className="sticky bottom-0 flex justify-end border-t bg-background py-4"><Button disabled={!valid} loading={saving} loadingText="Saving..." onClick={save}>Save draft</Button></div>
  </div>;
}

function Billing() {
  const { data, loading, error, reload } = useLoad("/super-admin/billing", {});
  const [refundTarget, setRefundTarget] = useState(null); const idempotency = useStableIdempotencyKey();
  const [gatewayTarget, setGatewayTarget] = useState(null);
  useEffect(() => { if (refundTarget) idempotency.reset(); }, [refundTarget, idempotency.reset]);
  const refundedFor = (payment) => (data.refunds || []).filter((item) => item.payment_id === payment.id && ["requested", "approved", "processed"].includes(item.status)).reduce((total, item) => total + Number(item.amount_paise || 0), 0);
  const remaining = refundTarget ? Math.max(0, Number(refundTarget.amount_paise || 0) - refundedFor(refundTarget)) : 0;
  const activeRefundSchema = refundSchema.superRefine((values, context) => {
    if (values.amount_paise > remaining) context.addIssue({ code: "custom", path: ["amount"], message: `Refund cannot exceed ${money(remaining)}` });
  });
  const refund = async (values) => {
    const response = await api.post(`/super-admin/billing/payments/${refundTarget.id}/refund`, {
      amount_paise: values.amount_paise, reason: values.reason, mfa_code: values.mfa_code, idempotency_key: idempotency.current(),
    });
    const refundMessage = response.data.status === "requested"
      ? "Refund sent for approval"
      : response.data.status === "processed"
        ? "Refund processed"
        : "Refund submitted and awaiting provider confirmation";
    toast.success(refundMessage);
    await reload();
  };
  const switchGateway = async () => {
    await api.put("/super-admin/billing/gateway", {
      provider: gatewayTarget.provider,
      version: data.provider?.version || 1,
    });
    toast.success(`${title(gatewayTarget.provider)} is now active for new checkouts`);
    await reload();
  };
  if (loading) return <PageSkeleton />; if (error) return <LoadError retry={reload} />;
  return <div className="space-y-6"><PageIntro eyebrow="Billing" title="Payments that reconcile cleanly" text="Track invoices, collections, failed payments, refunds, and payment-provider status." /><GatewayPanel gateway={data.provider} select={setGatewayTarget} /><div className="grid md:grid-cols-3 gap-4"><Metric label="Collected" value={money(data.summary?.collected_paise)} accent /><Metric label="Outstanding" value={money(data.summary?.outstanding_paise)} /><Metric label="Failed payments" value={data.summary?.failed || 0} warn={data.summary?.failed > 0} /></div><ApprovalQueue /><Panel title="Recent payments" action={<State value={data.provider?.mode || "not configured"} />}><DataTable headers={["Organization", "Amount", "Provider", "Mode", "Status", ""]} rows={data.payments?.map((payment) => [payment.organization_id?.slice(0, 8), money(payment.amount_paise), title(payment.provider), title(payment.mode), <State value={payment.status} />, payment.status === "captured" || payment.status === "partially_refunded" ? <Button size="sm" variant="outline" onClick={() => setRefundTarget(payment)}>Refund</Button> : null])} empty="No payments recorded yet." /></Panel><Panel title="Invoices"><DataTable headers={["Invoice", "Amount", "Created", "Status"]} rows={data.invoices?.map((invoice) => [invoice.invoice_number || invoice.id.slice(0, 8), money(invoice.amount_paise), date(invoice.created_at), <State value={invoice.status} />])} empty="No invoices yet." /></Panel><ValidatedActionDialog open={Boolean(gatewayTarget)} onOpenChange={(open) => { if (!open) setGatewayTarget(null); }} resetKey={gatewayTarget?.provider} title={`Activate ${title(gatewayTarget?.provider)}?`} description="This changes the provider used when a customer starts a new checkout." impact="Open and historical payments stay bound to their original provider. Cashfree currently supports one-time terms; existing Razorpay recurring subscriptions continue unchanged." schema={z.object({})} defaultValues={{}} fields={[]} submitLabel="Activate gateway" loadingText="Activating..." onSubmit={switchGateway} /><ValidatedActionDialog open={Boolean(refundTarget)} onOpenChange={(open) => { if (!open) setRefundTarget(null); }} resetKey={refundTarget?.id} title="Refund payment" description={`Refund up to ${money(remaining)} from this captured payment.`} impact="The refund is audited and may require independent approval. The original payment record remains immutable." schema={activeRefundSchema} defaultValues={{ amount: "", reason: "", mfa_code: "" }} fields={[{ name: "amount", label: "Refund amount (INR)", inputMode: "decimal", placeholder: "0.00" }, { name: "reason", label: "Refund reason", type: "textarea", maxLength: 1000 }, { name: "mfa_code", label: "Authenticator code", type: "password", inputMode: "numeric", autoComplete: "one-time-code", maxLength: 64 }]} submitLabel="Request refund" loadingText="Processing..." variant="destructive" onSubmit={refund} /></div>;
}

function GatewayPanel({ gateway, select }) {
  return <Panel title="Checkout gateway" action={<State value={`${gateway?.provider || "not configured"} ${gateway?.mode || ""}`} />}>
    <p className="mb-4 max-w-3xl text-sm text-muted-foreground">Choose the provider for new paid signups, one-time plan purchases, and AI-wallet top-ups. API credentials remain server-managed.</p>
    <div className="grid gap-3 md:grid-cols-2">{(gateway?.providers || []).map((provider) => {
      const ready = provider.configured && provider.webhook_configured;
      return <article key={provider.provider} className={`rounded-xl border p-4 ${provider.active ? "border-primary bg-primary/5 ring-1 ring-primary/15" : "bg-card"}`}>
        <div className="flex items-start justify-between gap-3"><div><h4 className="font-semibold">{title(provider.provider)}</h4><p className="mt-1 text-xs text-muted-foreground">{provider.recurring_supported ? "One-time and recurring checkout" : "One-time checkout"} / {title(provider.mode)}</p></div><State value={provider.active ? "active" : ready ? "configured" : "setup_needed"} /></div>
        <div className="mt-4 flex items-center justify-between gap-3 border-t pt-3"><span className="text-xs text-muted-foreground">{ready ? "Credentials and webhook are ready" : "Configure credentials and webhook in the deployment environment"}</span><Button size="sm" variant={provider.active ? "outline" : "default"} disabled={provider.active || !ready} onClick={() => select(provider)}>{provider.active ? "Active" : "Activate"}</Button></div>
      </article>;
    })}</div>
  </Panel>;
}

function ApprovalQueue() {
  const [items, setItems] = useState([]); const [available, setAvailable] = useState(true); const [decisionTarget, setDecisionTarget] = useState(null);
  const load = useCallback(() => api.get("/super-admin/approvals?status=pending").then(({ data }) => { setItems(data); setAvailable(true); }).catch((error) => { if (error.response?.status === 403) setAvailable(false); }), []);
  useEffect(() => { load(); }, [load]);
  const decisionSchema = approvalDecisionSchema.superRefine((values, context) => {
    if (decisionTarget?.item.amount_paise && !values.mfa_code) context.addIssue({ code: "custom", path: ["mfa_code"], message: "Enter your authentication code" });
  });
  const decide = async (values) => {
    const { item, decision } = decisionTarget;
    await api.post(`/super-admin/approvals/${item.id}/${decision}`, { version: item.version, note: values.note || null, mfa_code: values.mfa_code || null });
    toast.success(decision === "approve" ? "Action approved" : "Action rejected");
    await load();
  };
  if (!available) return null;
  return <><Panel title="Approvals waiting"><DataTable headers={["Request", "Amount", "Reason", "Requested", "Decision"]} rows={items.map((item) => [title(item.action_type), item.amount_paise ? money(item.amount_paise) : "—", item.reason, date(item.created_at), <div className="flex gap-2"><Button size="sm" onClick={() => setDecisionTarget({ item, decision: "approve" })}>Approve</Button><Button size="sm" variant="outline" onClick={() => setDecisionTarget({ item, decision: "reject" })}>Reject</Button></div>])} empty="No approvals are waiting." /></Panel><ValidatedActionDialog open={Boolean(decisionTarget)} onOpenChange={(open) => { if (!open) setDecisionTarget(null); }} resetKey={`${decisionTarget?.item.id}:${decisionTarget?.decision}`} title={decisionTarget?.decision === "approve" ? "Approve this request?" : "Reject this request?"} description={decisionTarget ? `${title(decisionTarget.item.action_type)}${decisionTarget.item.amount_paise ? ` for ${money(decisionTarget.item.amount_paise)}` : ""}` : ""} impact={decisionTarget?.decision === "approve" ? "The approved operation may execute immediately and will be permanently audited." : "The requested operation will not run; the decision remains in the audit record."} variant={decisionTarget?.decision === "reject" ? "destructive" : "default"} schema={decisionSchema} defaultValues={{ note: "", mfa_code: "" }} fields={[{ name: "note", label: `${decisionTarget?.decision === "approve" ? "Approval" : "Rejection"} note (optional)`, type: "textarea", maxLength: 1000 }, ...(decisionTarget?.item.amount_paise ? [{ name: "mfa_code", label: "Authenticator code", type: "password", inputMode: "numeric", autoComplete: "one-time-code", maxLength: 64 }] : [])]} submitLabel={decisionTarget?.decision === "approve" ? "Approve request" : "Reject request"} loadingText="Recording..." onSubmit={decide} /></>;
}

function Wallets() {
  const { data, loading, error, reload } = useLoad("/super-admin/wallets", { wallets: [], packs: [] });
  const [editingPack, setEditingPack] = useState(null); const [rechargeTarget, setRechargeTarget] = useState(null); const idempotency = useStableIdempotencyKey();
  useEffect(() => { if (rechargeTarget) idempotency.reset(); }, [rechargeTarget, idempotency.reset]);
  const recharge = async (values) => { await api.post(`/super-admin/wallets/${rechargeTarget.organization.id}/recharge`, { credits: values.credits, reason: values.reason, mfa_code: values.mfa_code, idempotency_key: idempotency.current() }); toast.success("AI credits added"); await reload(); };
  if (loading) return <PageSkeleton />; if (error) return <LoadError retry={reload} />;
  return <div className="space-y-6"><PageIntro eyebrow="AI Wallet" title="Credits with a complete money trail" text="Control recharge packs, tax treatment, cycle grants, and manual adjustments." action={<Button onClick={() => setEditingPack({ name: "", credits: 500, price_paise: 49900, tax_enabled: true, gst_rate_bps: 1800, is_active: true, display_order: data.packs.length })}>New pack</Button>} /><div className="grid gap-4 md:grid-cols-3">{data.packs.map((pack) => <button onClick={() => setEditingPack(pack)} className="rounded-2xl bg-primary p-5 text-left text-primary-foreground transition hover:-translate-y-0.5" key={pack.id}><div className="text-xs uppercase tracking-widest text-accent">Recharge pack</div><div className="mt-2 font-display text-2xl">{pack.name}</div><div className="mt-4 text-3xl font-bold">{format(pack.credits)} credits</div><div className="mt-1 text-primary-foreground/65">{money(pack.price_paise)} {pack.tax_enabled ? `+ ${pack.gst_rate_bps / 100}% GST` : "- no GST"}</div><div className="mt-4 text-xs text-primary-foreground/55">Select to edit</div></button>)}</div><Panel title="Organization wallets"><DataTable headers={["Organization", "Available", "Reserved", "Cycle ends", ""]} rows={data.wallets.map((item) => [<div><div className="font-medium">{item.organization.name}</div><div className="text-xs text-muted-foreground">{item.organization.slug}</div></div>, format(item.wallet.available_credits), format(item.wallet.reserved_credits), date(item.wallet.cycle_end), <Button size="sm" variant="outline" onClick={() => setRechargeTarget(item)}>Add credits</Button>])} empty="No AI wallets found." /></Panel>{editingPack && <Drawer title={editingPack.id ? `Edit ${editingPack.name}` : "New recharge pack"} close={() => setEditingPack(null)}><PackEditor pack={editingPack} saved={() => { setEditingPack(null); reload(); }} /></Drawer>}<ValidatedActionDialog open={Boolean(rechargeTarget)} onOpenChange={(open) => { if (!open) setRechargeTarget(null); }} resetKey={rechargeTarget?.organization.id} title="Add AI credits" description={rechargeTarget ? `Manually credit ${rechargeTarget.organization.name}'s wallet.` : ""} impact="The adjustment is permanent, MFA-protected, and recorded in the wallet ledger and platform audit." schema={walletRechargeSchema} defaultValues={{ credits: "", reason: "", mfa_code: "" }} fields={[{ name: "credits", label: "AI credits", inputMode: "numeric", placeholder: "500" }, { name: "reason", label: "Recharge reason", type: "textarea", maxLength: 500 }, { name: "mfa_code", label: "Authenticator code", type: "password", inputMode: "numeric", autoComplete: "one-time-code", maxLength: 64 }]} submitLabel="Add credits" loadingText="Adding..." onSubmit={recharge} /></div>;
}

function PackEditor({ pack, saved }) {
  const [form, setForm] = useState({ ...pack, price: (pack.price_paise || 0) / 100, gst_rate: (pack.gst_rate_bps || 1800) / 100 });
  const [saving, setSaving] = useState(false);
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const valid = form.name.trim().length > 0
    && form.name.trim().length <= 120
    && isValidNumber(form.credits, { min: 1, integer: true })
    && isValidNumber(form.price, { min: 1 })
    && (!form.tax_enabled || isValidNumber(form.gst_rate, { max: 100 }))
    && isValidNumber(form.display_order || 0, { integer: true });
  const save = async () => { if (!valid || saving) return; setSaving(true); const payload = { name: form.name.trim(), credits: Number(form.credits), price_paise: Math.round(Number(form.price) * 100), tax_enabled: Boolean(form.tax_enabled), gst_rate_bps: Math.round(Number(form.gst_rate || 0) * 100), is_active: Boolean(form.is_active), display_order: Number(form.display_order || 0) }; try { if (pack.id) await api.patch(`/super-admin/wallets/packs/${pack.id}`, payload); else await api.post("/super-admin/wallets/packs", payload); toast.success("Recharge pack saved"); saved(); } catch (error) { toast.error(message(error)); } finally { setSaving(false); } };
  return <div className="space-y-4"><FieldLabel text="Pack name"><Input value={form.name} onChange={(event) => set("name", event.target.value)} /></FieldLabel><div className="grid grid-cols-2 gap-3"><FieldLabel text="Credits"><Input type="number" min="1" value={form.credits} onChange={(event) => set("credits", event.target.value)} /></FieldLabel><FieldLabel text="Price before GST"><Input type="number" min="1" value={form.price} onChange={(event) => set("price", event.target.value)} /></FieldLabel></div><label className="flex items-center justify-between rounded-xl border p-3"><span><span className="block text-sm font-medium">Charge GST</span><span className="text-xs text-muted-foreground">Applies only to this pack</span></span><input type="checkbox" className="h-5 w-5 accent-[hsl(var(--accent))]" checked={form.tax_enabled} onChange={(event) => set("tax_enabled", event.target.checked)} /></label>{form.tax_enabled && <FieldLabel text="GST rate (%)"><Input type="number" min="0" max="100" step="0.01" value={form.gst_rate} onChange={(event) => set("gst_rate", event.target.value)} /></FieldLabel>}<label className="flex gap-2 text-sm"><input type="checkbox" checked={form.is_active} onChange={(event) => set("is_active", event.target.checked)} />Available for purchase</label><Button className="w-full" disabled={!valid} loading={saving} loadingText="Saving..." onClick={save}>Save recharge pack</Button></div>;
}

function PlatformTeam() {
  const { data, loading, error, reload } = useLoad("/super-admin/platform-team", { users: [], roles: [] });
  const [addOpen, setAddOpen] = useState(false); const pending = usePendingAction();
  const defaultRole = data.roles.find((item) => item.slug === "read-only") || data.roles[0];
  const add = async (values) => { await api.post("/super-admin/platform-team", values); toast.success("Team member added. They can verify their account to continue."); await reload(); };
  const changeRole = (person, roleId) => pending.run(`role:${person.id}`, async () => { try { await api.put(`/super-admin/platform-team/${person.id}/role`, { role_id: roleId }); toast.success("Platform role updated"); await reload(); } catch (error) { toast.error(message(error)); } });
  if (loading) return <PageSkeleton />; if (error) return <LoadError retry={reload} />;
  return <div className="space-y-6"><PageIntro eyebrow="Platform Team" title="Clear responsibility, limited authority" text="Operations, Support, Finance, and Read-only roles keep platform access focused." action={<Button disabled={!defaultRole} onClick={() => setAddOpen(true)}>Add team member</Button>} /><div className="grid gap-4 lg:grid-cols-3">{data.roles.map((role) => <div key={role.id} className="rounded-2xl border bg-card p-5"><ShieldCheck className="text-accent" size={24} /><div className="mt-3 font-display text-xl font-bold">{role.name}</div><p className="mt-1 text-sm text-muted-foreground">{role.description}</p><div className="mt-4 text-xs">{role.permissions.length} responsibilities</div></div>)}</div><Panel title="Team members"><DataTable headers={["Name", "Email", "Role", "Status"]} rows={data.users.map((person) => [`${person.first_name} ${person.last_name}`, person.email, <select aria-label={`Role for ${person.first_name}`} className="rounded-lg border bg-background px-2 py-1 disabled:opacity-60" value={person.roles?.[0]?.id || ""} disabled={pending.isPending(`role:${person.id}`)} onChange={(event) => changeRole(person, event.target.value)}>{data.roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select>, <State value={person.is_active ? "active" : "suspended"} />])} empty="No platform team members." /></Panel><ValidatedActionDialog open={addOpen} onOpenChange={setAddOpen} resetKey={defaultRole?.id} title="Add platform team member" description="Invite a verified work email with the least authority needed for their role." impact="The person can access platform-level data allowed by the selected role after account verification." schema={platformTeamSchema} defaultValues={{ email: "", first_name: "", last_name: "", role_id: defaultRole?.id || "" }} fields={[{ name: "email", label: "Work email", type: "email", autoComplete: "email" }, { name: "first_name", label: "First name", autoComplete: "given-name" }, { name: "last_name", label: "Last name (optional)", autoComplete: "family-name" }, { name: "role_id", label: "Platform role", type: "select", options: data.roles.map((role) => [role.id, role.name]) }]} submitLabel="Add team member" loadingText="Adding..." onSubmit={add} /></div>;
}

function Support() {
  const orgs = useLoad("/super-admin/organizations?limit=100", { items: [] }); const sessions = useLoad("/super-admin/support-sessions", []);
  const [orgId, setOrgId] = useState(""); const [users, setUsers] = useState([]); const [userId, setUserId] = useState(""); const [reason, setReason] = useState(""); const [ticket, setTicket] = useState(""); const [mode, setMode] = useState("read_only");
  useEffect(() => { if (!orgId) return; api.get(`/super-admin/organizations/${orgId}`).then(({ data }) => setUsers(data.users.filter((person) => person.is_active))).catch(() => setUsers([])); }, [orgId]);
  const valid = Boolean(orgId && userId && ticket.trim().length >= 3 && reason.trim().length >= 8);
  const start = async () => { if (!valid) return; try { const { data } = await api.post("/super-admin/support-sessions", { organization_id: orgId, target_user_id: userId, reason: reason.trim(), ticket_reference: ticket.trim(), mode }); if (data.session_token) { sessionStorage.setItem("edvatiq.support_session", data.session_token); toast.success("Support session ready for 30 minutes"); } else toast.success("Temporary changes sent for approval"); sessions.reload(); } catch (error) { toast.error(message(error)); } };
  return <div className="space-y-6"><PageIntro eyebrow="Support" title="Help without invisible access" text="Every support visit has a business, target user, reason, ticket, expiry, and permanent audit trail." /><div className="grid xl:grid-cols-[420px_1fr] gap-5"><Panel title="Start a support session"><FormSelect label="Organization" value={orgId} set={setOrgId} options={orgs.data.items?.map((org) => [org.id, org.name]) || []} /><FormSelect label="Work as" value={userId} set={setUserId} options={users.map((person) => [person.id, `${person.first_name} ${person.last_name}`])} /><FieldLabel text="Ticket reference"><Input value={ticket} onChange={(event) => setTicket(event.target.value)} /></FieldLabel><FieldLabel text="Why access is needed"><textarea className="w-full min-h-24 border rounded-lg p-3 text-sm" value={reason} onChange={(event) => setReason(event.target.value)} /></FieldLabel><FormSelect label="Access" value={mode} set={setMode} options={[["read_only", "View only"], ["limited_write", "Temporary changes (approval required)"]]} /><Button className="w-full mt-4" disabled={!valid} onClick={start}>Start session</Button></Panel><Panel title="Recent support sessions"><DataTable headers={["Ticket", "Access", "Started", "Status"]} rows={sessions.data.map((row) => [row.ticket_reference, row.mode === "read_only" ? "View only" : "Temporary changes", date(row.created_at), <State value={row.status} />])} empty="No support sessions yet." /></Panel></div></div>;
}

function Operations() {
  const { data, loading, error, reload } = useLoad("/super-admin/operations", {});
  const retry = async (job) => { try { await api.post(`/super-admin/operations/jobs/${job.id}/retry`); toast.success("Work queued again"); reload(); } catch (error) { toast.error(message(error)); } };
  if (loading) return <PageSkeleton />; if (error) return <LoadError retry={reload} />;
  return <div className="space-y-6"><PageIntro eyebrow="Operations" title="Problems become actionable queues" text="See service health and recover failed work without exposing secrets or error internals." /><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Object.entries(data.health || {}).map(([key, value]) => <div className="rounded-2xl border bg-card p-4" key={key}><State value={value} /><div className="mt-3 font-medium">{title(key)}</div></div>)}</div><Panel title="Background work"><DataTable headers={["Type", "Organization", "Attempts", "Status", ""]} rows={data.jobs?.map((job) => [title(job.kind), job.organization_id.slice(0, 8), job.attempts, <State value={job.status} />, job.status === "failed" || job.status === "cancelled" ? <Button size="sm" variant="outline" onClick={() => retry(job)}><ArrowClockwise className="mr-1" />Retry</Button> : null])} empty="No background work." /></Panel><div className="grid gap-5 lg:grid-cols-2"><Panel title="Client communications"><Signal label="Waiting" value={data.messages?.filter((row) => row.status === "queued").length || 0} /><Signal label="Failed" value={data.messages?.filter((row) => row.status === "failed").length || 0} /></Panel><Panel title="Document processing"><Signal label="Waiting" value={data.documents?.filter((row) => row.status === "pending").length || 0} /><Signal label="Needs attention" value={data.documents?.filter((row) => row.status === "failed").length || 0} /></Panel></div></div>;
}

function Audit() {
  const [query, setQuery] = useState(""); const { data, loading, error, reload } = useLoad(`/super-admin/audit${query ? `?q=${encodeURIComponent(query)}` : ""}`, []);
  return <div className="space-y-6"><PageIntro eyebrow="Audit" title="A reliable record of important changes" text="Platform and tenant activity stays attributable to the person who performed it." /><div className="relative max-w-lg"><MagnifyingGlass className="absolute left-3 top-3" /><Input className="bg-card pl-10" placeholder="Search activity" value={query} onChange={(event) => setQuery(event.target.value)} /></div>{loading ? <TableSkeleton /> : error ? <LoadError retry={reload} /> : <div className="space-y-2 rounded-2xl border bg-card p-4">{data.map((event) => <Event key={event.id} event={event} />)}</div>}</div>;
}

function Settings() {
  const { data, loading, error, reload } = useLoad("/super-admin/settings", []);
  if (loading) return <PageSkeleton />; if (error) return <LoadError retry={reload} />;
  const labels = { financial_approvals: ["Financial approvals", "Controls when a second person must approve a money-related action."], retention: ["Record retention", "Controls how long required financial and care records are sealed before removal."] };
  return <div className="space-y-6"><PageIntro eyebrow="Settings" title="Platform policies in one place" text="Sensitive provider keys stay on the server. This page contains only safe operating policies." /><div className="grid lg:grid-cols-3 gap-5">{data.filter((row) => row.key !== "payment_gateway").map((row) => row.key === "ai_credit_policy" ? <AICreditPolicyCard key={row.id} row={row} reload={reload} /> : row.key === "ai_models" ? <AIModelsCard key={row.id} row={row} reload={reload} /> : <PolicyCard key={row.id} row={row} label={labels[row.key]} reload={reload} />)}</div></div>;
}

function AIModelsCard({ row, reload }) {
  const [values, setValues] = useState(row.value || {}); const [saving, setSaving] = useState(false);
  const stages = [["planner", "Planner"], ["synthesis", "Answer"], ["repair", "Grounding repair"]];
  const valid = stages.every(([key]) => /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$/.test(String(values[key] || "").trim()));
  const save = async () => { if (!valid || saving) return; setSaving(true); try { await api.put(`/super-admin/settings/${row.key}`, { value: Object.fromEntries(stages.map(([key]) => [key, values[key].trim()])), version: row.version }); toast.success("AI execution models saved"); reload(); } catch (error) { toast.error(message(error)); } finally { setSaving(false); } };
  return <div className="rounded-2xl border bg-card p-5"><Robot className="text-accent" size={24} /><h2 className="mt-3 font-display text-xl font-bold">AI execution models</h2><p className="mt-2 text-sm text-muted-foreground">Use a small planner and a capable answer model. Repair runs only after high-risk verification fails.</p><div className="mt-4 space-y-3">{stages.map(([key, label]) => <FieldLabel key={key} text={label}><Input value={values[key] || ""} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))} /></FieldLabel>)}</div><Button variant="outline" className="mt-4 w-full" disabled={!valid} loading={saving} loadingText="Saving..." onClick={save}>Save models</Button></div>;
}

function AICreditPolicyCard({ row, reload }) {
  const [values, setValues] = useState(row.value); const [saving, setSaving] = useState(false);
  const updateLimit = (key, value) => setValues((current) => ({ ...current, route_max_credits: { ...current.route_max_credits, [key]: Number(value) } }));
  const valid = ["business", "analytics", "knowledge", "action"].every((key) => isValidNumber(values.route_max_credits?.[key], { min: 1, integer: true }));
  const save = async () => { if (!valid || saving) return; setSaving(true); try { await api.put(`/super-admin/settings/${row.key}`, { value: values, version: row.version }); toast.success("AI credit policy saved"); reload(); } catch (error) { toast.error(message(error)); } finally { setSaving(false); } };
  const limits = values.route_max_credits || {};
  return <div className="rounded-2xl border bg-card p-5"><Robot className="text-accent" size={24} /><h2 className="mt-3 font-display text-xl font-bold">AI credit protection</h2><p className="mt-2 text-sm text-muted-foreground">Sets a maximum charge for each type of request. Actual usage can be lower.</p><div className="mt-4 space-y-3"><FieldLabel text="Everyday question maximum"><Input type="number" min="1" value={limits.business || 1} onChange={(event) => updateLimit("business", event.target.value)} /></FieldLabel><FieldLabel text="Business analysis maximum"><Input type="number" min="1" value={limits.analytics || 1} onChange={(event) => updateLimit("analytics", event.target.value)} /></FieldLabel><FieldLabel text="Document answer maximum"><Input type="number" min="1" value={limits.knowledge || 1} onChange={(event) => updateLimit("knowledge", event.target.value)} /></FieldLabel><FieldLabel text="Business action maximum"><Input type="number" min="1" value={limits.action || 1} onChange={(event) => updateLimit("action", event.target.value)} /></FieldLabel></div><Button variant="outline" className="mt-4 w-full" disabled={!valid} loading={saving} loadingText="Saving..." onClick={save}>Save policy</Button></div>;
}

function PolicyCard({ row, label, reload }) {
  const [values, setValues] = useState(row.value); const [saving, setSaving] = useState(false);
  const valid = Object.values(values).every((value) => typeof value === "boolean" || isValidNumber(value));
  const save = async () => { if (!valid || saving) return; const normalized = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, typeof value === "boolean" ? value : Number(value)])); setSaving(true); try { await api.put(`/super-admin/settings/${row.key}`, { value: normalized, version: row.version }); toast.success("Policy saved"); reload(); } catch (error) { toast.error(message(error)); } finally { setSaving(false); } };
  return <div className="rounded-2xl border bg-card p-5"><Gear className="text-accent" size={24} /><h2 className="mt-3 font-display text-xl font-bold">{label?.[0] || title(row.key)}</h2><p className="mt-2 text-sm text-muted-foreground">{label?.[1] || "Platform operating policy"}</p><div className="mt-4 space-y-3">{Object.entries(values).map(([key, value]) => <label key={key} className="block"><span className="text-xs text-muted-foreground">{title(key)}</span>{typeof value === "boolean" ? <input type="checkbox" className="ml-3 accent-[hsl(var(--accent))]" checked={value} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.checked }))} /> : <Input className="mt-1" type="number" min="0" value={value} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))} />}</label>)}</div><Button variant="outline" className="mt-4 w-full" disabled={!valid} loading={saving} loadingText="Saving..." onClick={save}>Save policy</Button></div>;
}

function MfaSetup({ onComplete }) {
  const [setup, setSetup] = useState(null); const [code, setCode] = useState(""); const [recovery, setRecovery] = useState([]); const [loading, setLoading] = useState(false);
  const begin = async () => { setLoading(true); try { const { data } = await api.post("/super-admin/security/mfa/enroll"); setSetup(data); } catch (error) { toast.error(message(error)); } finally { setLoading(false); } };
  const confirm = async () => { setLoading(true); try { const { data } = await api.post("/super-admin/security/mfa/confirm", { code }); setRecovery(data.recovery_codes); } catch (error) { toast.error(message(error)); } finally { setLoading(false); } };
  return <div className="fixed inset-0 z-[100] grid place-items-center bg-foreground/70 p-4 backdrop-blur-sm"><div className="w-full max-w-lg rounded-3xl bg-background p-7 text-foreground shadow-2xl"><div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary text-primary-foreground"><ShieldCheck size={25} /></div>{recovery.length ? <><h2 className="mt-5 font-display text-3xl font-bold">Keep your recovery codes safe</h2><p className="mt-2 text-sm text-muted-foreground">Each code can be used once if your phone is unavailable.</p><div className="my-5 grid grid-cols-2 gap-2">{recovery.map((item) => <code className="rounded-lg bg-secondary p-2 text-center" key={item}>{item}</code>)}</div><Button className="w-full" onClick={onComplete}>I have saved them</Button></> : <><div className="mt-5 text-xs uppercase tracking-widest text-accent">Account protection</div><h2 className="mt-2 font-display text-3xl font-bold">Protect platform access</h2><p className="mt-2 text-sm text-muted-foreground">Platform accounts use an authenticator app. This setup is required before the control center can be used.</p>{!setup ? <Button className="mt-6 w-full" disabled={loading} onClick={begin}>Set up authenticator</Button> : <div className="mt-5 space-y-4"><div className="rounded-xl bg-secondary p-4"><div className="text-xs text-muted-foreground">Add this setup key in your authenticator app</div><code className="mt-2 block break-all font-semibold tracking-wider">{setup.secret}</code></div><FieldLabel text="6-digit code"><Input inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} /></FieldLabel><Button className="w-full" disabled={loading || code.length !== 6} onClick={confirm}>Verify and continue</Button></div>}</>}</div></div>;
}

function PageIntro({ eyebrow, title: heading, text, action }) { return <header className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><div className="overline text-accent">{eyebrow}</div><h2 className="mt-1 font-display text-3xl font-bold md:text-4xl">{heading}</h2><p className="mt-2 max-w-2xl text-muted-foreground">{text}</p></div>{action}</header>; }
function Metric({ label, value, note, accent, warn }) { return <div className={`rounded-2xl border p-5 ${accent ? "border-primary bg-primary text-primary-foreground" : warn ? "border-warning/30 bg-warning-soft" : "bg-card"}`}><div className={`text-sm ${accent ? "text-primary-foreground/65" : "text-muted-foreground"}`}>{label}</div><div className="mt-3 font-display text-3xl font-bold">{value ?? 0}</div>{note && <div className={`mt-2 text-xs ${accent ? "text-primary-foreground/55" : "text-muted-foreground"}`}>{note}</div>}</div>; }
function SmallMetric({ label, value }) { return <div className="rounded-xl bg-surface-subtle p-3"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 font-semibold">{value ?? "Not available"}</div></div>; }
function Panel({ title: heading, action, children }) { return <section className="overflow-hidden rounded-2xl border bg-card p-5 text-card-foreground"><div className="mb-4 flex items-center justify-between"><h3 className="font-display text-xl font-bold">{heading}</h3>{action}</div>{children}</section>; }
function Signal({ label, value, state }) { return <div className="flex items-center justify-between border-b py-2.5 text-sm last:border-0"><span className="text-muted-foreground">{label}</span><span className={`font-semibold ${state === "warn" ? "text-warning" : state === "good" ? "text-positive" : ""}`}>{value}</span></div>; }
function State({ value, dark }) { const good = ["active", "healthy", "captured", "paid", "published", "processed", "configured", "local_mode"].includes(value); const bad = ["failed", "past_due", "suspended", "attention", "setup_needed", "cancelled"].includes(value); return <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] uppercase tracking-wide ${dark ? "border-primary-foreground/15 bg-primary-foreground/10 text-primary-foreground" : good ? "status-positive" : bad ? "status-warning" : "status-neutral"}`}>{title(value)}</span>; }
function StatusDot({ good, label }) { return <div className="hidden items-center gap-2 text-xs sm:flex"><span className={`h-2 w-2 rounded-full ${good ? "bg-positive" : "bg-warning"}`} />{label}</div>; }
function Pill({ children }) { return <span className="rounded-lg bg-secondary px-2 py-1 text-xs">{children}</span>; }
function DataTable({ headers, rows = [], empty }) { return <div className="-mx-5 -mb-5 overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead><tr className="bg-secondary text-left">{headers.map((item) => <Th key={item}>{item}</Th>)}</tr></thead><tbody>{rows.map((row, index) => <tr className="border-t" key={index}>{row.map((cell, cellIndex) => <Td key={cellIndex}>{cell}</Td>)}</tr>)}</tbody></table>{!rows.length && <Empty text={empty} />}</div>; }
function Th({ children }) { return <th className="px-4 py-3 font-medium text-muted-foreground">{children}</th>; }
function Td({ children }) { return <td className="px-4 py-3">{children}</td>; }
function Empty({ text }) { return <div className="p-10 text-center text-sm text-muted-foreground">{text}</div>; }
function Drawer({ title: heading, close, children }) { return <><button className="fixed inset-0 z-40 bg-foreground/35" onClick={close} aria-label="Close" /><aside className="premium-scrollbar fixed inset-y-0 right-0 z-50 w-full max-w-2xl overflow-y-auto bg-background text-foreground shadow-2xl"><header className="sticky top-0 z-10 flex justify-between border-b bg-background/95 p-4 backdrop-blur"><div className="font-display text-xl font-bold">{heading}</div><button onClick={close} className="grid h-9 w-9 place-items-center rounded-xl border"><X /></button></header><div className="p-5">{children}</div></aside></>; }
function Event({ event }) { return <div className="flex gap-3 rounded-xl border p-3"><div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary"><Scroll /></div><div className="min-w-0"><div className="text-sm font-medium">{title(event.action?.replaceAll(".", " "))}</div><div className="mt-1 text-xs text-muted-foreground">{dateTime(event.created_at)}{event.resource_type ? ` · ${title(event.resource_type)}` : ""}</div></div></div>; }
function FormSelect({ label, value, set, options }) { return <FieldLabel text={label}><select className="h-10 w-full rounded-lg border bg-background px-3 text-sm" value={value} onChange={(event) => set(event.target.value)}><option value="">Choose {label.toLowerCase()}</option>{options.map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select></FieldLabel>; }
function FieldLabel({ text, children }) { return <label className="block mt-3"><span className="text-xs font-medium">{text}</span><div className="mt-1.5">{children}</div></label>; }
function isValidNumber(value, { min = 0, max = Number.POSITIVE_INFINITY, integer = false, optional = false } = {}) { if (value === "" || value == null) return optional; const number = Number(value); return Number.isFinite(number) && number >= min && number <= max && (!integer || Number.isInteger(number)); }
function PageSkeleton() { return <div className="animate-pulse space-y-5"><div className="h-10 w-1/3 rounded-xl bg-secondary" /><div className="grid gap-4 md:grid-cols-4">{[1, 2, 3, 4].map((item) => <div className="h-32 rounded-2xl bg-card" key={item} />)}</div><div className="h-72 rounded-2xl bg-card" /></div>; }
function TableSkeleton() { return <div className="h-80 animate-pulse rounded-2xl bg-card" />; }
function LoadError({ retry }) { return <div className="rounded-2xl border bg-card p-10 text-center"><Warning size={30} className="mx-auto text-warning" /><div className="mt-3 font-display text-xl">This section could not be loaded</div><Button variant="outline" className="mt-4" onClick={retry}><ArrowClockwise className="mr-2" />Try again</Button></div>; }
function title(value) { if (value == null) return "—"; return String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function money(paise) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format((Number(paise) || 0) / 100); }
function format(value) { return new Intl.NumberFormat("en-IN").format(Number(value) || 0); }
function bytes(value) { const size = Number(value) || 0; return size > 1e9 ? `${(size / 1e9).toFixed(1)} GB` : size > 1e6 ? `${(size / 1e6).toFixed(1)} MB` : `${Math.round(size / 1000)} KB`; }
function date(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "—"; }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(value)) : "—"; }
function message(error) { const detail = error.response?.data?.detail; if (Array.isArray(detail)) return detail.map((item) => item.msg).join(", "); return typeof detail === "string" ? detail : "That action could not be completed"; }
