import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Plus } from "@phosphor-icons/react";

export default function Academic() {
  return (
    <div className="space-y-6" data-testid="academic-page">
      <header>
        <div className="overline text-muted-foreground">Academic Structure</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Departments · Units · Levels · Sections · Subjects</h1>
        <p className="text-sm text-muted-foreground mt-2">Generic hierarchy — same schema for K-12 & higher-ed.</p>
      </header>
      <Tabs defaultValue="departments">
        <TabsList className="rounded-sm bg-secondary">
          <TabsTrigger value="departments" className="rounded-sm">Departments</TabsTrigger>
          <TabsTrigger value="units" className="rounded-sm">Units</TabsTrigger>
          <TabsTrigger value="levels" className="rounded-sm">Levels</TabsTrigger>
          <TabsTrigger value="sections" className="rounded-sm">Sections</TabsTrigger>
          <TabsTrigger value="subjects" className="rounded-sm">Subjects</TabsTrigger>
        </TabsList>
        <TabsContent value="departments"><Departments /></TabsContent>
        <TabsContent value="units"><Units /></TabsContent>
        <TabsContent value="levels"><Levels /></TabsContent>
        <TabsContent value="sections"><Sections /></TabsContent>
        <TabsContent value="subjects"><Subjects /></TabsContent>
      </Tabs>
    </div>
  );
}

