import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import useTerminology from "@/hooks/useTerminology";

export default function Faculty() {
  const { can } = useAuth();
  const { plural, t } = useTerminology();
  const [faculty, setFaculty] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [open, setOpen] = useState(false);

  const load = () => api.get("/faculty").then((r) => setFaculty(r.data));
  useEffect(() => {
    load();
    api.get("/academic/departments").then((r) => setDepartments(r.data));
  }, []);

  const deptName = (id) => departments.find((d) => d.id === id)?.name || "—";

  return (
    <div className="space-y-6" data-testid="faculty-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">{plural("faculty")}</div>
          <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Teaching staff</h1>
        </div>
        {can("faculty.create") && <NewFacultyDialog open={open} setOpen={setOpen} departments={departments} onCreated={load} />}
      </header>

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3">Employee #</th>
                <th className="text-left px-4 py-3">Designation</th>
                <th className="text-left px-4 py-3">Department</th>
                <th className="text-left px-4 py-3">Qualification</th>
                <th className="text-right px-4 py-3">Experience</th>
              </tr>
            </thead>
            <tbody>
              {faculty.length === 0 && (
                <tr><td colSpan={5} className="text-center py-10 text-muted-foreground">No faculty yet.</td></tr>
              )}
              {faculty.map((f) => (
                <tr key={f.id} className="border-t border-border hover:bg-secondary/60" data-testid={`faculty-row-${f.employee_number}`}>
                  <td className="px-4 py-3 font-mono">{f.employee_number}</td>
                  <td className="px-4 py-3">{f.designation || "—"}</td>
                  <td className="px-4 py-3">{deptName(f.department_id)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{f.qualification || "—"}</td>
                  <td className="px-4 py-3 text-right font-mono">{f.experience_years ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function NewFacultyDialog({ open, setOpen, departments, onCreated }) {
  const [form, setForm] = useState({ employee_number: "", email: "", first_name: "", last_name: "", password: "Faculty@123", designation: "", department_id: "", qualification: "", experience_years: 0 });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target?.value ?? e });
  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form, experience_years: Number(form.experience_years) || 0 };
      Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });
      await api.post("/faculty", payload);
      toast.success("Faculty added");
      setOpen(false);
      onCreated();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-faculty-btn"><Plus size={14} className="mr-2" /> Add faculty</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">Add faculty</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div><Label>Employee #</Label><Input required value={form.employee_number} onChange={set("employee_number")} className="rounded-sm font-mono" data-testid="fac-empno" /></div>
          <div><Label>Designation</Label><Input value={form.designation} onChange={set("designation")} className="rounded-sm" /></div>
          <div><Label>First name</Label><Input required value={form.first_name} onChange={set("first_name")} className="rounded-sm" data-testid="fac-first-name" /></div>
          <div><Label>Last name</Label><Input required value={form.last_name} onChange={set("last_name")} className="rounded-sm" data-testid="fac-last-name" /></div>
          <div className="col-span-2"><Label>Email</Label><Input required type="email" value={form.email} onChange={set("email")} className="rounded-sm" data-testid="fac-email" /></div>
          <div className="col-span-2"><Label>Initial password (they can change later)</Label><Input required type="text" value={form.password} onChange={set("password")} className="rounded-sm font-mono" /></div>
          <div><Label>Qualification</Label><Input value={form.qualification} onChange={set("qualification")} className="rounded-sm" /></div>
          <div><Label>Years experience</Label><Input type="number" min={0} value={form.experience_years} onChange={set("experience_years")} className="rounded-sm font-mono" /></div>
          <div className="col-span-2 flex justify-end pt-2"><Button type="submit" className="rounded-sm" data-testid="fac-submit">Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
