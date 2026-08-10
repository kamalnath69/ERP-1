import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Archive, Buildings, Check, CreditCard, MapPin,
  NotePencil, Plus, Receipt, ShieldCheck, Storefront, UserCircle, Users,
  WarningCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import SecondarySidebarLayout, { SecondarySidebarTrigger } from "@/components/layout/SecondarySidebarLayout";
import { EmptyState, ErrorState } from "@/components/system";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  useCreateLocationMutation, useGetSettingsWorkspaceQuery, useRequestIndustryMigrationMutation,
  useUpdateLocationMutation, useUpdateSettingsSectionMutation,
} from "@/features/settings/settingsApi";
import { cn } from "@/lib/utils";

export const SETTINGS_DRAFT_PREFIX = "edvatiq.settings.drafts.v1";

const blankLocation = {
  name: "", code: "", address: "", city: "", state: "", postal_code: "",
  phone: "", gstin: "", is_primary: false,
};

const SETTINGS_GROUPS = [
  {
    label: "Organization",
    items: [
      { value: "identity", icon: Buildings, label: "Business profile" },
      { value: "locations", icon: Storefront, label: "Locations" },
    ],
  },
  {
    label: "Finance",
    items: [{ value: "tax", icon: Receipt, label: "Tax & invoicing" }],
  },
  {
    label: "Security",
    items: [
      { value: "security", icon: ShieldCheck, label: "Sign-in policy" },
      { value: "audit", icon: Archive, label: "Audit log", auditOnly: true },
    ],
  },
];

const SECTION_CAPABILITIES = {
  identity: "identity_manage",
  locations: "locations_manage",
  tax: "tax_manage",
  security: "security_manage",
};

const INTERNAL_SECTIONS = new Set(["identity", "locations", "tax", "security", "audit"]);

function identityValues(organization = {}) {
  return {
    name: organization.name || "",
    legal_name: organization.legal_name || "",
    gstin: organization.gstin || "",
    timezone: organization.timezone || "Asia/Kolkata",
    contact_email: organization.contact_email || "",
    contact_phone: organization.contact_phone || "",
    description: organization.description || null,
    invoice_prefix: organization.invoice_prefix || "INV",
  };
}

function serverForms(data = {}) {
  return {
    identity: identityValues(data.organization),
    tax: {
      prices_include_tax: Boolean(data.tax?.prices_include_tax),
      default_tax_rate_bps: Number(data.tax?.default_tax_rate_bps || 0),
    },
    security: { mfa_policy: data.security?.mfa_policy || "optional" },
  };
}

function sameValue(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function storageKey(organizationId) {
  return `${SETTINGS_DRAFT_PREFIX}:${organizationId}`;
}

function cleanDraft(section, value, baseline) {
  if (!value || typeof value !== "object" || !baseline) return null;
  const next = { ...baseline };
  Object.keys(baseline).forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(value, key)) next[key] = value[key];
  });
  return sameValue(next, baseline) ? null : next;
}

export function readSettingsDrafts(organizationId, version, baseline) {
  if (!organizationId || typeof window === "undefined") return { sections: {}, stale: false };
  try {
    const raw = window.sessionStorage.getItem(storageKey(organizationId));
    if (!raw) return { sections: {}, stale: false };
    const record = JSON.parse(raw);
    if (Number(record.version) !== Number(version)) {
      window.sessionStorage.removeItem(storageKey(organizationId));
      return { sections: {}, stale: true };
    }
    const sections = {};
    Object.keys(baseline).forEach((section) => {
      const draft = cleanDraft(section, record.sections?.[section], baseline[section]);
      if (draft) sections[section] = draft;
    });
    return { sections, stale: false };
  } catch {
    window.sessionStorage.removeItem(storageKey(organizationId));
    return { sections: {}, stale: true };
  }
}

export function writeSettingsDrafts(organizationId, version, sections) {
  if (!organizationId || typeof window === "undefined") return;
  try {
    if (!Object.keys(sections).length) {
      window.sessionStorage.removeItem(storageKey(organizationId));
      return;
    }
    window.sessionStorage.setItem(storageKey(organizationId), JSON.stringify({ version, sections }));
  } catch {
    // Settings remain usable when browser storage is unavailable.
  }
}

