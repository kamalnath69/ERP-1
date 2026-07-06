import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";

export default function Users() {
  const { can } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);

  const load = () => api.get("/users").then((r) => setUsers(r.data));
  useEffect(() => {
    load();
    if (can("roles.manage")) api.get("/roles").then((r) => setRoles(r.data));
  }, [can]);

  return (
    <div className="space-y-6" data-testid="users-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Users</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Team & user accounts</h1>
        </div>
        {can("users.manage") && <NewUserDialog roles={roles} onCreated={load} />}
      </header>

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3">Name</th>
                <th className="text-left px-4 py-3">Email</th>
                <th className="text-left px-4 py-3">Phone</th>
                <th className="text-left px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && <tr><td colSpan={4} className="text-center py-10 text-muted-foreground">No users.</td></tr>}
              {users.map((u) => (
                <tr key={u.id} className="border-t border-border" data-testid={`user-row-${u.email}`}>
                  <td className="px-4 py-3">{u.first_name} {u.last_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                  <td className="px-4 py-3 font-mono">{u.phone || "—"}</td>
                  <td className="px-4 py-3"><span className={`text-xs px-2 py-1 rounded-sm font-mono uppercase ${u.is_active ? "bg-emerald-100 text-emerald-800" : "bg-muted"}`}>{u.is_active ? "active" : "inactive"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function NewUserDialog({ roles, onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", first_name: "", last_name: "", password: "", phone: "" });
  const [roleIds, setRoleIds] = useState(new Set());
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/users", { ...form, role_ids: Array.from(roleIds) });
      toast.success("User created");
      setOpen(false);
      setForm({ email: "", first_name: "", last_name: "", password: "", phone: "" });
      setRoleIds(new Set());
      onCreated();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const toggle = (id) => { const s = new Set(roleIds); s.has(id) ? s.delete(id) : s.add(id); setRoleIds(s); };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-user-btn"><Plus size={14} className="mr-2" /> New user</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">New user</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div><Label>First name</Label><Input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="rounded-sm" data-testid="new-user-fn" /></div>
          <div><Label>Last name</Label><Input required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="rounded-sm" /></div>
          <div className="col-span-2"><Label>Email</Label><Input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="rounded-sm" data-testid="new-user-email" /></div>
          <div className="col-span-2"><Label>Password (min 8)</Label><Input required type="password" minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="rounded-sm" /></div>
          <div className="col-span-2"><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="rounded-sm font-mono" /></div>
          <div className="col-span-2">
            <Label className="mb-2 block">Roles</Label>
            <div className="grid grid-cols-2 gap-2 border border-border p-3 max-h-48 overflow-y-auto">
              {roles.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={roleIds.has(r.id)} onCheckedChange={() => toggle(r.id)} />
                  {r.name}
                </label>
              ))}
            </div>
          </div>
          <div className="col-span-2 flex justify-end pt-2"><Button type="submit" className="rounded-sm" data-testid="new-user-submit">Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
