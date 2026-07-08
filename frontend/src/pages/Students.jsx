import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, MagnifyingGlass } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import useTerminology from "@/hooks/useTerminology";
import { useNavigate } from "react-router-dom";

export default function Students() {
  const { can } = useAuth();
  const { plural } = useTerminology();
  const nav = useNavigate();
  const [students, setStudents] = useState([]);
  const [sections, setSections] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [q, setQ] = useState("");
  const [sectionId, setSectionId] = useState("all");
  const [open, setOpen] = useState(false);

  const load = () =>
    api.get("/students", { params: { q: q || undefined, section_id: sectionId === "all" ? undefined : sectionId } })
      .then((r) => setStudents(r.data));

  useEffect(() => {
    load();
    api.get("/academic/sections").then((r) => setSections(r.data));
    api.get("/academic/departments").then((r) => setDepartments(r.data));
    // eslint-disable-next-line
  }, []);

  const sectionName = (id) => sections.find((s) => s.id === id)?.name || "—";
  const deptName = (id) => departments.find((d) => d.id === id)?.name || "—";

  return (
    <div className="space-y-6" data-testid="students-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">{plural("student")}</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Directory</h1>
        </div>
        {can("students.create") && (
          <NewStudentDialog open={open} setOpen={setOpen} sections={sections} departments={departments} onCreated={load} />
        )}
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[240px]">
          <Label className="text-xs">Search</Label>
          <div className="relative">
            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
              placeholder="Name, roll, admission, email…" className="pl-9 rounded-sm" data-testid="students-search-input" />
          </div>
        </div>
        <div className="min-w-[180px]">
          <Label className="text-xs">Section</Label>
          <Select value={sectionId} onValueChange={(v) => { setSectionId(v); }}>
            <SelectTrigger className="rounded-sm" data-testid="students-section-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sections</SelectItem>
              {sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={load} variant="outline" className="rounded-sm" data-testid="students-apply-filter-btn">Apply</Button>
      </div>

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">Admission</th>
                <th className="text-left px-4 py-3 font-semibold">Name</th>
                <th className="text-left px-4 py-3 font-semibold">Email</th>
                <th className="text-left px-4 py-3 font-semibold">Section</th>
                <th className="text-left px-4 py-3 font-semibold">Department</th>
                <th className="text-right px-4 py-3 font-semibold">Roll</th>
              </tr>
            </thead>
            <tbody>
              {students.length === 0 && (
                <tr><td colSpan={6} className="text-center py-10 text-muted-foreground">No students found.</td></tr>
              )}
              {students.map((s) => (
                <tr key={s.id} onClick={() => nav(`/app/students/${s.id}`)}
                  className="border-t border-border hover:bg-secondary/60 cursor-pointer"
                  data-testid={`student-row-${s.admission_number}`}>
                  <td className="px-4 py-3 font-mono">{s.admission_number}</td>
                  <td className="px-4 py-3">{s.first_name} {s.last_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{s.email || "—"}</td>
                  <td className="px-4 py-3">{sectionName(s.section_id)}</td>
                  <td className="px-4 py-3">{deptName(s.department_id)}</td>
                  <td className="px-4 py-3 text-right font-mono">{s.roll_number || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function NewStudentDialog({ open, setOpen, sections, departments, onCreated }) {
  const [form, setForm] = useState({ admission_number: "", first_name: "", last_name: "", email: "", roll_number: "", section_id: "", department_id: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target?.value ?? e });
  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form };
      Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });
      await api.post("/students", payload);
      toast.success("Student created");
      setOpen(false);
      setForm({ admission_number: "", first_name: "", last_name: "", email: "", roll_number: "", section_id: "", department_id: "" });
      onCreated();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="rounded-sm" data-testid="new-student-btn"><Plus size={14} className="mr-2" /> New student</Button>
      </DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">New student</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div className="col-span-2"><Label>Admission number</Label><Input required value={form.admission_number} onChange={set("admission_number")} className="rounded-sm font-mono" data-testid="new-student-admission" /></div>
          <div><Label>First name</Label><Input required value={form.first_name} onChange={set("first_name")} className="rounded-sm" data-testid="new-student-first-name" /></div>
          <div><Label>Last name</Label><Input required value={form.last_name} onChange={set("last_name")} className="rounded-sm" data-testid="new-student-last-name" /></div>
          <div className="col-span-2"><Label>Email (optional)</Label><Input type="email" value={form.email} onChange={set("email")} className="rounded-sm" /></div>
          <div><Label>Roll #</Label><Input value={form.roll_number} onChange={set("roll_number")} className="rounded-sm font-mono" /></div>
          <div>
            <Label>Section</Label>
            <Select value={form.section_id} onValueChange={(v) => setForm({ ...form, section_id: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Department</Label>
            <Select value={form.department_id} onValueChange={(v) => setForm({ ...form, department_id: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{departments.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="col-span-2 flex justify-end pt-2"><Button type="submit" className="rounded-sm" data-testid="new-student-submit">Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
