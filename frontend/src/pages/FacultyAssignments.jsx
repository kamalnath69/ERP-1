import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Trash } from "@phosphor-icons/react";

export default function FacultyAssignments() {
  const [assignments, setAssignments] = useState([]);
  const [faculty, setFaculty] = useState([]);
  const [users, setUsers] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [sections, setSections] = useState([]);
  const [form, setForm] = useState({ faculty_user_id: "", subject_id: "", section_id: "", role: "teacher" });

  const load = () => api.get("/assignments").then((r) => setAssignments(r.data));
  useEffect(() => {
    load();
    api.get("/faculty").then((r) => setFaculty(r.data));
    api.get("/users").then((r) => setUsers(r.data)).catch(() => {});
    api.get("/academic/subjects").then((r) => setSubjects(r.data));
    api.get("/academic/sections").then((r) => setSections(r.data));
  }, []);

  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/assignments", form); toast.success("Assigned"); setForm({ faculty_user_id: "", subject_id: "", section_id: "", role: "teacher" }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const remove = async (id) => { await api.delete(`/assignments/${id}`); toast.success("Removed"); load(); };

  const userLookup = (uid) => users.find((u) => u.id === uid);
  const subjName = (id) => subjects.find((s) => s.id === id)?.name || "—";
  const secName = (id) => sections.find((s) => s.id === id)?.name || "—";

  return (
    <div className="space-y-6" data-testid="assignments-page">
      <header>
        <div className="overline text-muted-foreground">Faculty Assignments</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Who teaches what</h1>
      </header>

      <Card className="rounded-sm border-border">
        <CardContent className="p-4">
          <form onSubmit={create} className="grid md:grid-cols-5 gap-3 items-end">
            <div>
              <Label className="text-xs">Faculty</Label>
              <Select value={form.faculty_user_id} onValueChange={(v) => setForm({ ...form, faculty_user_id: v })}>
                <SelectTrigger className="rounded-sm" data-testid="assign-faculty-select"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{faculty.map((f) => {
                  const u = userLookup(f.user_id);
                  return <SelectItem key={f.id} value={f.user_id}>{u ? `${u.first_name} ${u.last_name}` : f.employee_number}</SelectItem>;
                })}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Subject</Label>
              <Select value={form.subject_id} onValueChange={(v) => setForm({ ...form, subject_id: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{subjects.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Section</Label>
              <Select value={form.section_id} onValueChange={(v) => setForm({ ...form, section_id: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
                <SelectContent>{["teacher", "advisor", "coordinator", "hod"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <Button type="submit" className="rounded-sm" data-testid="assign-submit-btn">Assign</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3">Faculty</th>
                <th className="text-left px-4 py-3">Subject</th>
                <th className="text-left px-4 py-3">Section</th>
                <th className="text-left px-4 py-3">Role</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.length === 0 && <tr><td colSpan={5} className="text-center py-10 text-muted-foreground">No assignments.</td></tr>}
              {assignments.map((a) => {
                const u = userLookup(a.faculty_user_id);
                return (
                  <tr key={a.id} className="border-t border-border">
                    <td className="px-4 py-3">{u ? `${u.first_name} ${u.last_name}` : a.faculty_user_id.slice(0, 8)}</td>
                    <td className="px-4 py-3">{subjName(a.subject_id)}</td>
                    <td className="px-4 py-3">{secName(a.section_id)}</td>
                    <td className="px-4 py-3 uppercase font-mono text-xs">{a.role}</td>
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="outline" onClick={() => remove(a.id)} className="rounded-sm"><Trash size={12} /></Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
