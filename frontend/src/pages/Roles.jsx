import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Trash } from "@phosphor-icons/react";

export default function Roles() {
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [selectedRole, setSelectedRole] = useState(null);
  const [selectedPerms, setSelectedPerms] = useState(new Set());

  const loadRoles = () => api.get("/roles").then((r) => setRoles(r.data));

  useEffect(() => {
    loadRoles();
    api.get("/roles/permissions").then((r) => setPermissions(r.data));
  }, []);

  const openRole = async (r) => {
    const { data } = await api.get(`/roles/${r.id}`);
    setSelectedRole(data.role);
    setSelectedPerms(new Set(data.permission_ids));
  };

  const toggle = (pid) => {
    const s = new Set(selectedPerms);
    s.has(pid) ? s.delete(pid) : s.add(pid);
    setSelectedPerms(s);
  };

  const save = async () => {
    await api.patch(`/roles/${selectedRole.id}`, { permission_ids: Array.from(selectedPerms) });
    toast.success("Role updated");
    loadRoles();
  };

  const del = async () => {
    if (!selectedRole || selectedRole.is_system) return;
    await api.delete(`/roles/${selectedRole.id}`);
    toast.success("Role deleted");
    setSelectedRole(null);
    loadRoles();
  };

  const grouped = permissions.reduce((acc, p) => {
    acc[p.module] = acc[p.module] || [];
    acc[p.module].push(p);
    return acc;
  }, {});

  return (
    <div className="space-y-6" data-testid="roles-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Access Control</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Roles & Permissions</h1>
          <p className="text-sm text-muted-foreground mt-2">Every role is dynamic — clone, edit, or invent your own.</p>
        </div>
        <div className="flex items-center gap-2">
          <NewPermissionDialog onCreated={() => api.get("/roles/permissions").then((r) => setPermissions(r.data))} />
          <NewRoleDialog permissions={permissions} onCreated={loadRoles} />
        </div>
      </header>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="rounded-sm border-border">
          <CardContent className="p-0">
            {roles.map((r) => (
              <button key={r.id} onClick={() => openRole(r)}
                data-testid={`role-item-${r.slug}`}
                className={`w-full text-left px-4 py-3 border-b border-border hover:bg-secondary ${selectedRole?.id === r.id ? "bg-secondary" : ""}`}>
                <div className="flex justify-between items-baseline">
                  <div className="font-medium">{r.name}</div>
                  {r.is_system && <span className="overline">system</span>}
                </div>
                <div className="text-xs text-muted-foreground">{r.description || `Role · ${r.slug}`}</div>
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="lg:col-span-2 space-y-4">
          {selectedRole ? (
            <>
              <div className="flex items-baseline justify-between">
                <div>
                  <div className="overline">Editing</div>
                  <div className="font-display text-2xl tracking-tight">{selectedRole.name}</div>
                </div>
                <div className="flex gap-2">
                  <Button onClick={save} className="rounded-sm" data-testid="role-save-btn">Save</Button>
                  {!selectedRole.is_system && <Button variant="outline" onClick={del} className="rounded-sm" data-testid="role-delete-btn"><Trash size={14} /></Button>}
                </div>
              </div>
              {Object.entries(grouped).map(([mod, perms]) => (
                <Card key={mod} className="rounded-sm border-border">
                  <CardContent className="p-4">
                    <div className="overline mb-3">{mod}</div>
                    <div className="grid md:grid-cols-2 gap-3">
                      {perms.map((p) => (
                        <label key={p.id} className="flex items-start gap-3 cursor-pointer hover:bg-secondary/50 p-2 -m-2 rounded-sm">
                          <Checkbox checked={selectedPerms.has(p.id)} onCheckedChange={() => toggle(p.id)} data-testid={`perm-${p.code}`} />
                          <div>
                            <div className="text-sm font-medium">{p.label}</div>
                            <div className="text-xs font-mono text-muted-foreground">{p.code}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </>
          ) : (
            <Card className="rounded-sm border-border">
              <CardContent className="p-10 text-center text-muted-foreground">Pick a role to edit its permissions.</CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function NewRoleDialog({ permissions, onCreated }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState(new Set());
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/roles", { name, description, permission_ids: Array.from(selected) });
      toast.success("Role created");
      setOpen(false);
      setName(""); setDescription(""); setSelected(new Set());
      onCreated();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const toggle = (id) => {
    const s = new Set(selected); s.has(id) ? s.delete(id) : s.add(id); setSelected(s);
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-role-btn"><Plus size={14} className="mr-2" /> New role</Button></DialogTrigger>
      <DialogContent className="rounded-sm max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader><DialogTitle className="font-display tracking-tight">New role</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div><Label>Name</Label><Input value={name} onChange={(e) => setName(e.target.value)} required className="rounded-sm" data-testid="new-role-name" /></div>
          <div><Label>Description</Label><Textarea value={description} onChange={(e) => setDescription(e.target.value)} className="rounded-sm" /></div>
          <div>
            <Label className="mb-2 block">Permissions</Label>
            <div className="grid md:grid-cols-2 gap-2 max-h-72 overflow-y-auto border border-border p-3">
              {permissions.map((p) => (
                <label key={p.id} className="flex items-start gap-2 text-sm">
                  <Checkbox checked={selected.has(p.id)} onCheckedChange={() => toggle(p.id)} />
                  <span><span className="font-mono text-xs text-muted-foreground">{p.code}</span> {p.label}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end"><Button type="submit" className="rounded-sm" data-testid="new-role-submit">Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function NewPermissionDialog({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ code: "", label: "", module: "", description: "" });
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/permissions", form);
      toast.success("Permission created");
      setOpen(false);
      setForm({ code: "", label: "", module: "", description: "" });
      onCreated();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create permission");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="rounded-sm" data-testid="new-permission-btn">
          <Plus size={14} className="mr-2" /> New permission
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display tracking-tight">Create custom permission</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Code</Label>
            <Input
              required
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              placeholder="workflows.approve"
              className="rounded-sm font-mono"
              data-testid="new-perm-code"
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              Machine code the AI/backend checks. Use dot.notation. Must be unique.
            </p>
          </div>
          <div>
            <Label>Label</Label>
            <Input
              required
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              placeholder="Approve workflows"
              className="rounded-sm"
              data-testid="new-perm-label"
            />
          </div>
          <div>
            <Label>Module</Label>
            <Input
              required
              value={form.module}
              onChange={(e) => setForm({ ...form, module: e.target.value })}
              placeholder="workflows"
              className="rounded-sm"
              data-testid="new-perm-module"
            />
          </div>
          <div className="col-span-2">
            <Label>Description</Label>
            <Textarea
              rows={2}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="rounded-sm"
            />
          </div>
          <div className="col-span-2 flex justify-end pt-2">
            <Button type="submit" disabled={saving} className="rounded-sm" data-testid="new-perm-submit">
              {saving ? "Creating…" : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

