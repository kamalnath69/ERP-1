import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, LinkSimple } from "@phosphor-icons/react";

export default function Parents() {
  const [parents, setParents] = useState([]);
  const [students, setStudents] = useState([]);
  const load = () => api.get("/parents").then((r) => setParents(r.data));
  useEffect(() => { load(); api.get("/students").then((r) => setStudents(r.data)); }, []);

  return (
    <div className="space-y-6" data-testid="parents-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Parents & Guardians</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Directory</h1>
        </div>
        <div className="flex gap-2">
          <NewParentDialog onCreated={load} />
          <LinkDialog parents={parents} students={students} />
        </div>
      </header>

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3">Name</th>
                <th className="text-left px-4 py-3">Email</th>
                <th className="text-left px-4 py-3">Phone</th>
                <th className="text-left px-4 py-3">Occupation</th>
              </tr>
            </thead>
            <tbody>
              {parents.length === 0 && <tr><td colSpan={4} className="text-center py-10 text-muted-foreground">No parents yet.</td></tr>}
              {parents.map((p) => (
                <tr key={p.id} className="border-t border-border" data-testid={`parent-row-${p.id}`}>
                  <td className="px-4 py-3">{p.first_name} {p.last_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{p.email || "—"}</td>
                  <td className="px-4 py-3 font-mono">{p.phone || "—"}</td>
                  <td className="px-4 py-3">{p.occupation || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function NewParentDialog({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", phone: "", occupation: "" });
  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form };
      Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });
      await api.post("/parents", payload);
      toast.success("Parent added"); setOpen(false); onCreated();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-parent-btn"><Plus size={14} className="mr-2" /> Add parent</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">Add parent</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div><Label>First name</Label><Input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="rounded-sm" data-testid="parent-first-name" /></div>
          <div><Label>Last name</Label><Input required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="rounded-sm" /></div>
          <div className="col-span-2"><Label>Email</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="rounded-sm" /></div>
          <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="rounded-sm font-mono" /></div>
          <div><Label>Occupation</Label><Input value={form.occupation} onChange={(e) => setForm({ ...form, occupation: e.target.value })} className="rounded-sm" /></div>
          <div className="col-span-2 flex justify-end"><Button type="submit" className="rounded-sm">Save</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function LinkDialog({ parents, students }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ parent_id: "", student_id: "", relationship: "father" });
  const submit = async () => {
    try { await api.post("/parents/link", form); toast.success("Linked"); setOpen(false); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" className="rounded-sm" data-testid="link-parent-btn"><LinkSimple size={14} className="mr-2" /> Link to student</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">Link parent to student</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Parent</Label>
            <Select value={form.parent_id} onValueChange={(v) => setForm({ ...form, parent_id: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{parents.map((p) => <SelectItem key={p.id} value={p.id}>{p.first_name} {p.last_name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Student</Label>
            <Select value={form.student_id} onValueChange={(v) => setForm({ ...form, student_id: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{students.map((s) => <SelectItem key={s.id} value={s.id}>{s.first_name} {s.last_name} · {s.admission_number}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Relationship</Label>
            <Select value={form.relationship} onValueChange={(v) => setForm({ ...form, relationship: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
              <SelectContent>{["father", "mother", "guardian"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="flex justify-end"><Button onClick={submit} className="rounded-sm" data-testid="link-parent-submit">Link</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
