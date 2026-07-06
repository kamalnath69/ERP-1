import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Buildings } from "@phosphor-icons/react";

export default function Placements() {
  const [drives, setDrives] = useState([]);
  const [summary, setSummary] = useState(null);
  const load = () => { api.get("/placements/drives").then((r) => setDrives(r.data)); api.get("/placements/summary").then((r) => setSummary(r.data)).catch(() => {}); };
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6" data-testid="placements-page">
      <header className="flex items-baseline justify-between">
        <div><div className="overline text-muted-foreground">Placements</div><h1 className="text-3xl font-display font-bold tracking-tight mt-1">Drives & offers</h1></div>
        <NewDriveDialog onCreated={load} />
      </header>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="rounded-sm border-border"><CardContent className="p-4"><div className="overline">Drives</div><div className="font-display text-3xl mt-1">{summary.drives}</div></CardContent></Card>
          <Card className="rounded-sm border-border"><CardContent className="p-4"><div className="overline">Offers</div><div className="font-display text-3xl mt-1">{summary.offers}</div></CardContent></Card>
          <Card className="rounded-sm border-border"><CardContent className="p-4"><div className="overline">Avg package</div><div className="font-display text-3xl mt-1">{summary.avg_package_lpa} <span className="text-sm text-muted-foreground">LPA</span></div></CardContent></Card>
          <Card className="rounded-sm border-border"><CardContent className="p-4"><div className="overline">Top package</div><div className="font-display text-3xl mt-1">{summary.top_package_lpa} <span className="text-sm text-muted-foreground">LPA</span></div></CardContent></Card>
        </div>
      )}

      <div className="grid gap-3">
        {drives.length === 0 && <div className="text-sm text-muted-foreground">No drives yet.</div>}
        {drives.map((d) => (
          <Card key={d.id} className="rounded-sm border-border">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="h-12 w-12 border border-border flex items-center justify-center"><Buildings size={20} /></div>
              <div className="flex-1">
                <div className="font-medium">{d.company}</div>
                <div className="text-xs text-muted-foreground">{d.role} · {d.package_lpa} LPA · {d.drive_date || "TBD"}</div>
              </div>
              <span className={`text-xs px-2 py-1 rounded-sm font-mono uppercase ${d.status === "scheduled" ? "bg-blue-100 text-blue-800" : d.status === "ongoing" ? "bg-amber-100 text-amber-800" : "bg-muted"}`}>{d.status}</span>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function NewDriveDialog({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ company: "", role: "", package_lpa: 0, drive_date: "", description: "" });
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/placements/drives", { ...form, package_lpa: Number(form.package_lpa) });
      toast.success("Drive scheduled"); setOpen(false); onCreated();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-drive-btn"><Plus size={14} className="mr-2" /> New drive</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">New placement drive</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div className="col-span-2"><Label>Company</Label><Input required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} className="rounded-sm" data-testid="drive-company" /></div>
          <div><Label>Role</Label><Input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="rounded-sm" /></div>
          <div><Label>Package (LPA)</Label><Input type="number" min={0} step={0.1} value={form.package_lpa} onChange={(e) => setForm({ ...form, package_lpa: e.target.value })} className="rounded-sm font-mono" /></div>
          <div className="col-span-2"><Label>Date</Label><Input type="date" value={form.drive_date} onChange={(e) => setForm({ ...form, drive_date: e.target.value })} className="rounded-sm font-mono" /></div>
          <div className="col-span-2"><Label>Description</Label><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-sm" /></div>
          <div className="col-span-2 flex justify-end"><Button type="submit" className="rounded-sm">Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
