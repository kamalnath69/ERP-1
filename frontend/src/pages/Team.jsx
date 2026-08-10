import React, { useDeferredValue, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import PasswordStrength, { isPasswordAcceptable } from "@/components/PasswordStrength";
import { IdentificationBadge, MagnifyingGlass, Plus, ShieldCheck, Users } from "@phosphor-icons/react";
import { toast } from "sonner";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip, PageHeader,
  PageShell, StatusBadge,
} from "@/components/system";
import { EntityAvatar } from "@/components/entities/EntityProfile";
import { useGetRolesQuery } from "@/store/api/workspaceApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { useCreateEmployeeMutation, useGetTeamDirectoryQuery } from "@/features/team/teamApi";
import { clientLabel } from "@/app/routeManifest";
import useCursorPagination from "@/hooks/useCursorPagination";

const blank = { first_name: "", last_name: "", email: "", phone: "", designation: "", salary: "", joining_date: "", create_login: false, password: "", role_ids: [], location_ids: [] };

export default function Team() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const { locations, locationId, organization } = useBusiness();
  const isCollege = organization?.industry === "college";
  const entityName = clientLabel(organization?.industry, false);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [status, setStatus] = useState("all");
  const [open, setOpen] = useState(() => new URLSearchParams(window.location.search).get("new") === "1");
  const [form, setForm] = useState(() => ({ ...blank, location_ids: locationId ? [locationId] : [] }));
  const pageKey = JSON.stringify({ locationId, q: deferredSearch, status });
  const paging = useCursorPagination(pageKey);
  const directory = useGetTeamDirectoryQuery({ locationId, q: deferredSearch, status: status === "all" ? undefined : status, cursor: paging.cursor, limit: 25 }, withSkip(QUERY_POLICIES.collaborative, !locationId));
  const rolesQuery = useGetRolesQuery(undefined, withSkip(QUERY_POLICIES.reference, !can("roles.manage")));
  const [createEmployee, createState] = useCreateEmployeeMutation();
  const data = directory.data;
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(data); }, [acceptPage, data]);
  const rows = paging.items;
  const roles = rolesQuery.data || [];

  useEffect(() => {
    if (!open || form.location_ids.length || !locationId) return;
    setForm((current) => ({ ...current, location_ids: [locationId] }));
  }, [form.location_ids.length, locationId, open]);

  if (directory.isError && !data) return <PageShell><ErrorState title={isCollege ? "Faculty and staff could not be loaded" : "Team could not be loaded"} description={directory.error?.data?.detail} retry={directory.refetch} /></PageShell>;

  const submit = async (event) => {
    event.preventDefault();
    if (form.create_login && !isPasswordAcceptable(form.password)) return toast.error("Choose a stronger temporary password");
    if (form.create_login && !form.role_ids.length) return toast.error("Choose at least one role for login access");
    try {
      const payload = {
        ...form,
        salary_paise: can("employees.compensation.view") && form.salary ? Math.round(Number(form.salary) * 100) : null,
        joining_date: form.joining_date || null,
        email: form.email || null,
        phone: form.phone || null,
        designation: form.designation || null,
        password: form.create_login ? form.password : null,
      };
      await createEmployee(payload).unwrap();
      toast.success(isCollege ? "Faculty or staff member added" : "Team member added"); setOpen(false); setForm({ ...blank, location_ids: locationId ? [locationId] : [] });
    } catch (error) { toast.error(error?.data?.detail || (isCollege ? "Could not add faculty or staff member" : "Could not add team member")); }
  };

  const metrics = data?.summary ? [
    { id: "members", label: isCollege ? "Faculty & staff" : "Team members", value: data.summary.team_members },
    { id: "active", label: isCollege ? "Active people" : "Active", value: data.summary.active },
    { id: "accounts", label: "Login accounts", value: data.summary.login_accounts },
    { id: "available", label: isCollege ? "Scheduled today" : "Scheduled today", value: data.summary.available_today },
  ] : [];
  const columns = [
    { key: "name", label: isCollege ? "Faculty / staff" : "Team member", render: (row) => <div className="flex items-center gap-3"><EntityAvatar name={`${row.first_name} ${row.last_name}`} size="md" /><div><div className="font-semibold">{row.first_name} {row.last_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.employee_number} · {row.designation || (isCollege ? "College staff" : "Team member")}</div></div></div> },
    { key: "roles", label: "Responsibility", render: (row) => row.roles.length ? <div className="flex flex-wrap gap-1">{row.roles.map((role) => <StatusBadge key={role} status="neutral" label={role} />)}</div> : <span className="text-muted-foreground">No login role</span> },
    { key: "locations", label: isCollege ? "Campuses" : "Locations", render: (row) => row.locations.map((location) => location.name).join(", ") || "Not assigned" },
    { key: "workload", label: "Today", render: (row) => row.appointments_today == null ? <span className="text-muted-foreground">Restricted</span> : `${row.appointments_today} ${isCollege ? "student meetings" : "appointments"}` },
    { key: "account", label: "Account", render: (row) => row.account.enabled ? <StatusBadge status={row.account.active ? row.account.verified ? "active" : "pending" : "inactive"} label={row.account.active ? row.account.verified ? "Ready" : "Verification due" : "Suspended"} /> : <StatusBadge status="neutral" label="Staff only" /> },
    { key: "status", label: "Employment", render: (row) => <StatusBadge status={row.status} /> },
  ];
  const isFilteredEmpty = Boolean(deferredSearch || status !== "all");

  return <PageShell className="reveal">
    <PageHeader eyebrow={isCollege ? "Academic and placement staff" : "People and responsibility"} title={isCollege ? "Faculty & staff" : "Team"} description={isCollege ? "Manage faculty, placement coordinators, HODs, campus assignments, and role-based access." : "Employee profiles, schedules, assignments, locations, and account access in one directory."} actions={<div className="flex gap-2">{can("roles.manage") && <Button variant="outline" onClick={() => navigate("/app/access")}><ShieldCheck className="mr-2" />Access</Button>}{can("employees.manage") && <Button onClick={() => setOpen(true)}><Plus className="mr-2" />{isCollege ? "Add faculty or staff" : "Add team member"}</Button>}</div>} />
    <MetricStrip metrics={metrics} loading={directory.isLoading && !data} />
    <FilterBar><div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search name, phone, role, or employee number" /></div><Select value={status} onValueChange={setStatus}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All employment states</SelectItem><SelectItem value="active">Active</SelectItem><SelectItem value="on_leave">On leave</SelectItem><SelectItem value="inactive">Inactive</SelectItem></SelectContent></Select></FilterBar>
    <DataTable loading={directory.isLoading && !rows.length} rows={rows} columns={columns} onRowClick={(row) => navigate(`/app/team/${row.id}`)} empty={<EmptyState variant={isFilteredEmpty ? "filtered" : "page"} alignment="left" icon={Users} title={isFilteredEmpty ? `No ${isCollege ? "faculty or staff" : "team members"} match this view` : isCollege ? "Build the College team" : "Build your operating team"} description={isFilteredEmpty ? "Clear the search and employment filter to see the complete directory." : isCollege ? "Add faculty, HODs, or placement staff, assign their campuses, and provide only the access they need." : "Add the first team member, assign their locations, and optionally provide application access."} primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setSearch(""); setStatus("all"); }}>Clear filters</Button> : can("employees.manage") ? <Button onClick={() => setOpen(true)}>{isCollege ? "Add faculty or staff" : "Add team member"}</Button> : null} steps={isFilteredEmpty ? [] : [{ title: "Create profile" }, { title: isCollege ? "Assign campuses" : "Assign locations" }, { title: "Choose access" }]} />} />
    {(rows.length > 0 || data?.has_more) && <CursorListFooter count={rows.length} noun={isCollege ? "faculty and staff" : "team members"} hasMore={Boolean(data?.has_more)} loading={directory.isFetching} error={directory.isError} onLoadMore={() => paging.loadMore(data?.next_cursor)} onRetry={directory.refetch} />}

    <DrawerForm open={open} onOpenChange={setOpen} title={isCollege ? "Add faculty or staff" : "Add team member"} description={isCollege ? "Create the staff profile, assign campuses, and optionally provide application access." : "Create the employee profile first. Login access is optional and can be adjusted later."}>
      <form onSubmit={submit} className="space-y-6">
        <section className="grid gap-4 sm:grid-cols-2"><Field label="First name"><Input autoFocus required value={form.first_name} onChange={setField(setForm, "first_name")} /></Field><Field label="Last name"><Input value={form.last_name} onChange={setField(setForm, "last_name")} /></Field><Field label="Phone"><Input value={form.phone} onChange={setField(setForm, "phone")} /></Field><Field label="Email"><Input type="email" value={form.email} onChange={setField(setForm, "email")} /></Field><Field label="Designation"><Input value={form.designation} onChange={setField(setForm, "designation")} /></Field><Field label="Joining date"><Input type="date" value={form.joining_date} onChange={setField(setForm, "joining_date")} /></Field>{can("employees.compensation.view") && <Field label="Monthly salary (INR)"><Input type="number" min="0" value={form.salary} onChange={setField(setForm, "salary")} /></Field>}</section>
        <section><div className="mb-3"><h3 className="font-display text-xl font-semibold">{isCollege ? "Campuses" : "Locations"}</h3><p className="mt-1 text-xs text-muted-foreground">Select where this person works.</p></div><div className="grid gap-2 sm:grid-cols-2">{locations.map((location) => <CheckCard key={location.id} label={location.name} checked={form.location_ids.includes(location.id)} onChange={() => toggleList(setForm, "location_ids", location.id)} />)}</div></section>
        {can("roles.manage") ? <section className="rounded-2xl border bg-secondary/35 p-4"><CheckRow label="Give this person app login" checked={form.create_login} onChange={(checked) => setForm((current) => ({ ...current, create_login: checked }))} />{form.create_login && <div className="mt-5 space-y-5"><Field label="Temporary password"><Input type="password" required value={form.password} onChange={setField(setForm, "password")} /><PasswordStrength password={form.password} compact /></Field><div><Label>Starting roles</Label><div className="mt-2 grid gap-2 sm:grid-cols-2">{roles.filter((role) => role.is_active).map((role) => <CheckCard key={role.id} label={role.name} checked={form.role_ids.includes(role.id)} onChange={() => toggleList(setForm, "role_ids", role.id)} />)}</div></div><p className="text-xs text-muted-foreground">They will verify their email before using the account. You can refine location and {entityName} reach in Access.</p></div>}</section> : <div className="rounded-2xl border p-4 text-sm text-muted-foreground"><IdentificationBadge className="mb-2" />An owner can add login access after this employee profile is created.</div>}
        <Button disabled={createState.isLoading || !form.location_ids.length || (form.create_login && (!form.role_ids.length || !isPasswordAcceptable(form.password)))} className="h-12 w-full">{createState.isLoading ? "Adding..." : isCollege ? "Add faculty or staff" : "Add team member"}</Button>
      </form>
    </DrawerForm>
  </PageShell>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function CheckRow({ label, checked, onChange }) { return <label className="flex cursor-pointer items-center gap-3 text-sm font-medium"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />{label}</label>; }
function CheckCard({ label, checked, onChange }) { return <label className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-sm ${checked ? "border-accent bg-accent/5" : "bg-card"}`}><input type="checkbox" checked={checked} onChange={onChange} />{label}</label>; }
function setField(setForm, key) { return (event) => setForm((current) => ({ ...current, [key]: event.target.value })); }
function toggleList(setForm, key, id) { setForm((current) => ({ ...current, [key]: current[key].includes(id) ? current[key].filter((value) => value !== id) : [...current[key], id] })); }
