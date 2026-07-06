import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Plus } from "@phosphor-icons/react";

export default function Hostel() {
  return (
    <div className="space-y-6" data-testid="hostel-page">
      <header><div className="overline text-muted-foreground">Hostel</div><h1 className="text-3xl font-display font-bold tracking-tight mt-1">Blocks, rooms, allocations</h1></header>
      <Tabs defaultValue="blocks">
        <TabsList className="rounded-sm bg-secondary"><TabsTrigger value="blocks" className="rounded-sm">Blocks</TabsTrigger><TabsTrigger value="rooms" className="rounded-sm">Rooms</TabsTrigger><TabsTrigger value="allocate" className="rounded-sm">Allocate</TabsTrigger></TabsList>
        <TabsContent value="blocks"><Blocks /></TabsContent>
        <TabsContent value="rooms"><Rooms /></TabsContent>
        <TabsContent value="allocate"><Allocate /></TabsContent>
      </Tabs>
    </div>
  );
}

function Blocks() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ name: "", kind: "mixed" });
  const load = () => api.get("/hostel/blocks").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);
  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/hostel/blocks", form); toast.success("Block added"); setForm({ name: "", kind: "mixed" }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="mt-4 space-y-4">
      <Card className="rounded-sm border-border"><CardContent className="p-4">
        <form onSubmit={create} className="flex gap-3 items-end">
          <div className="flex-1"><Label className="text-xs">Name</Label><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" data-testid="block-name" /></div>
          <div>
            <Label className="text-xs">Kind</Label>
            <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v })}>
              <SelectTrigger className="rounded-sm w-40"><SelectValue /></SelectTrigger>
              <SelectContent>{["boys", "girls", "mixed"].map((k) => <SelectItem key={k} value={k}>{k}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
        </form>
      </CardContent></Card>
      <Card className="rounded-sm border-border"><CardContent className="p-0">
        <table className="w-full text-sm"><thead className="bg-secondary text-xs uppercase tracking-widest"><tr><th className="text-left px-4 py-3">Name</th><th className="text-left px-4 py-3">Kind</th></tr></thead>
          <tbody>{items.length === 0 && <tr><td colSpan={2} className="text-center py-10 text-muted-foreground">No blocks.</td></tr>}
            {items.map((b) => <tr key={b.id} className="border-t border-border"><td className="px-4 py-3">{b.name}</td><td className="px-4 py-3 uppercase font-mono text-xs">{b.kind}</td></tr>)}
          </tbody>
        </table>
      </CardContent></Card>
    </div>
  );
}

function Rooms() {
  const [items, setItems] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [form, setForm] = useState({ block_id: "", room_number: "", capacity: 2 });
  const load = () => api.get("/hostel/rooms").then((r) => setItems(r.data));
  useEffect(() => { load(); api.get("/hostel/blocks").then((r) => setBlocks(r.data)); }, []);
  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/hostel/rooms", { ...form, capacity: Number(form.capacity) }); toast.success("Room added"); setForm({ block_id: "", room_number: "", capacity: 2 }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const blockName = (id) => blocks.find((b) => b.id === id)?.name || "—";
  return (
    <div className="mt-4 space-y-4">
      <Card className="rounded-sm border-border"><CardContent className="p-4">
        <form onSubmit={create} className="grid md:grid-cols-4 gap-3 items-end">
          <div>
            <Label className="text-xs">Block</Label>
            <Select value={form.block_id} onValueChange={(v) => setForm({ ...form, block_id: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{blocks.map((b) => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Room #</Label><Input required value={form.room_number} onChange={(e) => setForm({ ...form, room_number: e.target.value })} className="rounded-sm font-mono" data-testid="room-number" /></div>
          <div><Label className="text-xs">Capacity</Label><Input type="number" min={1} value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} className="rounded-sm font-mono" /></div>
          <Button type="submit" className="rounded-sm">Add</Button>
        </form>
      </CardContent></Card>
      <Card className="rounded-sm border-border"><CardContent className="p-0">
        <table className="w-full text-sm"><thead className="bg-secondary text-xs uppercase tracking-widest"><tr><th className="text-left px-4 py-3">Block</th><th className="text-left px-4 py-3">Room</th><th className="text-right px-4 py-3">Occupied / Capacity</th></tr></thead>
          <tbody>{items.length === 0 && <tr><td colSpan={3} className="text-center py-10 text-muted-foreground">No rooms.</td></tr>}
            {items.map((r) => <tr key={r.id} className="border-t border-border"><td className="px-4 py-3">{blockName(r.block_id)}</td><td className="px-4 py-3 font-mono">{r.room_number}</td><td className="px-4 py-3 text-right font-mono">{r.occupied} / {r.capacity}</td></tr>)}
          </tbody>
        </table>
      </CardContent></Card>
    </div>
  );
}

function Allocate() {
  const [rooms, setRooms] = useState([]);
  const [students, setStudents] = useState([]);
  const [form, setForm] = useState({ student_id: "", room_id: "" });
  useEffect(() => { api.get("/hostel/rooms").then((r) => setRooms(r.data)); api.get("/students").then((r) => setStudents(r.data)); }, []);
  const submit = async (e) => {
    e.preventDefault();
    try { await api.post("/hostel/allocations", form); toast.success("Allocated"); setForm({ student_id: "", room_id: "" }); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <Card className="rounded-sm border-border mt-4"><CardContent className="p-6">
      <form onSubmit={submit} className="grid md:grid-cols-3 gap-3 items-end max-w-2xl">
        <div>
          <Label className="text-xs">Student</Label>
          <Select value={form.student_id} onValueChange={(v) => setForm({ ...form, student_id: v })}>
            <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>{students.map((s) => <SelectItem key={s.id} value={s.id}>{s.first_name} {s.last_name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Room</Label>
          <Select value={form.room_id} onValueChange={(v) => setForm({ ...form, room_id: v })}>
            <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>{rooms.filter((r) => r.occupied < r.capacity).map((r) => <SelectItem key={r.id} value={r.id}>Room {r.room_number} ({r.occupied}/{r.capacity})</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <Button type="submit" className="rounded-sm" data-testid="alloc-submit">Allocate</Button>
      </form>
    </CardContent></Card>
  );
}
