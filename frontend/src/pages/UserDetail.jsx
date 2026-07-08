import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
  ArrowLeft, CheckCircle, XCircle, Circle, ShieldCheck, FloppyDisk, TrashSimple,
  MagnifyingGlass,
} from "@phosphor-icons/react";
import UserAIScopes from "@/components/UserAIScopes";

// Three possible states per (user, permission):
//   inherit  -> no override row (falls back to role); UI value: undefined
//   allow    -> override row with granted=true
//   deny     -> override row with granted=false
const STATE = {
  INHERIT: "inherit",
  ALLOW: "allow",
  DENY: "deny",
};

export default function UserDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const canManageRoles = can("roles.manage");

  const [detail, setDetail] = useState(null);
  const [permissions, setPermissions] = useState([]); // catalogue
  const [overrides, setOverrides] = useState({}); // { permission_id: 'inherit'|'allow'|'deny' }
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");

  const load = async () => {
    const [d, p] = await Promise.all([
      api.get(`/users/${id}/detail`),
      api.get(`/roles/permissions`),
    ]);
    setDetail(d.data);
    setPermissions(p.data);
    const init = {};
    for (const o of d.data.overrides || []) {
      init[o.permission_id] = o.granted ? STATE.ALLOW : STATE.DENY;
    }
    setOverrides(init);
    setDirty(false);
  };

  useEffect(() => {
    load().catch(() => toast.error("Failed to load user"));
  }, [id]);

  const rolePermIds = useMemo(() => new Set(detail?.role_permission_ids || []), [detail]);
  const groupedPerms = useMemo(() => {
    const map = new Map();
    for (const p of permissions) {
      if (q && !`${p.code} ${p.label} ${p.module}`.toLowerCase().includes(q.toLowerCase())) continue;
      if (!map.has(p.module)) map.set(p.module, []);
      map.get(p.module).push(p);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [permissions, q]);

  const stateFor = (pid) => overrides[pid] || STATE.INHERIT;
  const setState = (pid, s) => {
    setOverrides((prev) => {
      const next = { ...prev };
      if (s === STATE.INHERIT) delete next[pid];
      else next[pid] = s;
      return next;
    });
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        overrides: Object.entries(overrides).map(([permission_id, s]) => ({
          permission_id,
          granted: s === STATE.ALLOW,
        })),
      };
      await api.put(`/users/${id}/overrides`, payload);
      toast.success("Permission overrides saved");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save overrides");
    } finally {
      setSaving(false);
    }
  };

  const clearAll = async () => {
    if (!window.confirm("Clear ALL user-level permission overrides for this user?")) return;
    try {
      await api.delete(`/users/${id}/overrides`);
      toast.success("Overrides cleared");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to clear");
    }
  };

  if (!detail) return <div className="text-sm text-muted-foreground">Loading…</div>;

  const u = detail.user;
  const initials = (u.first_name?.[0] || "?") + (u.last_name?.[0] || "");

  return (
    <div className="space-y-6" data-testid="user-detail-page">
      <div>
        <Link to="/app/users" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 mb-2">
          <ArrowLeft size={12} /> Back to Users
        </Link>
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-sm bg-secondary flex items-center justify-center overflow-hidden">
            {u.avatar_base64 ? (
              <img src={u.avatar_base64} alt={u.first_name} className="w-full h-full object-cover" />
            ) : (
              <span className="text-xl font-display font-bold">{initials}</span>
            )}
          </div>
          <div className="flex-1">
            <h1 className="text-3xl font-display font-bold tracking-tight">
              {u.first_name} {u.last_name}
            </h1>
            <p className="text-sm text-muted-foreground">{u.email}</p>
            {u.designation && <p className="text-sm mt-1">{u.designation}</p>}
            <div className="mt-2 flex gap-2 flex-wrap">
              {detail.roles.map((r) => (
                <Badge key={r.id} variant="outline" className="rounded-sm">
                  {r.name}
                </Badge>
              ))}
              {u.is_active ? (
                <Badge className="rounded-sm bg-accent/20 text-accent border-accent">Active</Badge>
              ) : (
                <Badge className="rounded-sm bg-destructive/20 text-destructive border-destructive">Inactive</Badge>
              )}
            </div>
          </div>
        </div>
      </div>

      {u.bio && (
        <Card className="rounded-sm border-border">
          <CardHeader>
            <CardTitle className="font-display text-lg">About</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{u.bio}</p>
          </CardContent>
        </Card>
      )}

      <UserAIScopes
        userId={id}
        canManage={can("ai.scopes.manage") || can("roles.manage")}
      />

      <Card className="rounded-sm border-border">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="font-display text-lg flex items-center gap-2">
            <ShieldCheck size={16} className="text-accent" />
            Permission overrides
          </CardTitle>
          <div className="flex items-center gap-2">
            <div className="relative">
              <MagnifyingGlass size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search permission…"
                className="pl-7 h-8 w-56 rounded-sm"
                data-testid="perm-search"
              />
            </div>
            {canManageRoles && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  className="rounded-sm text-destructive"
                  onClick={clearAll}
                  data-testid="perm-clear-all"
                >
                  <TrashSimple size={14} className="mr-1" /> Clear
                </Button>
                <Button
                  size="sm"
                  className="rounded-sm"
                  disabled={!dirty || saving}
                  onClick={save}
                  data-testid="perm-save"
                >
                  <FloppyDisk size={14} className="mr-1" /> {saving ? "Saving…" : "Save"}
                </Button>
              </>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Overrides win over role-granted permissions. <b>Inherit</b> uses role default;{" "}
            <b>Allow</b> forces grant even if role denies; <b>Deny</b> revokes even if role grants.
          </p>
          <Legend />

          {groupedPerms.length === 0 && (
            <div className="text-sm text-muted-foreground py-4">No permissions match.</div>
          )}

          {groupedPerms.map(([module, perms]) => (
            <div key={module} className="border border-border">
              <div className="px-3 py-2 bg-secondary/40 overline">{module}</div>
              <div className="divide-y divide-border">
                {perms.map((p) => {
                  const inRole = rolePermIds.has(p.id);
                  const s = stateFor(p.id);
                  const effective =
                    s === STATE.ALLOW ? true :
                    s === STATE.DENY ? false :
                    inRole;
                  return (
                    <div key={p.id} className="px-3 py-2 grid grid-cols-12 gap-2 items-center text-sm">
                      <div className="col-span-5">
                        <div className="font-mono text-[11px] text-muted-foreground">{p.code}</div>
                        <div className="text-sm">{p.label}</div>
                      </div>
                      <div className="col-span-2 text-[11px] uppercase tracking-widest text-muted-foreground">
                        Role: {inRole ? <span className="text-accent">granted</span> : <span>—</span>}
                      </div>
                      <div className="col-span-3 flex gap-1">
                        <StateButton
                          active={s === STATE.INHERIT}
                          disabled={!canManageRoles}
                          onClick={() => setState(p.id, STATE.INHERIT)}
                          icon={Circle}
                          label="Inherit"
                          testid={`perm-${p.code}-inherit`}
                        />
                        <StateButton
                          active={s === STATE.ALLOW}
                          disabled={!canManageRoles}
                          onClick={() => setState(p.id, STATE.ALLOW)}
                          icon={CheckCircle}
                          label="Allow"
                          tone="allow"
                          testid={`perm-${p.code}-allow`}
                        />
                        <StateButton
                          active={s === STATE.DENY}
                          disabled={!canManageRoles}
                          onClick={() => setState(p.id, STATE.DENY)}
                          icon={XCircle}
                          label="Deny"
                          tone="deny"
                          testid={`perm-${p.code}-deny`}
                        />
                      </div>
                      <div className="col-span-2 text-right">
                        {effective ? (
                          <Badge className="rounded-sm bg-accent/20 text-accent border-accent">Effective</Badge>
                        ) : (
                          <Badge variant="outline" className="rounded-sm text-muted-foreground">No</Badge>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function StateButton({ active, disabled, onClick, icon: Icon, label, tone, testid }) {
  const toneClass =
    tone === "allow"
      ? active ? "border-accent text-accent" : ""
      : tone === "deny"
      ? active ? "border-destructive text-destructive" : ""
      : active ? "border-foreground" : "";
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      data-testid={testid}
      className={`text-[11px] uppercase tracking-widest border border-border px-2 py-1 flex items-center gap-1 hover:bg-secondary disabled:opacity-50 ${toneClass} ${active ? "bg-secondary" : ""}`}
    >
      <Icon size={12} /> {label}
    </button>
  );
}

function Legend() {
  return (
    <div className="flex gap-4 text-[11px] text-muted-foreground">
      <span className="flex items-center gap-1"><Circle size={12} /> Inherit from role</span>
      <span className="flex items-center gap-1"><CheckCircle size={12} className="text-accent" /> Force allow</span>
      <span className="flex items-center gap-1"><XCircle size={12} className="text-destructive" /> Force deny</span>
    </div>
  );
}
