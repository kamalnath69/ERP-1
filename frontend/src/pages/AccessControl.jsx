import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  CheckCircle, Copy, Lock, MagnifyingGlass, MapPin, ShieldCheck, SpinnerGap,
  UserFocus, UsersThree, WarningCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, MetricCard, PageHeader, PageShell,
  StatusBadge, Surface,
} from "@/components/system";
import { EntityAvatar } from "@/components/entities/EntityProfile";
import { clientLabel } from "@/app/routeManifest";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import {
  useCreateRoleMutation, useDeleteRoleMutation, useDuplicateRoleMutation,
  useGetAccessAuditQuery, useGetAccessClientsPageQuery, useGetAccessUsersPageQuery,
  useGetAccessWorkspaceQuery, useLazyGetAccessConfigurationQuery,
  usePreviewAccessMutation, useSaveAccessMutation, useUpdateRoleMutation,
} from "@/features/access/accessApi";
import { cn } from "@/lib/utils";
import useCursorPagination from "@/hooks/useCursorPagination";

const emptyConfig = { role_ids: [], permission_overrides: [], location_mode: "full", location_ids: [], client_mode: "all", client_ids: [], selected_clients: [], version: 1 };
const permissionDependencies = {
  "clients.manage": ["clients.view"], "clients.media.manage": ["clients.media.view", "clients.view"],
  "inventory.adjust": ["inventory.view"], "appointments.manage": ["appointments.view"],
  "sales.manage": ["sales.view"], "gym.memberships.manage": ["gym.memberships.view"],
  "gym.attendance.mark": ["gym.attendance.view"], "clinical.write": ["clinical.view"],
  "clinical.sign": ["clinical.write", "clinical.view"], "documents.manage": ["documents.view"],
};