export function normalizeSettingsSection(requested, canViewAudit = true) {
  if (!requested || !INTERNAL_SECTIONS.has(requested)) return "identity";
  if (requested === "audit" && !canViewAudit) return "identity";
  return requested;
}

export default function Settings() {
  const auth = useAuth();
  const { refresh: refreshContext } = useBusiness();
  const [params, setParams] = useSearchParams();
  const query = useGetSettingsWorkspaceQuery();
  const [saveSection, saveState] = useUpdateSettingsSectionMutation();
  const [createLocation, createLocationState] = useCreateLocationMutation();
  const [updateLocation, updateLocationState] = useUpdateLocationMutation();
  const [requestMigration, migrationState] = useRequestIndustryMigrationMutation();
  const [baseline, setBaseline] = useState(() => serverForms());
  const [forms, setForms] = useState(() => serverForms());
  const [drafts, setDrafts] = useState({});
  const [settingsVersion, setSettingsVersion] = useState(1);
  const [locationDialog, setLocationDialog] = useState(null);
  const [locationForm, setLocationForm] = useState(blankLocation);
  const [industryDialog, setIndustryDialog] = useState(false);
  const [industryRequest, setIndustryRequest] = useState({ requested_industry: "", reason: "" });

  const data = query.data;
  const isCollege = data?.organization?.industry === "college";
  const canViewAudit = Boolean(data?.capabilities?.audit_view);
  const requestedSection = params.get("section");
  const active = normalizeSettingsSection(requestedSection, canViewAudit);
  const settingsGroups = useMemo(() => SETTINGS_GROUPS.map((group) => ({
    ...group,
    label: isCollege && group.label === "Organization" ? "College" : group.label,
    items: group.items.map((item) => ({
      ...item,
      label: isCollege && item.value === "identity" ? "College profile"
        : isCollege && item.value === "locations" ? "Campuses"
          : isCollege && item.value === "tax" ? "Fee invoicing & tax"
            : item.label,
    })),
  })), [isCollege]);
  const sections = useMemo(() => settingsGroups.flatMap((group) => group.items).filter(
    (item) => !item.auditOnly || canViewAudit,
  ), [canViewAudit, settingsGroups]);
  const activeSection = sections.find((item) => item.value === active) || sections[0];
  const relatedLinks = [
    { to: "/app/me", icon: UserCircle, label: "My profile", visible: true },
    { to: "/app/access", icon: Users, label: "Team & access", visible: auth?.can?.("roles.manage") },
    { to: "/app/billing", icon: CreditCard, label: "Plan & billing", visible: auth?.can?.("billing.view") },
  ].filter((item) => item.visible);

  useEffect(() => {
    if (!data?.organization) return;
    const nextBaseline = serverForms(data);
    const restored = readSettingsDrafts(
      data.organization.id,
      data.organization.settings_version,
      nextBaseline,
    );
    setBaseline(nextBaseline);
    setForms({ ...nextBaseline, ...restored.sections });
    setDrafts(restored.sections);
    setSettingsVersion(data.organization.settings_version);
    if (restored.stale) toast.info("Saved settings drafts were cleared because the workspace changed.");
  }, [data]);

  useEffect(() => {
    if (!data || !requestedSection || requestedSection === active) return;
    setParams(active === "identity" ? {} : { section: active }, { replace: true });
  }, [active, data, requestedSection, setParams]);

  const go = (value) => {
    setParams(value === "identity" ? {} : { section: value }, { replace: true });
  };

  const updateForm = (section, next) => {
    setForms((current) => ({ ...current, [section]: next }));
    setDrafts((current) => {
      const updated = { ...current };
      if (sameValue(next, baseline[section])) delete updated[section];
      else updated[section] = next;
      writeSettingsDrafts(data?.organization?.id, settingsVersion, updated);
      return updated;
    });
  };

  const setField = (section, key, value) => updateForm(section, { ...forms[section], [key]: value });

  const discard = (section) => {
    setForms((current) => ({ ...current, [section]: baseline[section] }));
    setDrafts((current) => {
      const updated = { ...current };
      delete updated[section];
      writeSettingsDrafts(data.organization.id, settingsVersion, updated);
      return updated;
    });
  };

  const save = async (section) => {
    try {
      const payload = section === "identity"
        ? { ...forms.identity, version: settingsVersion }
        : { ...forms[section], version: settingsVersion };
      const result = await saveSection({ section, data: payload }).unwrap();
      const savedValue = { ...baseline[section], ...result.value };
      const remaining = { ...drafts };
      delete remaining[section];
      setBaseline((current) => ({ ...current, [section]: savedValue }));
      setForms((current) => ({ ...current, [section]: savedValue }));
      setDrafts(remaining);
      setSettingsVersion(result.settings_version);
      writeSettingsDrafts(data.organization.id, result.settings_version, remaining);
      toast.success(`${sectionLabel(section, isCollege)} saved`);
      if (section === "identity") await refreshContext();
      query.refetch();
    } catch (error) {
      const conflict = error?.status === 409 || error?.originalStatus === 409;
      if (conflict) {
        window.sessionStorage.removeItem(storageKey(data.organization.id));
        setDrafts({});
        await query.refetch();
        toast.error("Settings changed elsewhere. Stale drafts were cleared and the latest values were loaded.");
        return;
      }
      toast.error(error?.data?.detail || `${sectionLabel(section, isCollege)} could not be saved`);
    }
  };

  const editLocation = (location = null) => {
    setLocationDialog(location || "new");
    setLocationForm(location ? { ...location } : blankLocation);
  };

  const saveLocation = async () => {
    try {
      if (locationDialog === "new") await createLocation(locationForm).unwrap();
      else await updateLocation({
        locationId: locationDialog.id,
        data: { ...locationForm, version: locationDialog.version },
      }).unwrap();
      toast.success(locationDialog === "new" ? (isCollege ? "Campus added" : "Location added") : (isCollege ? "Campus updated" : "Location updated"));
      setLocationDialog(null);
      await refreshContext();
    } catch (error) {
      toast.error(error?.data?.detail || (isCollege ? "Campus could not be saved" : "Location could not be saved"));
    }
  };

  const submitIndustryRequest = async () => {
    try {
      await requestMigration(industryRequest).unwrap();
      toast.success("Industry review requested");
      setIndustryDialog(false);
      setIndustryRequest({ requested_industry: "", reason: "" });
    } catch (error) {
      toast.error(error?.data?.detail || "Review request could not be submitted");
    }
  };

  if (query.isLoading && !data) return <SettingsSkeleton />;
  if (query.error && !data) return <SecondarySidebarLayout
    sidebar={<div className="p-5 text-sm font-semibold">Organization settings</div>}
    sidebarClassName="bg-surface-subtle/35"
    contentClassName="bg-card"
  ><div className="mx-auto max-w-[860px] p-6 sm:p-10"><ErrorState title="Settings could not be loaded" description={query.error?.data?.detail} retry={query.refetch} /></div></SecondarySidebarLayout>;

  const capability = SECTION_CAPABILITIES[active];
  const canManage = capability ? Boolean(data.capabilities[capability]) : undefined;
  const activeDirty = Boolean(drafts[active]);
  const savingLocation = createLocationState.isLoading || updateLocationState.isLoading;

  return <>
    <SecondarySidebarLayout
      ariaLabel="Settings navigation"
      className="reveal bg-card"
      sidebarClassName="bg-surface-subtle/35"
      contentClassName="bg-card"
      mobileTitle="Settings"
      mobileDescription={data.organization.name}
      sidebar={<>
        <div className="shrink-0 border-b px-5 py-5">
          <div className="text-sm font-semibold">{isCollege ? "College settings" : "Organization settings"}</div>
          <div className="mt-1 truncate text-xs text-muted-foreground">{data.organization.name}</div>
        </div>
        <SettingsNavigation
          active={active}
          groups={settingsGroups}
          sections={sections}
          relatedLinks={relatedLinks}
          dirtySections={drafts}
          onChange={go}
        />
      </>}
      mobileSidebar={({ closeSidebar }) => <SettingsNavigation
        active={active}
        groups={settingsGroups}
        sections={sections}
        relatedLinks={relatedLinks}
        dirtySections={drafts}
        onChange={go}
        onNavigate={closeSidebar}
      />}
    >
      {({ openSidebar }) => <div className="flex min-h-full min-w-0 flex-col bg-card">
        <div className="border-b p-3 lg:hidden">
          <SecondarySidebarTrigger
            icon={activeSection?.icon}
            label={activeSection?.label || "Settings"}
            onClick={openSidebar}
            indicator={activeDirty && <span className="h-2 w-2 rounded-full bg-warning" aria-label="Unsaved changes" />}
          />
        </div>

        <main className="flex min-h-full min-w-0 flex-col">
          <div key={active} className="mx-auto w-full max-w-[860px] flex-1 px-5 py-7 sm:px-8 sm:py-9 lg:px-10 lg:py-10">
            {active === "identity" && <IdentitySection
              data={data}
              isCollege={isCollege}
              value={forms.identity}
              canManage={canManage}
              onChange={(key, value) => setField("identity", key, value)}
              onIndustry={() => setIndustryDialog(true)}
            />}
            {active === "locations" && <LocationsSection
              locations={data.locations}
              isCollege={isCollege}
              canManage={canManage}
              onAdd={() => editLocation()}
              onEdit={editLocation}
            />}
            {active === "tax" && <TaxSection
              value={forms.tax}
              isCollege={isCollege}
              canManage={canManage}
              onChange={(key, value) => setField("tax", key, value)}
            />}
            {active === "security" && <SecuritySection
              value={forms.security}
              canManage={canManage}
              onChange={(value) => setField("security", "mfa_policy", value)}
            />}
            {active === "audit" && <AuditSection events={data.audit} />}
          </div>

          {activeDirty && canManage && <DirtySaveBar
            section={activeSection?.label || sectionLabel(active)}
            saving={saveState.isLoading}
            onDiscard={() => discard(active)}
            onSave={() => save(active)}
          />}
        </main>
      </div>}
    </SecondarySidebarLayout>

    <LocationDialog
      dialog={locationDialog}
      form={locationForm}
      setForm={setLocationForm}
      saving={savingLocation}
      onSave={saveLocation}
      onClose={() => setLocationDialog(null)}
      isCollege={isCollege}
    />
    <IndustryDialog
      open={industryDialog}
      currentIndustry={data.organization.industry}
      request={industryRequest}
      setRequest={setIndustryRequest}
      pending={migrationState.isLoading}
      onSave={submitIndustryRequest}
      onClose={() => setIndustryDialog(false)}
    />
  </>;
}