function CrudList({ items, columns, onCreate, children, testid }) {
  return (
    <div className="space-y-4 mt-4" data-testid={testid}>
      {children}
      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>{columns.map((c) => <th key={c.key} className="text-left px-4 py-3">{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={columns.length} className="text-center py-10 text-muted-foreground">Nothing yet.</td></tr>}
              {items.map((it) => (
                <tr key={it.id} className="border-t border-border">
                  {columns.map((c) => <td key={c.key} className={`px-4 py-2 ${c.mono ? "font-mono" : ""}`}>{c.render ? c.render(it) : (it[c.key] ?? "—")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function Departments() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ name: "", code: "" });
  const load = () => api.get("/academic/departments").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);
  const create = async (e) => { e.preventDefault(); try { await api.post("/academic/departments", form); toast.success("Created"); setForm({ name: "", code: "" }); load(); } catch (err) { toast.error(err.response?.data?.detail || "Failed"); } };
  return (
    <CrudList testid="departments-list" items={items} columns={[{ key: "name", label: "Name" }, { key: "code", label: "Code", mono: true }, { key: "description", label: "Description" }]}>
      <form onSubmit={create} className="flex gap-2">
        <Input placeholder="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" data-testid="dept-name-input" />
        <Input placeholder="Code" required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="rounded-sm font-mono w-32" data-testid="dept-code-input" />
        <Button type="submit" className="rounded-sm" data-testid="dept-create-btn"><Plus size={14} className="mr-1" /> Add</Button>
      </form>
    </CrudList>
  );
}

function Units() {
  const [items, setItems] = useState([]);
  const [depts, setDepts] = useState([]);
  const [form, setForm] = useState({ name: "", code: "", department_id: "" });
  const load = () => api.get("/academic/units").then((r) => setItems(r.data));
  useEffect(() => { load(); api.get("/academic/departments").then((r) => setDepts(r.data)); }, []);
  const create = async (e) => { e.preventDefault(); try { await api.post("/academic/units", form); toast.success("Created"); setForm({ name: "", code: "", department_id: "" }); load(); } catch (err) { toast.error(err.response?.data?.detail || "Failed"); } };
  return (
    <CrudList testid="units-list" items={items} columns={[{ key: "name", label: "Name" }, { key: "code", label: "Code", mono: true }]}>
      <form onSubmit={create} className="flex gap-2 flex-wrap">
        <Input placeholder="Name (e.g. B.Tech CSE)" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" />
        <Input placeholder="Code" required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="rounded-sm font-mono w-40" />
        <Select value={form.department_id} onValueChange={(v) => setForm({ ...form, department_id: v })}>
          <SelectTrigger className="rounded-sm w-48"><SelectValue placeholder="Department (opt)" /></SelectTrigger>
          <SelectContent>{depts.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent>
        </Select>
        <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
      </form>
    </CrudList>
  );
}

function Levels() {
  const [items, setItems] = useState([]);
  const [units, setUnits] = useState([]);
  const [form, setForm] = useState({ name: "", unit_id: "", sequence: 1 });
  const load = () => api.get("/academic/levels").then((r) => setItems(r.data));
  useEffect(() => { load(); api.get("/academic/units").then((r) => setUnits(r.data)); }, []);
  const create = async (e) => { e.preventDefault(); try { await api.post("/academic/levels", { ...form, sequence: Number(form.sequence) }); toast.success("Created"); setForm({ name: "", unit_id: "", sequence: 1 }); load(); } catch (err) { toast.error(err.response?.data?.detail || "Failed"); } };
  return (
    <CrudList testid="levels-list" items={items} columns={[{ key: "name", label: "Name" }, { key: "sequence", label: "Sequence", mono: true }]}>
      <form onSubmit={create} className="flex gap-2 flex-wrap">
        <Input placeholder="Name (e.g. Year 2)" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" />
        <Select value={form.unit_id} onValueChange={(v) => setForm({ ...form, unit_id: v })}>
          <SelectTrigger className="rounded-sm w-56"><SelectValue placeholder="Unit" /></SelectTrigger>
          <SelectContent>{units.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
        </Select>
        <Input type="number" min={0} placeholder="Seq" required value={form.sequence} onChange={(e) => setForm({ ...form, sequence: e.target.value })} className="rounded-sm font-mono w-24" />
        <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
      </form>
    </CrudList>
  );
}

function Sections() {
  const [items, setItems] = useState([]);
  const [levels, setLevels] = useState([]);
  const [form, setForm] = useState({ name: "", level_id: "", room: "" });
  const load = () => api.get("/academic/sections").then((r) => setItems(r.data));
  useEffect(() => { load(); api.get("/academic/levels").then((r) => setLevels(r.data)); }, []);
  const create = async (e) => { e.preventDefault(); try { await api.post("/academic/sections", form); toast.success("Created"); setForm({ name: "", level_id: "", room: "" }); load(); } catch (err) { toast.error(err.response?.data?.detail || "Failed"); } };
  return (
    <CrudList testid="sections-list" items={items} columns={[{ key: "name", label: "Name" }, { key: "room", label: "Room" }]}>
      <form onSubmit={create} className="flex gap-2 flex-wrap">
        <Input placeholder="Section name (A, B…)" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm w-32" />
        <Select value={form.level_id} onValueChange={(v) => setForm({ ...form, level_id: v })}>
          <SelectTrigger className="rounded-sm w-56"><SelectValue placeholder="Level" /></SelectTrigger>
          <SelectContent>{levels.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
        </Select>
        <Input placeholder="Room (opt)" value={form.room} onChange={(e) => setForm({ ...form, room: e.target.value })} className="rounded-sm w-32" />
        <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
      </form>
    </CrudList>
  );
}

function Subjects() {
  const [items, setItems] = useState([]);
  const [depts, setDepts] = useState([]);
  const [form, setForm] = useState({ name: "", code: "", credits: 3, department_id: "" });
  const load = () => api.get("/academic/subjects").then((r) => setItems(r.data));
  useEffect(() => { load(); api.get("/academic/departments").then((r) => setDepts(r.data)); }, []);
  const create = async (e) => { e.preventDefault(); try { await api.post("/academic/subjects", { ...form, credits: Number(form.credits) }); toast.success("Created"); setForm({ name: "", code: "", credits: 3, department_id: "" }); load(); } catch (err) { toast.error(err.response?.data?.detail || "Failed"); } };
  return (
    <CrudList testid="subjects-list" items={items} columns={[{ key: "name", label: "Name" }, { key: "code", label: "Code", mono: true }, { key: "credits", label: "Credits", mono: true }]}>
      <form onSubmit={create} className="flex gap-2 flex-wrap">
        <Input placeholder="Subject name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" />
        <Input placeholder="Code" required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="rounded-sm font-mono w-32" />
        <Input type="number" placeholder="Credits" min={0} value={form.credits} onChange={(e) => setForm({ ...form, credits: e.target.value })} className="rounded-sm font-mono w-24" />
        <Select value={form.department_id} onValueChange={(v) => setForm({ ...form, department_id: v })}>
          <SelectTrigger className="rounded-sm w-48"><SelectValue placeholder="Department (opt)" /></SelectTrigger>
          <SelectContent>{depts.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent>
        </Select>
        <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
      </form>
    </CrudList>
  );
}
