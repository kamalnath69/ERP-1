import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, ShieldSlash, ShieldCheck } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { Link } from "react-router-dom";

export default function SuperAdmin() {
  const { user } = useAuth();
  const [orgs, setOrgs] = useState([]);
  const [health, setHealth] = useState(null);

  const load = () => {
    api.get("/super-admin/organizations").then((r) => setOrgs(r.data));
    api.get("/super-admin/health").then((r) => setHealth(r.data));
  };
  useEffect(() => { load(); }, []);

  if (!user?.is_super_admin) return <div className="text-sm text-destructive">Super admin only</div>;

  const suspend = async (id) => { await api.post(`/super-admin/organizations/${id}/suspend`); toast.success("Suspended"); load(); };
  const activate = async (id) => { await api.post(`/super-admin/organizations/${id}/activate`); toast.success("Activated"); load(); };

  return (
    <div className="space-y-6" data-testid="super-admin-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Platform Console</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">All organizations</h1>
        </div>
        <div className="flex gap-2">
          <NewOrgDialog onCreated={load} />
          <Link to="/app"><Button variant="outline" className="rounded-sm">Tenant view</Button></Link>
        </div>
      </header>

      {health && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[["total_organizations","Orgs"],["active_organizations","Active"],["total_users","Users"],["total_students","Students"]].map(([k, l]) => (
            <Card key={k} className="rounded-sm border-border"><CardContent className="p-4"><div className="overline">{l}</div><div className="font-display text-3xl mt-1" data-testid={`platform-kpi-${k}`}>{health[k]}</div></CardContent></Card>
          ))}
        </div>
      )}

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3">Slug</th>
                <th className="text-left px-4 py-3">Name</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Plan</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((o) => (
                <tr key={o.id} className="border-t border-border" data-testid={`org-row-${o.slug}`}>
                  <td className="px-4 py-3 font-mono">{o.slug}</td>
                  <td className="px-4 py-3">{o.name}</td>
                  <td className="px-4 py-3 uppercase text-xs font-mono">{o.org_type}</td>
                  <td className="px-4 py-3 uppercase text-xs font-mono">{o.plan}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-1 rounded-sm font-mono uppercase ${o.status === "active" ? "bg-emerald-100 text-emerald-800" : o.status === "suspended" ? "bg-red-100 text-red-800" : "bg-muted"}`}>{o.status}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {o.status === "active" ? (
                      <Button size="sm" variant="outline" onClick={() => suspend(o.id)} className="rounded-sm" data-testid={`suspend-${o.slug}`}><ShieldSlash size={12} className="mr-1" /> Suspend</Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => activate(o.id)} className="rounded-sm" data-testid={`activate-${o.slug}`}><ShieldCheck size={12} className="mr-1" /> Activate</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function NewOrgDialog({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", slug: "", org_type: "college", contact_email: "" });
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/super-admin/organizations", form);
      toast.success("Organization created");
      setOpen(false);
      setForm({ name: "", slug: "", org_type: "college", contact_email: "" });
      onCreated();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-org-btn"><Plus size={14} className="mr-2" /> New organization</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">New organization</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div><Label>Name</Label><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" /></div>
          <div><Label>Slug</Label><Input required value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g,"-") })} className="rounded-sm font-mono" /></div>
          <div>
            <Label>Type</Label>
            <Select value={form.org_type} onValueChange={(v) => setForm({ ...form, org_type: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["school","college","university","training_institute","coaching_centre"].map((t) => <SelectItem key={t} value={t}>{t.replace("_"," ")}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label>Contact email</Label><Input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className="rounded-sm" /></div>
          <div className="flex justify-end"><Button type="submit" className="rounded-sm">Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