function SettingsNavigation({ active, groups, sections, relatedLinks, dirtySections, onChange, onNavigate }) {
  const available = new Set(sections.map((item) => item.value));
  return <nav aria-label="Settings sections" className="premium-scrollbar flex-1 overflow-y-auto px-3 py-4">
    {groups.map((group) => {
      const items = group.items.filter((item) => available.has(item.value));
      if (!items.length) return null;
      return <div key={group.label} className="mb-5 last:mb-0">
        <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{group.label}</div>
        <div className="space-y-0.5">{items.map((item) => <SettingsNavItem
          key={item.value}
          item={item}
          active={active === item.value}
          dirty={Boolean(dirtySections[item.value])}
          onClick={() => { onChange(item.value); onNavigate?.(); }}
        />)}</div>
      </div>;
    })}

    {!!relatedLinks.length && <div className="mt-6 border-t pt-5">
      <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Related</div>
      <div className="space-y-0.5">{relatedLinks.map((item) => {
        const Icon = item.icon;
        return <Link key={item.to} to={item.to} onClick={onNavigate} className="flex h-10 items-center gap-3 rounded-lg border-l-2 border-transparent px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground">
          <Icon size={17} className="shrink-0" /><span>{item.label}</span>
        </Link>;
      })}</div>
    </div>}
  </nav>;
}

