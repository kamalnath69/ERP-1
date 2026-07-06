import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Trash } from "@phosphor-icons/react";

const KIND_COLORS = {
  event: "bg-blue-100 text-blue-800",
  holiday: "bg-emerald-100 text-emerald-800",
  exam: "bg-red-100 text-red-800",
  deadline: "bg-amber-100 text-amber-800",
};

export default function Calendar() {
  const [events, setEvents] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", event_date: new Date().toISOString().slice(0, 10), kind: "event", description: "" });

  const load = () => api.get("/calendar").then((r) => setEvents(r.data));
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/calendar", form);
      toast.success("Event created"); setOpen(false);
      setForm({ title: "", event_date: new Date().toISOString().slice(0, 10), kind: "event", description: "" });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const remove = async (id) => { await api.delete(`/calendar/${id}`); load(); };

  return (
    <div className="space-y-6" data-testid="calendar-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Academic Calendar</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Events & holidays</h1>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-event-btn"><Plus size={14} className="mr-2" /> Add event</Button></DialogTrigger>
          <DialogContent className="rounded-sm">
            <DialogHeader><DialogTitle className="font-display tracking-tight">New event</DialogTitle></DialogHeader>
            <form onSubmit={create} className="space-y-3">
              <div><Label>Title</Label><Input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-sm" data-testid="event-title" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Date</Label><Input required type="date" value={form.event_date} onChange={(e) => setForm({ ...form, event_date: e.target.value })} className="rounded-sm font-mono" /></div>
                <div>
                  <Label>Kind</Label>
                  <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v })}>
                    <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>{Object.keys(KIND_COLORS).map((k) => <SelectItem key={k} value={k}>{k}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div><Label>Description</Label><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-sm" /></div>
              <div className="flex justify-end"><Button type="submit" className="rounded-sm">Create</Button></div>
            </form>
          </DialogContent>
        </Dialog>
      </header>

      <div className="grid gap-3">
        {events.length === 0 && <div className="text-sm text-muted-foreground">No events yet.</div>}
        {events.map((e) => (
          <Card key={e.id} className="rounded-sm border-border">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="border-r border-border pr-4 min-w-24">
                <div className="font-display text-2xl font-bold">{new Date(e.event_date).getDate()}</div>
                <div className="text-xs uppercase tracking-widest text-muted-foreground">
                  {new Date(e.event_date).toLocaleString("default", { month: "short", year: "numeric" })}
                </div>
              </div>
              <div className="flex-1">
                <div className="flex gap-2 items-baseline">
                  <div className="font-medium">{e.title}</div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-sm uppercase tracking-widest font-mono ${KIND_COLORS[e.kind] || "bg-muted"}`}>{e.kind}</span>
                </div>
                {e.description && <div className="text-xs text-muted-foreground mt-1">{e.description}</div>}
              </div>
              <Button size="sm" variant="outline" onClick={() => remove(e.id)} className="rounded-sm"><Trash size={12} /></Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
