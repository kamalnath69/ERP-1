import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, CurrencyInr } from "@phosphor-icons/react";

export default function Fees() {
  const [summary, setSummary] = useState(null);
  useEffect(() => { api.get("/fees/summary").then((r) => setSummary(r.data)).catch(() => {}); }, []);

  return (
    <div className="space-y-6" data-testid="fees-page">
      <header>
        <div className="overline text-muted-foreground">Fees</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Structures & collections</h1>
      </header>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {summary.by_status.map((s) => (
            <Card key={s.status} className="rounded-sm border-border">
              <CardContent className="p-4">
                <div className="overline">{s.status}</div>
                <div className="mt-2 font-display text-2xl font-bold">₹{(s.collected || 0).toLocaleString()}</div>
                <div className="text-xs text-muted-foreground mt-1">of ₹{(s.total || 0).toLocaleString()} · {s.count} invoices</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Tabs defaultValue="structures">
        <TabsList className="rounded-sm bg-secondary">
          <TabsTrigger value="structures" className="rounded-sm">Structures</TabsTrigger>
          <TabsTrigger value="invoices" className="rounded-sm">Invoices</TabsTrigger>
        </TabsList>
        <TabsContent value="structures"><Structures onChange={() => api.get("/fees/summary").then((r) => setSummary(r.data))} /></TabsContent>
        <TabsContent value="invoices"><Invoices /></TabsContent>
      </Tabs>
    </div>
  );
}

function Structures({ onChange }) {
  const [items, setItems] = useState([]);
  const [sections, setSections] = useState([]);
  const [form, setForm] = useState({ name: "", amount: "", due_date: "" });
  const [assignFor, setAssignFor] = useState(null);
  const [assignSection, setAssignSection] = useState("");
  const load = () => api.get("/fees/structures").then((r) => setItems(r.data));
  useEffect(() => { load(); api.get("/academic/sections").then((r) => setSections(r.data)); }, []);
  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/fees/structures", { ...form, amount: Number(form.amount) }); toast.success("Created"); setForm({ name: "", amount: "", due_date: "" }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const assign = async () => {
    try {
      const { data } = await api.post("/fees/bulk-assign", { structure_id: assignFor.id, section_id: assignSection || null });
      toast.success(`Created ${data.invoices_created} invoices`); setAssignFor(null); setAssignSection(""); onChange?.();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="space-y-4 mt-4">
      <Card className="rounded-sm border-border">
        <CardContent className="p-4">
          <form onSubmit={create} className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px]"><Label className="text-xs">Structure name</Label><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" placeholder="e.g. Term 1 · CSE Y2" data-testid="fee-name" /></div>
            <div><Label className="text-xs">Amount (₹)</Label><Input type="number" min={1} required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="rounded-sm font-mono w-32" data-testid="fee-amount" /></div>
            <div><Label className="text-xs">Due date</Label><Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} className="rounded-sm font-mono" /></div>
            <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr><th className="text-left px-4 py-3">Name</th><th className="text-right px-4 py-3">Amount</th><th className="text-left px-4 py-3">Due</th><th className="text-right px-4 py-3">Actions</th></tr>
            </thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={4} className="text-center py-10 text-muted-foreground">No structures.</td></tr>}
              {items.map((s) => (
                <tr key={s.id} className="border-t border-border">
                  <td className="px-4 py-3">{s.name}</td>
                  <td className="px-4 py-3 text-right font-mono">₹{s.amount.toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono text-xs">{s.due_date || "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="outline" onClick={() => setAssignFor(s)} className="rounded-sm" data-testid={`assign-${s.id}`}>Bulk assign</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Dialog open={!!assignFor} onOpenChange={(o) => !o && setAssignFor(null)}>
        <DialogContent className="rounded-sm">
          <DialogHeader><DialogTitle className="font-display tracking-tight">Bulk-assign {assignFor?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Creates an invoice for every student in the chosen section (or all students if none selected).</p>
            <div>
              <Label>Section (optional)</Label>
              <Select value={assignSection} onValueChange={setAssignSection}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="All students" /></SelectTrigger>
                <SelectContent>{sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex justify-end"><Button onClick={assign} className="rounded-sm">Create invoices</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Invoices() {
  const [items, setItems] = useState([]);
  const load = () => api.get("/fees/invoices").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);
  const pay = async (id) => { await api.post(`/fees/invoices/${id}/mark-paid`); toast.success("Marked paid"); load(); };
  return (
    <Card className="rounded-sm border-border mt-4">
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="bg-secondary text-xs uppercase tracking-widest">
            <tr><th className="text-left px-4 py-3">Invoice</th><th className="text-left px-4 py-3">Student</th><th className="text-right px-4 py-3">Amount</th><th className="text-right px-4 py-3">Paid</th><th className="text-left px-4 py-3">Status</th><th></th></tr>
          </thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={6} className="text-center py-10 text-muted-foreground">No invoices.</td></tr>}
            {items.map((i) => (
              <tr key={i.id} className="border-t border-border">
                <td className="px-4 py-3 font-mono text-xs">{i.id.slice(0, 8)}</td>
                <td className="px-4 py-3 font-mono text-xs">{i.student_id.slice(0, 8)}</td>
                <td className="px-4 py-3 text-right font-mono">₹{i.amount.toLocaleString()}</td>
                <td className="px-4 py-3 text-right font-mono">₹{(i.amount_paid || 0).toLocaleString()}</td>
                <td className="px-4 py-3"><span className={`text-xs px-2 py-1 rounded-sm font-mono uppercase ${i.status === "paid" ? "bg-emerald-100 text-emerald-800" : i.status === "pending" ? "bg-amber-100 text-amber-800" : "bg-muted"}`}>{i.status}</span></td>
                <td className="px-4 py-3">
                  {i.status !== "paid" && <Button size="sm" variant="outline" onClick={() => pay(i.id)} className="rounded-sm" data-testid={`pay-${i.id}`}><CurrencyInr size={12} className="mr-1" /> Mark paid</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