function SettingsNavItem({ item, active, dirty, onClick }) {
  const Icon = item.icon;
  return <button
    type="button"
    onClick={onClick}
    aria-current={active ? "page" : undefined}
    className={cn(
      "flex h-10 w-full items-center gap-3 rounded-lg border-l-2 px-3 text-left text-sm transition-colors",
      active
        ? "border-primary bg-secondary font-semibold text-foreground"
        : "border-transparent text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
    )}
  >
    <Icon size={17} className="shrink-0" />
    <span className="min-w-0 flex-1 truncate">{item.label}</span>
    {dirty && <span className="h-2 w-2 rounded-full bg-warning" aria-label={`${item.label} has unsaved changes`} />}
  </button>;
}

function SectionHeader({ title, description, canManage, action }) {
  return <header className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-start sm:justify-between">
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-2xl font-semibold tracking-[-0.025em]">{title}</h2>
        {canManage === false && <span className="rounded-full bg-secondary px-2.5 py-1 text-[10px] font-semibold text-muted-foreground">View only</span>}
      </div>
      {description && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p>}
    </div>
    {action && <div className="shrink-0">{action}</div>}
  </header>;
}

function SettingsGroup({ title, description, children, last = false }) {
  return <section className={cn("grid gap-5 border-b py-7 md:grid-cols-[190px_minmax(0,1fr)]", last && "border-b-0 pb-0")}>
    <div><h3 className="text-sm font-semibold">{title}</h3>{description && <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>}</div>
    <div className="min-w-0">{children}</div>
  </section>;
}

