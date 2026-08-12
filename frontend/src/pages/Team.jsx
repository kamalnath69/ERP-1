import React, { useDeferredValue, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import PasswordStrength from "@/components/PasswordStrength";
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
import { applyApiErrors, employeeSchema, FORM_OPTIONS } from "@/lib/validation";

const blank = { first_name: "", last_name: "", email: "", phone: "", designation: "", salary: "", joining_date: "", create_login: false, password: "", role_ids: [], location_ids: [] };
const employeeDefaults = (locationId) => ({ ...blank, location_ids: locationId ? [locationId] : [] });

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
  const employeeForm = useForm({ resolver: zodResolver(employeeSchema), defaultValues: employeeDefaults(locationId), ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, setValue, watch } = employeeForm;
  const selectedLocationIds = watch("location_ids") || [];
  const selectedRoleIds = watch("role_ids") || [];
  const createLogin = watch("create_login");
  const temporaryPassword = watch("password") || "";
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
    if (!open || selectedLocationIds.length || !locationId) return;
    setValue("location_ids", [locationId], { shouldValidate: true });
  }, [locationId, open, selectedLocationIds.length, setValue]);

  if (directory.isError && !data) return <PageShell><ErrorState title={isCollege ? "Faculty and staff could not be loaded" : "Team could not be loaded"} description={directory.error?.data?.detail} retry={directory.refetch} /></PageShell>;

  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      const payload = {
        first_name: values.first_name,
        last_name: values.last_name || "",
        email: values.email || null,
        phone: values.phone || null,
        designation: values.designation || null,
        salary_paise: can("employees.compensation.view") ? values.salary_paise : null,
        joining_date: values.joining_date || null,
        location_ids: values.location_ids,
        create_login: values.create_login,
        password: values.create_login ? values.password : null,
        role_ids: values.create_login ? values.role_ids : [],
      };
      await createEmployee(payload).unwrap();
      toast.success(isCollege ? "Faculty or staff member added" : "Team member added");
      reset(employeeDefaults(locationId));
      setOpen(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, {
        aliases: { salary_paise: "salary" },
        fallback: isCollege ? "Could not add faculty or staff member" : "Could not add team member",
      });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  const openCreate = () => { reset(employeeDefaults(locationId)); setOpen(true); };
  const changeDrawer = (nextOpen) => { if (!nextOpen && (formState.isSubmitting || createState.isLoading)) return; setOpen(nextOpen); };

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
    <PageHeader eyebrow={isCollege ? "Academic and placement staff" : "People and responsibility"} title={isCollege ? "Faculty & staff" : "Team"} description={isCollege ? "Manage faculty, placement coordinators, HODs, campus assignments, and role-based access." : "Employee profiles, schedules, assignments, locations, and account access in one directory."} actions={<div className="flex gap-2">{can("roles.manage") && <Button variant="outline" onClick={() => navigate("/app/access")}><ShieldCheck className="mr-2" />Access</Button>}{can("employees.manage") && <Button onClick={openCreate}><Plus className="mr-2" />{isCollege ? "Add faculty or staff" : "Add team member"}</Button>}</div>} />
    <MetricStrip metrics={metrics} loading={directory.isLoading && !data} />
    <FilterBar><div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search name, phone, role, or employee number" /></div><Select value={status} onValueChange={setStatus}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All employment states</SelectItem><SelectItem value="active">Active</SelectItem><SelectItem value="on_leave">On leave</SelectItem><SelectItem value="inactive">Inactive</SelectItem></SelectContent></Select></FilterBar>
    <DataTable loading={directory.isLoading && !rows.length} rows={rows} columns={columns} onRowClick={(row) => navigate(`/app/team/${row.id}`)} empty={<EmptyState variant={isFilteredEmpty ? "filtered" : "page"} alignment="left" icon={Users} title={isFilteredEmpty ? `No ${isCollege ? "faculty or staff" : "team members"} match this view` : isCollege ? "Build the College team" : "Build your operating team"} description={isFilteredEmpty ? "Clear the search and employment filter to see the complete directory." : isCollege ? "Add faculty, HODs, or placement staff, assign their campuses, and provide only the access they need." : "Add the first team member, assign their locations, and optionally provide application access."} primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setSearch(""); setStatus("all"); }}>Clear filters</Button> : can("employees.manage") ? <Button onClick={openCreate}>{isCollege ? "Add faculty or staff" : "Add team member"}</Button> : null} steps={isFilteredEmpty ? [] : [{ title: "Create profile" }, { title: isCollege ? "Assign campuses" : "Assign locations" }, { title: "Choose access" }]} />} />
    {(rows.length > 0 || data?.has_more) && <CursorListFooter count={rows.length} noun={isCollege ? "faculty and staff" : "team members"} hasMore={Boolean(data?.has_more)} loading={directory.isFetching} error={directory.isError} onLoadMore={() => paging.loadMore(data?.next_cursor)} onRetry={directory.refetch} />}

    <DrawerForm open={open} onOpenChange={changeDrawer} title={isCollege ? "Add faculty or staff" : "Add team member"} description={isCollege ? "Create the staff profile, assign campuses, and optionally provide application access." : "Create the employee profile first. Login access is optional and can be adjusted later."}>
      <Form {...employeeForm}><form noValidate onSubmit={submit} className="space-y-6">
        <section className="grid gap-4 sm:grid-cols-2"><ValidatedField control={control} name="first_name" label="First name"><Input autoFocus autoComplete="given-name" /></ValidatedField><ValidatedField control={control} name="last_name" label="Last name"><Input autoComplete="family-name" /></ValidatedField><ValidatedField control={control} name="phone" label="Phone"><Input inputMode="tel" autoComplete="tel" /></ValidatedField><ValidatedField control={control} name="email" label="Email"><Input type="email" autoComplete="email" /></ValidatedField><ValidatedField control={control} name="designation" label="Designation"><Input /></ValidatedField><ValidatedField control={control} name="joining_date" label="Joining date"><Input type="date" /></ValidatedField>{can("employees.compensation.view") && <ValidatedField control={control} name="salary" label="Monthly salary (INR)"><Input inputMode="decimal" /></ValidatedField>}</section>
        <FormField control={control} name="location_ids" render={() => <FormItem><section><div className="mb-3"><FormLabel className="font-display text-xl font-semibold">{isCollege ? "Campuses" : "Locations"}</FormLabel><p className="mt-1 text-xs text-muted-foreground">Select where this person works.</p></div><div className="grid gap-2 sm:grid-cols-2">{locations.map((location) => <CheckCard key={location.id} label={location.name} checked={selectedLocationIds.includes(location.id)} onChange={() => toggleFormList(employeeForm, "location_ids", location.id)} />)}</div><FormMessage className="mt-2" /></section></FormItem>} />
        {can("roles.manage") ? <section className="rounded-2xl border bg-secondary/35 p-4"><FormField control={control} name="create_login" render={({ field }) => <FormItem><CheckRow label="Give this person app login" checked={field.value} onChange={field.onChange} /></FormItem>} />{createLogin && <div className="mt-5 space-y-5"><ValidatedField control={control} name="password" label="Temporary password"><Input type="password" autoComplete="new-password" /></ValidatedField><PasswordStrength password={temporaryPassword} compact /><FormField control={control} name="role_ids" render={() => <FormItem><FormLabel>Starting roles</FormLabel><div className="mt-2 grid gap-2 sm:grid-cols-2">{roles.filter((role) => role.is_active).map((role) => <CheckCard key={role.id} label={role.name} checked={selectedRoleIds.includes(role.id)} onChange={() => toggleFormList(employeeForm, "role_ids", role.id)} />)}</div><FormMessage /></FormItem>} /><p className="text-xs text-muted-foreground">They will verify their email before using the account. You can refine location and {entityName} reach in Access.</p></div>}</section> : <div className="rounded-2xl border p-4 text-sm text-muted-foreground"><IdentificationBadge className="mb-2" />An owner can add login access after this employee profile is created.</div>}
        <FormRootError error={formState.errors.root?.server} />
        <Button type="submit" loading={formState.isSubmitting || createState.isLoading} loadingText="Adding..." className="h-12 w-full">{isCollege ? "Add faculty or staff" : "Add team member"}</Button>
      </form></Form>
    </DrawerForm>
  </PageShell>;
}

function ValidatedField({ control, name, label, children }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />; }
function CheckRow({ label, checked, onChange }) { return <label className="flex cursor-pointer items-center gap-3 text-sm font-medium"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />{label}</label>; }
function CheckCard({ label, checked, onChange }) { return <label className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-sm ${checked ? "border-accent bg-accent/5" : "bg-card"}`}><input type="checkbox" checked={checked} onChange={onChange} />{label}</label>; }
function toggleFormList(form, key, id) { const current = form.getValues(key) || []; form.setValue(key, current.includes(id) ? current.filter((value) => value !== id) : [...current, id], { shouldDirty: true, shouldValidate: true }); }
