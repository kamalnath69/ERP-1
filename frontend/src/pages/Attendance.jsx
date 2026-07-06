import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const STATUSES = ["present", "absent", "late", "excused"];

export default function Attendance() {
  const { can } = useAuth();
  const [sections, setSections] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [students, setStudents] = useState([]);
  const [sectionId, setSectionId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [sessionDate, setSessionDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [statusMap, setStatusMap] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/academic/sections").then((r) => setSections(r.data));
    api.get("/academic/subjects").then((r) => setSubjects(r.data));
  }, []);

  useEffect(() => {
    if (!sectionId) { setStudents([]); return; }
    api.get("/students", { params: { section_id: sectionId } }).then((r) => {
      setStudents(r.data);
      const map = {};
      r.data.forEach((s) => (map[s.id] = "present"));
      setStatusMap(map);
    });
  }, [sectionId]);

  const summary = useMemo(() => {
    const counts = { present: 0, absent: 0, late: 0, excused: 0 };
    Object.values(statusMap).forEach((s) => { counts[s] = (counts[s] || 0) + 1; });
    return counts;
  }, [statusMap]);

  const save = async () => {
    if (!sectionId) return toast.error("Pick a section");
    setSaving(true);
    try {
      await api.post("/attendance/sessions", {
        section_id: sectionId,
        subject_id: subjectId || null,
        session_date: sessionDate,
        records: Object.entries(statusMap).map(([student_id, status]) => ({ student_id, status })),
      });
      toast.success("Attendance saved");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="attendance-page">
      <header>
        <div className="overline text-muted-foreground">Attendance</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Mark attendance</h1>
      </header>

      <div className="grid md:grid-cols-4 gap-3">
        <div>
          <Label className="text-xs">Section</Label>
          <Select value={sectionId} onValueChange={setSectionId}>
            <SelectTrigger className="rounded-sm" data-testid="att-section-select"><SelectValue placeholder="Pick a section" /></SelectTrigger>
            <SelectContent>{sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Subject (optional)</Label>
          <Select value={subjectId} onValueChange={setSubjectId}>
            <SelectTrigger className="rounded-sm" data-testid="att-subject-select"><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>{subjects.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Date</Label>
          <Input type="date" value={sessionDate} onChange={(e) => setSessionDate(e.target.value)} className="rounded-sm font-mono" data-testid="att-date-input" />
        </div>
        <div className="flex items-end">
          {can("attendance.mark") && <Button onClick={save} disabled={saving || !sectionId} className="rounded-sm w-full" data-testid="att-save-btn">{saving ? "Saving…" : "Save session"}</Button>}
        </div>
      </div>

      {students.length > 0 && (
        <>
          <div className="flex gap-4 text-xs font-mono uppercase tracking-widest">
            <span>Total: {students.length}</span>
            <span className="text-emerald-600">Present: {summary.present}</span>
            <span className="text-destructive">Absent: {summary.absent}</span>
            <span className="text-amber-600">Late: {summary.late}</span>
            <span className="text-muted-foreground">Excused: {summary.excused}</span>
          </div>
          <Card className="rounded-sm border-border">
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-secondary text-xs uppercase tracking-widest">
                  <tr>
                    <th className="text-left px-4 py-3">Admission</th>
                    <th className="text-left px-4 py-3">Name</th>
                    <th className="text-left px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.id} className="border-t border-border" data-testid={`att-row-${s.admission_number}`}>
                      <td className="px-4 py-2 font-mono">{s.admission_number}</td>
                      <td className="px-4 py-2">{s.first_name} {s.last_name}</td>
                      <td className="px-4 py-2">
                        <div className="flex gap-1">
                          {STATUSES.map((st) => (
                            <button
                              key={st}
                              onClick={() => setStatusMap({ ...statusMap, [s.id]: st })}
                              data-testid={`att-btn-${s.admission_number}-${st}`}
                              className={`px-2 py-1 text-xs uppercase tracking-widest rounded-sm border ${
                                statusMap[s.id] === st
                                  ? st === "present" ? "bg-emerald-600 text-white border-emerald-600"
                                    : st === "absent" ? "bg-destructive text-white border-destructive"
                                    : st === "late" ? "bg-amber-500 text-white border-amber-500"
                                    : "bg-muted-foreground text-white border-muted-foreground"
                                  : "border-border hover:bg-secondary"
                              }`}
                            >
                              {st}
                            </button>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