function IdentitySection({ data, value, canManage, onChange, onIndustry, isCollege }) {
  return <div>
    <SectionHeader title={isCollege ? "College profile" : "Business profile"} description={isCollege ? "Institution details used across student records, campus schedules, fee documents, and communication." : "Organization details used across invoices, schedules, and team communication."} canManage={canManage} />
    <fieldset disabled={!canManage}>
      <SettingsGroup title={isCollege ? "Institution details" : "Company details"} description="The legal and operating names used by your workspace.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={isCollege ? "College name" : "Business name"}><Input value={value.name || ""} onChange={(event) => onChange("name", event.target.value)} /></Field>
          <Field label="Legal name"><Input value={value.legal_name || ""} onChange={(event) => onChange("legal_name", event.target.value)} /></Field>
        </div>
      </SettingsGroup>
      <SettingsGroup title="Contact" description="Primary organization contact information.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Contact email"><Input type="email" value={value.contact_email || ""} onChange={(event) => onChange("contact_email", event.target.value)} /></Field>
          <Field label="Contact phone"><Input inputMode="tel" value={value.contact_phone || ""} onChange={(event) => onChange("contact_phone", event.target.value)} /></Field>
        </div>
      </SettingsGroup>
      <SettingsGroup title="Regional & documents" description={isCollege ? "Defaults used for dates, fee records, and official numbering." : "Defaults used for dates, money, and invoice numbering."}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Timezone" hint="Use an IANA timezone such as Asia/Kolkata."><Input value={value.timezone || "Asia/Kolkata"} onChange={(event) => onChange("timezone", event.target.value)} /></Field>
          <Field label="Currency"><Input value={data.organization.currency || "INR"} disabled /></Field>
          <Field label="Invoice prefix" hint="Letters, numbers, and hyphens only."><Input value={value.invoice_prefix || "INV"} onChange={(event) => onChange("invoice_prefix", event.target.value)} /></Field>
          <Field label="GSTIN"><Input value={value.gstin || ""} onChange={(event) => onChange("gstin", event.target.value)} /></Field>
        </div>
      </SettingsGroup>
      <SettingsGroup title="Workspace type" description="Industry controls terminology and operational modules." last>
        <div className="rounded-xl border">
          <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div><div className="text-xs text-muted-foreground">Primary industry</div><div className="mt-1 text-sm font-semibold capitalize">{data.organization.industry}</div></div>
            <Button type="button" variant="outline" size="sm" disabled={!canManage || Boolean(data.pending_industry_request)} onClick={onIndustry}>{data.pending_industry_request ? "Review pending" : "Request change"}</Button>
          </div>
          {data.pending_industry_request && <div className="flex gap-2 border-t px-4 py-3 text-xs text-warning"><WarningCircle size={16} className="shrink-0" />A change to {capitalize(data.pending_industry_request.requested_industry)} is under review.</div>}
        </div>
      </SettingsGroup>
    </fieldset>
  </div>;
}