export default function AccessControl() {
  const { user: currentUser, can } = useAuth();
  const { organization } = useBusiness();
  const isCollege = organization?.industry === "college";
  const entityLabel = clientLabel(organization?.industry);
  const entitySingular = clientLabel(organization?.industry, false);
  const workspace = useGetAccessWorkspaceQuery(undefined, QUERY_POLICIES.collaborative);
  const data = workspace.data;
  const [tab, setTab] = useState("people");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [permissionSearch, setPermissionSearch] = useState("");
  const [accessUser, setAccessUser] = useState(null);
  const [config, setConfig] = useState(emptyConfig);
  const [configReady, setConfigReady] = useState(false);
  const [roleEditor, setRoleEditor] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const [comparison, setComparison] = useState([]);
  const [loadConfiguration] = useLazyGetAccessConfigurationQuery();
  const [previewAccess, previewState] = usePreviewAccessMutation();
  const [saveAccess, saveState] = useSaveAccessMutation();
  const [createRole, createState] = useCreateRoleMutation();
  const [updateRole, updateState] = useUpdateRoleMutation();
  const [duplicateRole, duplicateState] = useDuplicateRoleMutation();
  const [deleteRole, deleteState] = useDeleteRoleMutation();
  const userPaging = useCursorPagination(JSON.stringify({ q: deferredSearch }));
  const usersQuery = useGetAccessUsersPageQuery({ q: deferredSearch, cursor: userPaging.cursor, limit: 25 }, QUERY_POLICIES.collaborative);
  const auditPaging = useCursorPagination("access-audit");
  const audit = useGetAccessAuditQuery({ cursor: auditPaging.cursor, limit: 50 }, withSkip(QUERY_POLICIES.operational, !data?.capabilities?.view_audit || tab !== "audit"));
  const { accept: acceptUsers } = userPaging;
  const { accept: acceptAudit } = auditPaging;
  useEffect(() => { acceptUsers(usersQuery.data); }, [acceptUsers, usersQuery.data]);
  useEffect(() => { acceptAudit(audit.data); }, [acceptAudit, audit.data]);

  const roles = useMemo(() => data?.roles || [], [data?.roles]);
  const permissions = useMemo(() => data?.permissions || [], [data?.permissions]);
  const users = userPaging.items;
  const locations = useMemo(() => data?.locations || [], [data?.locations]);
  const permissionGroups = useMemo(() => groupBy(permissions.filter((row) => `${row.label} ${row.module}`.toLowerCase().includes(permissionSearch.toLowerCase())), "module"), [permissions, permissionSearch]);
  const rolePermissionIds = useMemo(() => new Set(roles.filter((role) => config.role_ids.includes(role.id)).flatMap((role) => role.permission_ids || [])), [roles, config.role_ids]);
  const effectiveIds = useMemo(() => {
    const ids = new Set(rolePermissionIds);
    config.permission_overrides.forEach((item) => item.granted ? ids.add(item.permission_id) : ids.delete(item.permission_id));
    return ids;
  }, [config.permission_overrides, rolePermissionIds]);
  const dependencyWarnings = useMemo(() => {
    const codes = new Set(permissions.filter((row) => effectiveIds.has(row.id)).map((row) => row.code));
    return Object.entries(permissionDependencies).flatMap(([code, required]) => codes.has(code) ? required.filter((need) => !codes.has(need)).map((need) => `${labelFor(permissions, code)} also needs ${labelFor(permissions, need)}.`) : []);
  }, [effectiveIds, permissions]);

  useEffect(() => {
    if (!accessUser || !configReady) return undefined;
    const timer = setTimeout(() => previewAccess({ userId: accessUser.id, configuration: config }), 350);
    return () => clearTimeout(timer);
  }, [accessUser, config, configReady, previewAccess]);

  if (workspace.isError && !data) return <PageShell><ErrorState title="Access control could not be loaded" description={workspace.error?.data?.detail} retry={workspace.refetch} /></PageShell>;

  const openAccess = async (person) => {
    setAccessUser(person); setConfigReady(false); previewState.reset();
    try {
      const loaded = await loadConfiguration(person.id, true).unwrap();
      setConfig({ ...emptyConfig, ...loaded }); setConfigReady(true);
    } catch (error) {
      toast.error(error?.data?.detail || "Could not load this person's access"); setAccessUser(null);
    }
  };
  const saveConfiguration = async () => {
    try {
      await saveAccess({ userId: accessUser.id, configuration: config }).unwrap();
      toast.success("Access updated"); setAccessUser(null); setConfigReady(false);
    } catch (error) { toast.error(error?.data?.detail || "Could not update access"); }
  };
  const openRole = (role = null, mode = "create") => {
    const source = role || {};
    setRoleEditor({
      mode, sourceId: source.id, name: mode === "duplicate" ? `${source.name} custom` : source.name || "",
      description: mode === "duplicate" ? `Customized from ${source.name}` : source.description || "",
      permission_ids: source.permission_ids || [], version: source.version,
    });
  };
  const saveRoleEditor = async () => {
    const payload = { name: roleEditor.name.trim(), description: roleEditor.description.trim() || null, permission_ids: roleEditor.permission_ids };
    try {
      if (roleEditor.mode === "create") await createRole(payload).unwrap();
      if (roleEditor.mode === "edit") await updateRole({ roleId: roleEditor.sourceId, version: roleEditor.version, ...payload }).unwrap();
      if (roleEditor.mode === "duplicate") await duplicateRole({ roleId: roleEditor.sourceId, ...payload }).unwrap();
      toast.success(roleEditor.mode === "edit" ? "Role updated" : "Role created"); setRoleEditor(null);
    } catch (error) { toast.error(error?.data?.detail || "Could not save role"); }
  };
  const applyRoleAction = async () => {
    const { role, action } = confirmation;
    if (!data?.capabilities?.create_custom_roles) {
      toast.error("Custom role management is not available on this plan");
      setConfirmation(null);
      return;
    }
    try {
      if (action === "delete") await deleteRole(role.id).unwrap();
      else await updateRole({ roleId: role.id, version: role.version, is_active: !role.is_active }).unwrap();
      toast.success(action === "delete" ? "Role deleted" : role.is_active ? "Role deactivated" : "Role activated"); setConfirmation(null);
    } catch (error) { toast.error(error?.data?.detail || "Could not update role"); }
  };

  const peopleColumns = [
    { key: "person", label: "Person", render: (row) => <div className="flex items-center gap-3"><EntityAvatar name={`${row.first_name} ${row.last_name}`} size="md" /><div><div className="font-semibold">{row.first_name} {row.last_name}{row.id === currentUser.id && <span className="ml-2 text-xs text-muted-foreground">You</span>}</div><div className="mt-1 text-xs text-muted-foreground">{row.email}</div></div></div> },
    { key: "roles", label: "Roles", render: (row) => <div className="flex flex-wrap gap-1.5">{row.roles?.length ? row.roles.map((role) => <StatusBadge key={role.id} status="neutral" label={role.name} />) : <span className="text-muted-foreground">No role</span>}</div> },
    { key: "status", label: "Account", render: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} /> },
    { key: "action", label: "", render: (row) => <Button size="sm" variant="outline" disabled={row.id === currentUser.id} onClick={(event) => { event.stopPropagation(); openAccess(row); }}>Manage access</Button> },
  ];

  return <PageShell className="reveal">
    <PageHeader eyebrow="Responsibilities and reach" title="Access control" description={isCollege ? "Set what each faculty or staff member can do, which campuses they can use, and which students they can support." : `Set what each person can do, which locations they can use, and which ${entityLabel.toLowerCase()} they can work with.`} />
    <div className="grid gap-3 sm:grid-cols-3"><MetricCard metric={{ label: "Role templates", value: roles.length }} loading={!data} /><MetricCard metric={{ label: isCollege ? "Faculty & staff accounts" : "Team accounts", value: usersQuery.data?.summary?.total || 0 }} loading={usersQuery.isLoading && !usersQuery.data} /><MetricCard metric={{ label: isCollege ? "Campuses" : "Business locations", value: locations.length }} loading={!data} /></div>

    <Tabs value={tab} onValueChange={setTab}><TabsList className="h-auto w-full justify-start overflow-x-auto rounded-xl sm:w-fit"><TabsTrigger value="people">People</TabsTrigger><TabsTrigger value="roles">Roles</TabsTrigger><TabsTrigger value="permissions">Permissions</TabsTrigger>{data?.capabilities?.view_audit && <TabsTrigger value="audit">Audit</TabsTrigger>}</TabsList>
      <TabsContent value="people" className="mt-5 space-y-4"><Surface className="p-3"><div className="relative"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search people or roles" /></div></Surface><DataTable loading={usersQuery.isLoading && !users.length} rows={users} columns={peopleColumns} empty={<EmptyState variant={search.trim() ? "filtered" : "section"} alignment="left" icon={UsersThree} title={search.trim() ? `No ${isCollege ? "faculty or staff" : "team"} accounts match this search` : isCollege ? "No faculty or staff accounts yet" : "No team accounts yet"} description={search.trim() ? "Clear the search to return to every account." : isCollege ? "Create login access from Faculty & staff, then assign College responsibilities here." : "Create employee login access from Team, then assign responsibilities here."} primaryAction={search.trim() ? <Button variant="outline" onClick={() => setSearch("")}>Clear search</Button> : null} />} />{(users.length > 0 || usersQuery.data?.has_more) && <CursorListFooter count={users.length} noun="accounts" hasMore={Boolean(usersQuery.data?.has_more)} loading={usersQuery.isFetching} error={usersQuery.isError} onLoadMore={() => userPaging.loadMore(usersQuery.data?.next_cursor)} onRetry={usersQuery.refetch} />}</TabsContent>

      <TabsContent value="roles" className="mt-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted-foreground">Built-in templates stay safe. Duplicate one when your {isCollege ? "College" : "business"} needs a variation.</p>{data?.capabilities?.create_custom_roles ? <Button onClick={() => openRole()}><ShieldCheck className="mr-2" />Create role</Button> : <div className="inline-flex items-center gap-2 rounded-xl border bg-secondary px-3 py-2 text-xs text-muted-foreground"><Lock />Custom roles are available on Growth and above</div>}</div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{roles.map((role) => <Surface key={role.id} className={cn("p-5", !role.is_active && "opacity-65")}><div className="flex items-start justify-between gap-3"><div className="grid h-11 w-11 place-items-center rounded-2xl bg-secondary"><ShieldCheck size={23} /></div><div className="flex gap-2"><StatusBadge status={role.is_active ? "active" : "inactive"} />{role.is_system && <StatusBadge status="neutral" label="Built in" />}</div></div><h2 className="mt-4 font-display text-2xl font-semibold">{role.name}</h2><p className="mt-2 min-h-10 text-sm text-muted-foreground">{role.description || "Custom responsibilities for your team."}</p><div className="mt-5 flex items-center justify-between border-t pt-4 text-xs text-muted-foreground"><span>{role.permission_ids.length} permissions</span><span>{role.user_count} {role.user_count === 1 ? "person" : "people"}</span></div><div className="mt-4 flex flex-wrap gap-2">{role.is_system ? <Button size="sm" variant="outline" disabled={!data.capabilities.create_custom_roles} onClick={() => openRole(role, "duplicate")}><Copy className="mr-2" />Duplicate</Button> : <><Button size="sm" variant="outline" disabled={!data.capabilities.create_custom_roles} onClick={() => openRole(role, "edit")}>Edit</Button><Button size="sm" variant="ghost" disabled={!data.capabilities.create_custom_roles} onClick={() => setConfirmation({ role, action: "toggle" })}>{role.is_active ? "Deactivate" : "Activate"}</Button>{!role.user_count && <Button size="sm" variant="ghost" disabled={!data.capabilities.create_custom_roles} className="text-danger" onClick={() => setConfirmation({ role, action: "delete" })}>Delete</Button>}</>}</div><label className="mt-4 flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={comparison.includes(role.id)} disabled={!comparison.includes(role.id) && comparison.length >= 2} onChange={() => setComparison((current) => current.includes(role.id) ? current.filter((id) => id !== role.id) : [...current, role.id])} />Compare role</label></Surface>)}</div>
        {comparison.length === 2 && <RoleComparison roles={roles.filter((role) => comparison.includes(role.id))} permissions={permissions} />}
      </TabsContent>

      <TabsContent value="permissions" className="mt-5 space-y-4"><Surface className="p-3"><div className="relative"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={permissionSearch} onChange={(event) => setPermissionSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search permitted actions" /></div></Surface><div className="grid gap-4 lg:grid-cols-2">{Object.entries(permissionGroups).map(([module, list]) => <Surface className="p-5" key={module}><h2 className="font-display text-xl font-semibold capitalize">{humanize(module)}</h2><div className="mt-3 divide-y">{list.map((permission) => <div key={permission.id} className="py-3"><div className="text-sm font-medium">{permission.label}</div><div className="mt-1 text-xs text-muted-foreground">{permission.description || `Controls ${humanize(permission.code)}.`}</div></div>)}</div></Surface>)}</div></TabsContent>

      <TabsContent value="audit" className="mt-5"><DataTable loading={audit.isLoading && !auditPaging.items.length} rows={auditPaging.items} columns={[{ key: "summary", label: "Change", render: (row) => <div><div className="font-semibold">{row.summary || humanize(row.action)}</div><div className="mt-1 text-xs text-muted-foreground">{humanize(row.action)}</div></div> }, { key: "actor", label: "Changed by" }, { key: "created_at", label: "When", render: (row) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(row.created_at)) }]} empty={<EmptyState variant="section" alignment="left" icon={ShieldCheck} title="No access changes recorded" description="Role and personal-access changes will appear here." />} />{(auditPaging.items.length > 0 || audit.data?.has_more) && <CursorListFooter count={auditPaging.items.length} noun="changes" hasMore={Boolean(audit.data?.has_more)} loading={audit.isFetching} error={audit.isError} onLoadMore={() => auditPaging.loadMore(audit.data?.next_cursor)} onRetry={audit.refetch} />}</TabsContent>
    </Tabs>

    <DrawerForm open={Boolean(accessUser)} onOpenChange={(open) => { if (!open) { setAccessUser(null); setConfigReady(false); } }} title={accessUser ? `Access for ${accessUser.first_name} ${accessUser.last_name}` : "Access"} description="Role defaults and personal scope are saved together.">
      {!configReady ? <div className="space-y-4">{[1, 2, 3].map((item) => <div key={item} className="h-24 animate-pulse rounded-2xl bg-secondary" />)}</div> : <div className="space-y-7">
        <EditorSection number="1" title="Responsibilities" copy="Choose one or more roles as the starting point."><div className="grid gap-3 sm:grid-cols-2">{roles.filter((role) => role.is_active).map((role) => <Choice key={role.id} checked={config.role_ids.includes(role.id)} title={role.name} copy={`${role.permission_ids.length} permitted actions`} onClick={() => toggleConfig(setConfig, "role_ids", role.id)} />)}</div></EditorSection>
        <EditorSection number="2" title={isCollege ? "Campus reach" : "Location reach"} copy={isCollege ? "All campuses includes campuses added later. Restricted access stays within your selection." : "All locations includes locations added later. Restricted access stays within your selection."}><Mode value={config.location_mode} onChange={(value) => setConfig((current) => ({ ...current, location_mode: value, location_ids: value === "full" ? [] : current.location_ids }))} options={[["full", isCollege ? "All campuses" : "All locations"], ["restricted", isCollege ? "Selected campuses" : "Selected locations"]]} />{config.location_mode === "restricted" && <div className="mt-3 grid gap-3 sm:grid-cols-2">{locations.map((location) => <Choice key={location.id} checked={config.location_ids.includes(location.id)} title={location.name} copy={location.city || location.code} onClick={() => toggleConfig(setConfig, "location_ids", location.id)} />)}</div>}</EditorSection>
        <EditorSection number="3" title={`${entityLabel} reach`} copy={isCollege ? "Choose all students in permitted campuses, assigned students, or a fixed selection." : `Choose every ${entityLabel.toLowerCase()} in permitted locations, assigned relationships, or a fixed selection.`}><Mode value={config.client_mode} onChange={(value) => setConfig((current) => ({ ...current, client_mode: value, client_ids: value === "selected" ? current.client_ids : [] }))} options={[["all", `All ${entityLabel.toLowerCase()}`], ["assigned", "Assigned only"], ["selected", "Selected only"]]} />{config.client_mode === "selected" && <ClientPicker selectedClients={config.selected_clients || []} selected={config.client_ids} onToggle={(id) => toggleConfig(setConfig, "client_ids", id)} entityLabel={entityLabel} />}</EditorSection>
        <EditorSection number="4" title="Personal adjustments" copy="Use sparingly. A personal block always wins over a role allowance."><div className="space-y-3">{Object.entries(groupBy(permissions, "module")).map(([module, list]) => <details className="overflow-hidden rounded-2xl border" key={module}><summary className="cursor-pointer bg-secondary px-4 py-3 font-semibold capitalize">{humanize(module)}</summary><div className="divide-y">{list.map((permission) => { const override = config.permission_overrides.find((item) => item.permission_id === permission.id); const mode = override ? override.granted ? "allow" : "deny" : "inherit"; return <div className="flex flex-col justify-between gap-3 p-3 sm:flex-row sm:items-center" key={permission.id}><div><div className="text-sm font-medium">{permission.label}</div><div className="mt-1 text-xs text-muted-foreground">Role default: {rolePermissionIds.has(permission.id) ? "allowed" : "not allowed"}</div></div><select className={cn("h-9 rounded-xl border bg-background px-3 text-sm", mode === "deny" && "text-danger", mode === "allow" && "text-positive")} value={mode} onChange={(event) => setOverride(setConfig, permission.id, event.target.value)}><option value="inherit">Use role default</option><option value="allow">Allow personally</option><option value="deny">Block personally</option></select></div>; })}</div></details>)}</div></EditorSection>
        <AccessPreview loading={previewState.isLoading} error={previewState.error} preview={previewState.data} localCount={effectiveIds.size} warnings={dependencyWarnings} entitySingular={entitySingular} />
        <Button className="h-12 w-full" disabled={saveState.isLoading || previewState.isLoading || Boolean(previewState.error) || dependencyWarnings.length > 0} onClick={saveConfiguration}>{saveState.isLoading ? <><SpinnerGap className="mr-2 animate-spin" />Saving access</> : "Save access"}</Button>
      </div>}
    </DrawerForm>

    <RoleEditor editor={roleEditor} setEditor={setRoleEditor} groups={groupBy(permissions, "module")} onSave={saveRoleEditor} saving={createState.isLoading || updateState.isLoading || duplicateState.isLoading} />
    <AlertDialog open={Boolean(confirmation)} onOpenChange={(open) => !open && setConfirmation(null)}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{confirmation?.action === "delete" ? "Delete this role?" : `${confirmation?.role?.is_active ? "Deactivate" : "Activate"} this role?`}</AlertDialogTitle><AlertDialogDescription>{confirmation?.action === "delete" ? "The role has no assigned people and will be removed permanently." : `${confirmation?.role?.user_count || 0} people currently use this role. Their effective access may change immediately.`}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Keep role</AlertDialogCancel><AlertDialogAction disabled={deleteState.isLoading || updateState.isLoading} onClick={applyRoleAction}>Confirm</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </PageShell>;
}

function AccessPreview({ loading, error, preview, localCount, warnings, entitySingular }) {
  return <Surface className="bg-primary p-5 text-primary-foreground"><div className="flex items-start gap-3"><CheckCircle className="shrink-0 text-accent" size={25} /><div className="min-w-0 flex-1"><h3 className="font-display text-2xl font-semibold">Effective access preview</h3>{loading ? <p className="mt-2 flex items-center gap-2 text-sm opacity-70"><SpinnerGap className="animate-spin" />Checking boundaries</p> : error ? <p className="mt-2 text-sm text-red-200">{error?.data?.detail || "This configuration is not valid."}</p> : <><p className="mt-2 text-sm opacity-70">{preview?.effective_permissions?.length ?? localCount} actions · {scopeText(preview?.location_scope, "location")} · {scopeText(preview?.client_scope, entitySingular.toLowerCase())}</p><div className="mt-4 flex flex-wrap gap-1.5">{preview?.effective_permissions?.slice(0, 14).map((permission) => <span key={permission.id} className="rounded-full bg-white/10 px-2.5 py-1 text-[10px]">{permission.label}</span>)}</div></>}{[...(preview?.warnings || []), ...warnings].map((warning) => <p key={warning} className="mt-3 flex gap-2 text-xs text-amber-200"><WarningCircle className="shrink-0" />{warning}</p>)}</div></div></Surface>;
}

function RoleEditor({ editor, setEditor, groups, onSave, saving }) {
  const [search, setSearch] = useState("");
  if (!editor) return null;
  const filtered = Object.fromEntries(Object.entries(groups).map(([module, rows]) => [module, rows.filter((row) => row.label.toLowerCase().includes(search.toLowerCase()))]).filter(([, rows]) => rows.length));
  const toggle = (id) => setEditor((current) => ({ ...current, permission_ids: current.permission_ids.includes(id) ? current.permission_ids.filter((value) => value !== id) : [...current.permission_ids, id] }));
  return <Dialog open onOpenChange={(open) => !open && setEditor(null)}><DialogContent className="premium-scrollbar max-h-[92vh] overflow-y-auto sm:max-w-4xl"><DialogHeader><DialogTitle className="font-display text-3xl">{editor.mode === "edit" ? "Edit role" : editor.mode === "duplicate" ? "Customize role template" : "Create role"}</DialogTitle></DialogHeader><div className="space-y-5"><div className="grid gap-4 sm:grid-cols-2"><Field label="Role name"><Input value={editor.name} onChange={(event) => setEditor({ ...editor, name: event.target.value })} /></Field><Field label="Description"><Input value={editor.description} onChange={(event) => setEditor({ ...editor, description: event.target.value })} /></Field></div><div className="relative"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="pl-10" placeholder="Search permissions" /></div>{Object.entries(filtered).map(([module, list]) => <section className="rounded-2xl border p-4" key={module}><h3 className="font-semibold capitalize">{humanize(module)}</h3><div className="mt-3 grid gap-2 sm:grid-cols-2">{list.map((permission) => <label className="flex cursor-pointer gap-3 rounded-xl p-2 hover:bg-secondary" key={permission.id}><input type="checkbox" checked={editor.permission_ids.includes(permission.id)} onChange={() => toggle(permission.id)} /><span className="text-sm">{permission.label}</span></label>)}</div></section>)}<Button className="w-full" disabled={saving || editor.name.trim().length < 2} onClick={onSave}>{saving ? "Saving role..." : "Save role"}</Button></div></DialogContent></Dialog>;
}

function RoleComparison({ roles, permissions }) {
  const [left, right] = roles;
  const rows = permissions.filter((permission) => left.permission_ids.includes(permission.id) !== right.permission_ids.includes(permission.id));
  return <Surface className="overflow-hidden"><div className="border-b p-5"><h3 className="font-display text-2xl font-semibold">Role differences</h3><p className="mt-1 text-sm text-muted-foreground">Only permissions that differ are shown.</p></div>{rows.length ? <div className="divide-y">{rows.map((permission) => <div className="grid grid-cols-[1fr_5rem_5rem] items-center gap-3 px-5 py-3 text-sm" key={permission.id}><span>{permission.label}</span><span className={left.permission_ids.includes(permission.id) ? "text-positive" : "text-muted-foreground"}>{left.permission_ids.includes(permission.id) ? "Allowed" : "No"}</span><span className={right.permission_ids.includes(permission.id) ? "text-positive" : "text-muted-foreground"}>{right.permission_ids.includes(permission.id) ? "Allowed" : "No"}</span></div>)}</div> : <EmptyState variant="inline" title="These roles are identical" description="Their permitted actions currently match." className="m-4" />}</Surface>;
}

function ClientPicker({ selectedClients, selected, onToggle, entityLabel }) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const paging = useCursorPagination(JSON.stringify({ q: deferredSearch }));
  const query = useGetAccessClientsPageQuery({ q: deferredSearch, cursor: paging.cursor, limit: 25 }, QUERY_POLICIES.collaborative);
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(query.data); }, [acceptPage, query.data]);
  const selectedRows = selectedClients.filter((row) => selected.includes(row.id));
  const selectedIds = new Set(selectedRows.map((row) => row.id));
  const resultRows = paging.items.filter((row) => !selectedIds.has(row.id));
  const row = (client) => <Choice key={client.id} checked={selected.includes(client.id)} title={`${client.first_name} ${client.last_name}`} copy={client.phone || client.client_number} onClick={() => onToggle(client.id)} />;
  return <div className="mt-3 space-y-3">
    <div className="flex items-center gap-3"><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${entityLabel.toLowerCase()}`} /><span className="shrink-0 text-xs font-medium text-muted-foreground">{selected.length} selected</span></div>
    <div className="premium-scrollbar max-h-80 space-y-3 overflow-y-auto pr-1">
      {selectedRows.length > 0 && <div><p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Selected</p><div className="grid gap-2 sm:grid-cols-2">{selectedRows.map(row)}</div></div>}
      <div><p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{deferredSearch ? "Search results" : `Available ${entityLabel.toLowerCase()}`}</p><div className="grid gap-2 sm:grid-cols-2">{resultRows.map(row)}</div>{!query.isLoading && !resultRows.length && <p className="rounded-xl border p-3 text-sm text-muted-foreground">No matching {entityLabel.toLowerCase()}.</p>}</div>
    </div>
    {(paging.items.length > 0 || query.data?.has_more) && <CursorListFooter count={paging.items.length} noun={entityLabel.toLowerCase()} hasMore={Boolean(query.data?.has_more)} loading={query.isFetching} error={query.isError} onLoadMore={() => paging.loadMore(query.data?.next_cursor)} onRetry={query.refetch} />}
  </div>;
}

function EditorSection({ number, title, copy, children }) { return <section><div className="mb-4 flex gap-3"><div className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-accent font-bold text-accent-foreground">{number}</div><div><h3 className="font-display text-2xl font-semibold">{title}</h3><p className="mt-1 text-sm text-muted-foreground">{copy}</p></div></div>{children}</section>; }
function Choice({ checked, title, copy, onClick }) { return <button type="button" onClick={onClick} className={cn("rounded-2xl border p-4 text-left transition-colors", checked ? "border-accent bg-accent/5 ring-2 ring-accent/15" : "bg-card hover:bg-secondary/50")}><div className="flex justify-between gap-3"><span className="font-medium">{title}</span><span className={cn("grid h-5 w-5 place-items-center rounded-md border", checked && "border-accent bg-accent text-accent-foreground")}>{checked && <CheckCircle size={15} weight="fill" />}</span></div><div className="mt-1 text-xs text-muted-foreground">{copy}</div></button>; }
function Mode({ value, onChange, options }) { return <div className="flex flex-wrap gap-2">{options.map(([id, label]) => <Button type="button" key={id} variant={value === id ? "default" : "outline"} onClick={() => onChange(id)}>{label}</Button>)}</div>; }
function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function toggleConfig(setConfig, key, value) { setConfig((current) => ({ ...current, [key]: current[key].includes(value) ? current[key].filter((id) => id !== value) : [...current[key], value] })); }
function setOverride(setConfig, permissionId, mode) { setConfig((current) => ({ ...current, permission_overrides: mode === "inherit" ? current.permission_overrides.filter((item) => item.permission_id !== permissionId) : [...current.permission_overrides.filter((item) => item.permission_id !== permissionId), { permission_id: permissionId, granted: mode === "allow" }] })); }
function groupBy(rows, key) { return rows.reduce((result, row) => ({ ...result, [row[key] || "other"]: [...(result[row[key] || "other"] || []), row] }), {}); }
function humanize(value = "") { return String(value).replaceAll("_", " ").replaceAll(".", " "); }
function labelFor(permissions, code) { return permissions.find((row) => row.code === code)?.label || humanize(code); }
function scopeText(scope, noun) { if (!scope) return `checking ${noun} scope`; if (scope.mode === "full" || scope.mode === "all") return `all permitted ${noun}s`; if (scope.mode === "assigned") return `assigned ${noun}s only`; return `${scope.count || 0} selected ${noun}${scope.count === 1 ? "" : "s"}`; }
