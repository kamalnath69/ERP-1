import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const STAGES = [
  { id: "new", label: "New", color: "bg-blue-100 text-blue-800 border-blue-400" },
  { id: "reviewing", label: "Reviewing", color: "bg-purple-100 text-purple-800 border-purple-400" },
  { id: "interview", label: "Interview", color: "bg-amber-100 text-amber-800 border-amber-400" },
  { id: "accepted", label: "Accepted", color: "bg-emerald-100 text-emerald-800 border-emerald-400" },
  { id: "enrolled", label: "Enrolled", color: "bg-gray-100 text-gray-800 border-gray-400" },
  { id: "rejected", label: "Rejected", color: "bg-red-100 text-red-800 border-red-400" },
];

export default function Admissions() {
  const [apps, setApps] = useState([]);
  const load = () => api.get("/admissions").then((r) => setApps(r.data));
  useEffect(() => { load(); }, []);

  const move = async (id, stage) => {
    await api.patch(`/admissions/${id}`, { stage });
    load();
  };
  const enroll = async (id) => {
    try { const { data } = await api.post(`/admissions/${id}/enroll`); toast.success(`Enrolled → student ${data.student_id.slice(0, 8)}`); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-6" data-testid="admissions-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Admissions Funnel</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Applications Kanban</h1>
          <p className="text-sm text-muted-foreground mt-2">Public form at <span className="font-mono">/admissions/&lt;org-slug&gt;</span>. Drag applications through stages, enroll to convert into a Student in one click.</p>
        </div>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        {STAGES.map((stage) => {
          const items = apps.filter((a) => a.stage === stage.id);
          return (
            <div key={stage.id} className="min-h-[300px]" data-testid={`stage-${stage.id}`}>
              <div className={`p-2 border ${stage.color} text-xs uppercase tracking-widest font-mono font-semibold flex justify-between`}>
                <span>{stage.label}</span><span>{items.length}</span>
              </div>
              <div className="mt-2 space-y-2">
                {items.map((a) => (
                  <Card key={a.id} className="rounded-sm border-border">
                    <CardContent className="p-3">
                      <div className="font-medium text-sm">{a.first_name} {a.last_name}</div>
                      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground truncate mt-1">{a.email}</div>
                      {a.interest_department && <div className="text-xs mt-1">{a.interest_department}</div>}
                      <div className="mt-3 flex flex-wrap gap-1">
                        {STAGES.filter((s) => s.id !== stage.id).slice(0, 3).map((s) => (
                          <button key={s.id} onClick={() => move(a.id, s.id)} data-testid={`move-${a.id}-${s.id}`}
                            className="text-[10px] font-mono uppercase tracking-widest border border-border px-2 py-0.5 hover:bg-secondary">→ {s.label}</button>
                        ))}
                        {stage.id === "accepted" && !a.student_id && (
                          <Button size="sm" onClick={() => enroll(a.id)} className="rounded-sm text-[10px] h-6 uppercase tracking-widest" data-testid={`enroll-${a.id}`}>Enroll</Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {items.length === 0 && <div className="text-xs text-muted-foreground text-center py-4">—</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