function LocationsSection({ locations, canManage, onAdd, onEdit, isCollege }) {
  return <div>
    <SectionHeader
      title={isCollege ? "Campuses" : "Locations"}
      description={isCollege ? "Campuses scope students, schedules, faculty access, and fee records." : "Branches that scope schedules, inventory, invoices, and team access."}
      canManage={canManage}
      action={canManage && <Button onClick={onAdd}><Plus />Add {isCollege ? "campus" : "location"}</Button>}
    />
    <div className="pt-7">
      {locations.length ? <div className="overflow-hidden rounded-xl border divide-y">{locations.map((location) => <LocationRow key={location.id} location={location} canManage={canManage} onEdit={() => onEdit(location)} />)}</div> : <EmptyState variant="section" alignment="left" icon={Storefront} title={isCollege ? "No campuses configured" : "No operating locations"} description={isCollege ? "Add the first campus to scope students, faculty, and schedules." : "Add the first location to scope daily operations."} action={canManage && <Button onClick={onAdd}><Plus />Add {isCollege ? "campus" : "location"}</Button>} />}
    </div>
  </div>;
}

function LocationRow({ location, canManage, onEdit }) {
  const address = [location.address, location.city, location.state, location.postal_code].filter(Boolean).join(", ");
  return <article className="grid gap-4 px-4 py-5 sm:px-5 lg:grid-cols-[minmax(180px,.8fr)_minmax(240px,1.25fr)_auto] lg:items-center">
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2"><h3 className="truncate text-sm font-semibold">{location.name}</h3>{location.is_primary && <span className="rounded-full bg-positive-soft px-2 py-0.5 text-[10px] font-semibold text-positive">Primary</span>}</div>
      <div className="mt-1 font-mono text-[11px] text-muted-foreground">{location.code}</div>
    </div>
    <div className="min-w-0 text-xs leading-5 text-muted-foreground">
      <div className="flex gap-2"><MapPin size={15} className="mt-0.5 shrink-0" /><span>{address || "Address not added"}</span></div>
      <div className="mt-1 pl-[23px]">{[location.phone, location.gstin && `GSTIN ${location.gstin}`].filter(Boolean).join(" / ") || "No contact details"}</div>
    </div>
    {canManage && <Button type="button" variant="ghost" size="sm" onClick={onEdit}><NotePencil />Edit</Button>}
  </article>;
}

function TaxSection({ value, canManage, onChange, isCollege }) {
  return <div>
    <SectionHeader title={isCollege ? "Fee invoicing & tax" : "Tax & invoicing"} description={isCollege ? "Defaults applied only when a student fee obligation creates an invoice." : "Defaults applied when new operational invoices are prepared."} canManage={canManage} />
    <fieldset disabled={!canManage}>
      <SettingsGroup title={isCollege ? "Fee amounts" : "Catalog pricing"} description={isCollege ? "Choose how configured fee amounts are interpreted." : "Choose how listed prices are interpreted."}>
        <label className="flex cursor-pointer items-center justify-between gap-5 rounded-xl border px-4 py-4">
          <span><span className="block text-sm font-semibold">{isCollege ? "Fee amounts include tax" : "Prices include tax"}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{isCollege ? "Treat newly configured fee amounts as tax-inclusive by default." : "Treat catalog prices as tax-inclusive by default."}</span></span>
          <Switch aria-label="Prices include tax" checked={Boolean(value.prices_include_tax)} disabled={!canManage} onCheckedChange={(checked) => onChange("prices_include_tax", checked)} />
        </label>
      </SettingsGroup>
      <SettingsGroup title="Default tax rate" description="Used when an item does not define its own rate." last>
        <Field label="Invoice default">
          <Select value={String(value.default_tax_rate_bps ?? 0)} onValueChange={(next) => onChange("default_tax_rate_bps", Number(next))} disabled={!canManage}>
            <SelectTrigger className="max-w-sm"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="0">No default tax</SelectItem><SelectItem value="500">5%</SelectItem><SelectItem value="1200">12%</SelectItem><SelectItem value="1800">18%</SelectItem><SelectItem value="2800">28%</SelectItem></SelectContent>
          </Select>
        </Field>
        <p className="mt-4 border-t pt-4 text-xs leading-5 text-muted-foreground">Changes apply to future invoices. Existing invoice tax snapshots remain unchanged.</p>
      </SettingsGroup>
    </fieldset>
  </div>;
}

