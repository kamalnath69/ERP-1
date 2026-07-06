import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, CheckCircle } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";

export default function Marks() {
  const { can } = useAuth();
  const [exams, setExams] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [sections, setSections] = useState([]);
  const [selectedExam, setSelectedExam] = useState(null);
  const [marks, setMarks] = useState([]);
  const [students, setStudents] = useState([]);
  const [inputMap, setInputMap] = useState({});

  const load = () => api.get("/marks/exams").then((r) => setExams(r.data));
  useEffect(() => {
    load();
    api.get("/academic/subjects").then((r) => setSubjects(r.data));
    api.get("/academic/sections").then((r) => setSections(r.data));
  }, []);

  const openExam = async (exam) => {
    setSelectedExam(exam);
    const { data } = await api.get(`/marks/exams/${exam.id}/marks`);
    setMarks(data.marks);
    const map = {};
    data.marks.forEach((m) => (map[m.student_id] = m.obtained));
    setInputMap(map);
    if (exam.section_id) {
      const { data: studs } = await api.get("/students", { params: { section_id: exam.section_id } });
      setStudents(studs);
    } else setStudents([]);
  };

  const publish = async () => {
    await api.post(`/marks/exams/${selectedExam.id}/publish`);
    toast.success("Marks published");
    load();
  };

  const saveMarks = async () => {
    if (!selectedExam) return;
    const entries = Object.entries(inputMap).map(([student_id, obtained]) => ({ student_id, obtained: Number(obtained) || 0 }));
    await api.post("/marks/bulk", { exam_id: selectedExam.id, marks: entries });
    toast.success("Marks saved");
    openExam(selectedExam);
  };

  const subjectName = (id) => subjects.find((s) => s.id === id)?.name || "—";
  const sectionName = (id) => sections.find((s) => s.id === id)?.name || "—";

  return (
    <div className="space-y-6" data-testid="marks-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Exams & Marks</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Assessments</h1>
        </div>
        {can("marks.enter") && <NewExamDialog subjects={subjects} sections={sections} onCreated={load} />}
      </header>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="rounded-sm border-border lg:col-span-1">
          <CardContent className="p-0">
            <div className="px-4 py-3 border-b border-border overline">All exams</div>
            {exams.length === 0 && <div className="p-4 text-sm text-muted-foreground">No exams yet.</div>}
            {exams.map((e) => (
              <button
                key={e.id}
                onClick={() => openExam(e)}
                data-testid={`exam-item-${e.id}`}
                className={`w-full text-left px-4 py-3 border-b border-border hover:bg-secondary ${selectedExam?.id === e.id ? "bg-secondary" : ""}`}
              >
                <div className="flex justify-between items-baseline">
                  <div className="font-medium">{e.name}</div>
                  {e.is_published ? <CheckCircle size={14} className="text-emerald-600" /> : <span className="overline">draft</span>}
                </div>
                <div className="text-xs text-muted-foreground">{subjectName(e.subject_id)} · {sectionName(e.section_id)} · /{e.max_marks}</div>
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="lg:col-span-2 space-y-4">
          {selectedExam ? (
            <>
              <Card className="rounded-sm border-border">
                <CardContent className="p-4 flex flex-wrap items-baseline justify-between gap-3">
                  <div>
                    <div className="overline">Editing</div>
                    <div className="font-display text-xl">{selectedExam.name}</div>
                    <div className="text-xs text-muted-foreground">{subjectName(selectedExam.subject_id)} · {sectionName(selectedExam.section_id)} · max {selectedExam.max_marks}</div>
                  </div>
                  <div className="flex gap-2">
                    {can("marks.enter") && <Button onClick={saveMarks} className="rounded-sm" data-testid="save-marks-btn">Save marks</Button>}
                    {can("marks.publish") && !selectedExam.is_published && <Button onClick={publish} variant="outline" className="rounded-sm" data-testid="publish-exam-btn">Publish</Button>}
                  </div>
                </CardContent>
              </Card>
              <Card className="rounded-sm border-border">
                <CardContent className="p-0">
                  <table className="w-full text-sm">
                    <thead className="bg-secondary text-xs uppercase tracking-widest">
                      <tr>
                        <th className="text-left px-4 py-3">Student</th>
                        <th className="text-right px-4 py-3">Marks / {selectedExam.max_marks}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {students.map((s) => (
                        <tr key={s.id} className="border-t border-border">
                          <td className="px-4 py-2">{s.first_name} {s.last_name} <span className="text-xs text-muted-foreground font-mono">({s.admission_number})</span></td>
                          <td className="px-4 py-2 text-right">
                            <Input
                              type="number"
                              min={0}
                              max={selectedExam.max_marks}
                              value={inputMap[s.id] ?? ""}
                              onChange={(e) => setInputMap({ ...inputMap, [s.id]: e.target.value })}
                              className="w-24 ml-auto rounded-sm font-mono text-right"
                              data-testid={`mark-input-${s.admission_number}`}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </>
          ) : (
            <Card className="rounded-sm border-border">
              <CardContent className="p-10 text-center text-muted-foreground">Pick an exam on the left to enter marks.</CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function NewExamDialog({ subjects, sections, onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", exam_type: "mid", subject_id: "", section_id: "", max_marks: 100, pass_marks: 40 });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target?.value ?? e });
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/marks/exams", { ...form, max_marks: Number(form.max_marks), pass_marks: Number(form.pass_marks) });
      toast.success("Exam created");
      setOpen(false);
      onCreated();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-exam-btn"><Plus size={14} className="mr-2" /> New exam</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">New exam</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div className="col-span-2"><Label>Name</Label><Input required value={form.name} onChange={set("name")} className="rounded-sm" data-testid="new-exam-name" /></div>
          <div>
            <Label>Type</Label>
            <Select value={form.exam_type} onValueChange={(v) => setForm({ ...form, exam_type: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["internal", "mid", "final", "assignment", "quiz"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Subject</Label>
            <Select value={form.subject_id} onValueChange={(v) => setForm({ ...form, subject_id: v })}>
              <SelectTrigger className="rounded-sm" data-testid="new-exam-subject"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{subjects.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Section</Label>
            <Select value={form.section_id} onValueChange={(v) => setForm({ ...form, section_id: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label>Max marks</Label><Input type="number" min={1} value={form.max_marks} onChange={set("max_marks")} className="rounded-sm font-mono" /></div>
          <div><Label>Pass marks</Label><Input type="number" min={0} value={form.pass_marks} onChange={set("pass_marks")} className="rounded-sm font-mono" /></div>
          <div className="col-span-2 flex justify-end pt-2"><Button type="submit" className="rounded-sm" data-testid="new-exam-submit">Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
