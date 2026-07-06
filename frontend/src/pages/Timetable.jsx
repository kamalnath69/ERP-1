import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, X } from "@phosphor-icons/react";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const PERIODS = [1, 2, 3, 4, 5, 6, 7, 8];

export default function Timetable() {
  const [sections, setSections] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [slots, setSlots] = useState([]);
  const [sectionId, setSectionId] = useState("");
  const [dialog, setDialog] = useState(null); // { day, period }
  const [slotForm, setSlotForm] = useState({ subject_id: "", room: "", label: "" });

  useEffect(() => {
    api.get("/academic/sections").then((r) => setSections(r.data));
    api.get("/academic/subjects").then((r) => setSubjects(r.data));
  }, []);
  useEffect(() => {
    if (sectionId) api.get("/timetable", { params: { section_id: sectionId } }).then((r) => setSlots(r.data));
    else setSlots([]);
  }, [sectionId]);

  const grid = useMemo(() => {
    const g = {};
    slots.forEach((s) => { g[`${s.day_of_week}-${s.period}`] = s; });
    return g;
  }, [slots]);

  const save = async () => {
    try {
      await api.post("/timetable", { section_id: sectionId, day_of_week: dialog.day, period: dialog.period, ...slotForm });
      const { data } = await api.get("/timetable", { params: { section_id: sectionId } });
      setSlots(data); setDialog(null); setSlotForm({ subject_id: "", room: "", label: "" });
      toast.success("Slot saved");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const clear = async (id) => { await api.delete(`/timetable/${id}`); setSlots(slots.filter((s) => s.id !== id)); toast.success("Cleared"); };
  const subjName = (id) => subjects.find((s) => s.id === id)?.name || "—";

  return (
    <div className="space-y-6" data-testid="timetable-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Timetable</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Weekly schedule</h1>
        </div>
        <div className="w-64">
          <Select value={sectionId} onValueChange={setSectionId}>
            <SelectTrigger className="rounded-sm" data-testid="tt-section-select"><SelectValue placeholder="Pick a section" /></SelectTrigger>
            <SelectContent>{sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </header>

      {sectionId ? (
        <Card className="rounded-sm border-border">
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead className="bg-secondary text-xs uppercase tracking-widest">
                <tr>
                  <th className="p-3 border-b border-border w-20">Period</th>
                  {DAYS.map((d) => <th key={d} className="p-3 border-b border-border">{d}</th>)}
                </tr>
              </thead>
              <tbody>
                {PERIODS.map((p) => (
                  <tr key={p}>
                    <td className="p-3 border-r border-b border-border font-mono text-xs bg-secondary/40">P{p}</td>
                    {DAYS.map((_, dayIdx) => {
                      const s = grid[`${dayIdx}-${p}`];
                      return (
                        <td key={dayIdx} className="p-2 border-b border-r border-border h-20 align-top">
                          {s ? (
                            <div className="border border-accent bg-accent/5 p-2 relative group" data-testid={`tt-slot-${dayIdx}-${p}`}>
                              <div className="font-medium text-sm truncate">{subjName(s.subject_id)}</div>
                              <div className="text-xs text-muted-foreground truncate">{s.room || s.label || ""}</div>
                              <button onClick={() => clear(s.id)} className="absolute top-1 right-1 opacity-0 group-hover:opacity-100"><X size={12} /></button>
                            </div>
                          ) : (
                            <button onClick={() => { setDialog({ day: dayIdx, period: p }); setSlotForm({ subject_id: "", room: "", label: "" }); }}
                              className="w-full h-full text-muted-foreground hover:bg-secondary text-xs" data-testid={`tt-empty-${dayIdx}-${p}`}>
                              +
                            </button>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : (
        <div className="text-sm text-muted-foreground">Pick a section to build its timetable.</div>
      )}

      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="rounded-sm">
          <DialogHeader><DialogTitle className="font-display tracking-tight">
            {dialog && `Slot · ${DAYS[dialog.day]} · P${dialog.period}`}
          </DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Subject</Label>
              <Select value={slotForm.subject_id} onValueChange={(v) => setSlotForm({ ...slotForm, subject_id: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{subjects.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Room</Label><Input value={slotForm.room} onChange={(e) => setSlotForm({ ...slotForm, room: e.target.value })} className="rounded-sm" /></div>
            <div><Label>Label (optional)</Label><Input value={slotForm.label} onChange={(e) => setSlotForm({ ...slotForm, label: e.target.value })} className="rounded-sm" /></div>
            <div className="flex justify-end"><Button onClick={save} className="rounded-sm" data-testid="tt-save-slot">Save</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