function SecuritySection({ value, canManage, onChange }) {
  const options = [
    ["optional", "Optional", "Each person chooses whether to add an authenticator."],
    ["privileged", "Privileged roles", "Owners, managers, and financial roles must use an authenticator."],
    ["all", "Everyone", "Every team account must use an authenticator at sign-in."],
  ];
  return <div>
    <SectionHeader title="Sign-in policy" description="Set the minimum authenticator requirement for this organization." canManage={canManage} />
    <fieldset disabled={!canManage} className="pt-7">
      <div role="radiogroup" aria-label="Authenticator policy" className="overflow-hidden rounded-xl border divide-y">
        {options.map(([id, label, description]) => {
          const selected = value.mfa_policy === id;
          return <button
            key={id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={!canManage}
            onClick={() => onChange(id)}
            className={cn("flex w-full items-start gap-4 px-4 py-4 text-left transition-colors sm:px-5", selected ? "bg-secondary/75" : "hover:bg-surface-hover")}
          >
            <span className={cn("mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border", selected ? "border-primary bg-primary text-primary-foreground" : "border-input")}>
              {selected && <Check size={12} weight="bold" />}
            </span>
            <span className="min-w-0"><span className="block text-sm font-semibold">{label}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span></span>
          </button>;
        })}
      </div>
      <p className="mt-4 text-xs leading-5 text-muted-foreground">People affected by a stronger policy complete authenticator enrollment at their next sign-in.</p>
    </fieldset>
  </div>;
}

function AuditSection({ events }) {
  return <div>
    <SectionHeader title="Audit log" description="Recent changes to organization settings, locations, and workspace type." />
    <div className="pt-7">
      {events.length ? <div className="overflow-hidden rounded-xl border">
        <div className="hidden grid-cols-[minmax(0,1fr)_180px_180px] border-b bg-surface-subtle/50 px-5 py-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground sm:grid"><span>Event</span><span>Actor</span><span>Time</span></div>
        <ol className="divide-y">{events.map((event) => <li key={event.id} className="grid gap-2 px-4 py-4 text-sm sm:grid-cols-[minmax(0,1fr)_180px_180px] sm:items-center sm:px-5">
          <span className="font-medium">{auditLabel(event.action)}</span>
          <span className="text-xs text-muted-foreground">{event.actor || "System"}</span>
          <time className="text-xs text-muted-foreground">{dateTime(event.created_at)}</time>
        </li>)}</ol>
      </div> : <EmptyState variant="inline" icon={Archive} title="No settings changes yet" description="Organization and location changes will appear here." />}
    </div>
  </div>;
}

function DirtySaveBar({ section, saving, onDiscard, onSave }) {
  return <div className="sticky bottom-20 z-20 mx-auto w-full max-w-[860px] px-5 pb-5 sm:px-8 md:bottom-4 lg:px-10">
    <div className="flex flex-col gap-3 rounded-xl border bg-card/96 px-4 py-3 shadow-xl backdrop-blur sm:flex-row sm:items-center sm:justify-between">
      <div><div className="text-sm font-semibold">Unsaved changes</div><div className="mt-0.5 text-xs text-muted-foreground">Your {section.toLowerCase()} draft is saved in this browser session.</div></div>
      <div className="flex gap-2"><Button type="button" variant="ghost" disabled={saving} onClick={onDiscard}>Discard</Button><Button type="button" disabled={saving} onClick={onSave}>{saving ? "Saving..." : "Save changes"}</Button></div>
    </div>
  </div>;
}

function Field({ label, hint, children }) {
  return <div className="space-y-2"><div><Label>{label}</Label>{hint && <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{hint}</p>}</div>{children}</div>;
}

function LocationDialog({ dialog, form, setForm, saving, onSave, onClose, isCollege }) {
  const editing = dialog && dialog !== "new";
  return <Dialog open={Boolean(dialog)} onOpenChange={(open) => !open && onClose()}>
    <DialogContent className="premium-scrollbar max-h-[92vh] overflow-y-auto sm:max-w-2xl">
      <DialogHeader><DialogTitle className="text-2xl font-semibold">{editing ? `Edit ${isCollege ? "campus" : "location"}` : `Add ${isCollege ? "campus" : "location"}`}</DialogTitle><DialogDescription>{isCollege ? "Campus details scope students, schedules, faculty access, and fee records." : "Location details are used to scope schedules, stock, invoices, and team access."}</DialogDescription></DialogHeader>
      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={isCollege ? "Campus name" : "Location name"}><Input autoFocus value={form.name || ""} onChange={simple(setForm, "name")} /></Field>
          <Field label={isCollege ? "Campus code" : "Location code"} hint="Short, stable identifier."><Input disabled={editing} value={form.code || ""} onChange={simple(setForm, "code")} /></Field>
          <Field label="City"><Input value={form.city || ""} onChange={simple(setForm, "city")} /></Field>
          <Field label="State"><Input value={form.state || ""} onChange={simple(setForm, "state")} /></Field>
          <Field label="Postal code"><Input inputMode="numeric" value={form.postal_code || ""} onChange={simple(setForm, "postal_code")} /></Field>
          <Field label={isCollege ? "Campus phone" : "Location phone"}><Input inputMode="tel" value={form.phone || ""} onChange={simple(setForm, "phone")} /></Field>
          <Field label="GSTIN"><Input value={form.gstin || ""} onChange={simple(setForm, "gstin")} /></Field>
          <div className="sm:col-span-2"><Field label="Street address"><Textarea rows={3} value={form.address || ""} onChange={simple(setForm, "address")} /></Field></div>
        </div>
        <div className="flex justify-end gap-2 border-t pt-5"><Button type="button" variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" disabled={saving || !form.name?.trim() || !form.code?.trim()}>{saving ? "Saving..." : editing ? `Save ${isCollege ? "campus" : "location"}` : `Add ${isCollege ? "campus" : "location"}`}</Button></div>
      </form>
    </DialogContent>
  </Dialog>;
}

function IndustryDialog({ open, currentIndustry, request, setRequest, pending, onSave, onClose }) {
  return <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
    <DialogContent className="sm:max-w-lg">
      <DialogHeader><DialogTitle className="text-2xl font-semibold">Request industry change</DialogTitle><DialogDescription>Industry changes are reviewed because they affect terminology, permissions, workflows, and reports.</DialogDescription></DialogHeader>
      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
        <Field label="Requested industry"><Select value={request.requested_industry} onValueChange={(value) => setRequest((current) => ({ ...current, requested_industry: value }))}><SelectTrigger><SelectValue placeholder="Choose industry" /></SelectTrigger><SelectContent>{["gym", "salon", "clinic", "college"].filter((value) => value !== currentIndustry).map((value) => <SelectItem key={value} value={value}>{capitalize(value)}</SelectItem>)}</SelectContent></Select></Field>
        <Field label="Business reason" hint="Explain the operational change so it can be reviewed safely."><Textarea rows={5} minLength={20} value={request.reason} onChange={simple(setRequest, "reason")} /></Field>
        <div className="flex justify-end gap-2 border-t pt-5"><Button type="button" variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" disabled={pending || !request.requested_industry || request.reason.trim().length < 20}>{pending ? "Submitting..." : "Submit for review"}</Button></div>
      </form>
    </DialogContent>
  </Dialog>;
}

function SettingsSkeleton() {
  return <SecondarySidebarLayout
    sidebar={<div className="h-full animate-pulse bg-surface-subtle" />}
    sidebarClassName="bg-surface-subtle/35"
    contentClassName="bg-card"
  >
    <div className="mx-auto max-w-[860px] p-6 sm:p-10"><div className="h-8 w-56 animate-pulse rounded bg-secondary" /><div className="mt-3 h-4 w-96 max-w-full animate-pulse rounded bg-secondary" /><div className="mt-8 space-y-5">{[1, 2, 3].map((item) => <div key={item} className="h-28 animate-pulse rounded-xl bg-surface-subtle" />)}</div></div>
  </SecondarySidebarLayout>;
}

function simple(setter, key) {
  return (event) => setter((current) => ({ ...current, [key]: event.target.value }));
}

function sectionLabel(value = "", isCollege = false) {
  const labels = { identity: isCollege ? "College profile" : "Business profile", tax: isCollege ? "Fee invoicing & tax" : "Tax & invoicing", security: "Sign-in policy" };
  if (labels[value]) return labels[value];
  return String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function capitalize(value = "") {
  const text = String(value || "");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function auditLabel(action = "") {
  return String(action)
    .replace("settings.", "")
    .replace("organization.", "business ")
    .replace("location.", "location ")
    .replaceAll("_", " ")
    .replaceAll(".", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateTime(value) {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Time unavailable";
}
