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

export default function Transport() {
  return (
    <div className="space-y-6" data-testid="transport-page">
      <header><div className="overline text-muted-foreground">Transport</div><h1 className="text-3xl font-display font-bold tracking-tight mt-1">Routes & vehicles</h1></header>
      <Tabs defaultValue="routes">
        <TabsList className="rounded-sm bg-secondary"><TabsTrigger value="routes" className="rounded-sm">Routes</TabsTrigger><TabsTrigger value="vehicles" className="rounded-sm">Vehicles</TabsTrigger></TabsList>
        <TabsContent value="routes"><Routes /></TabsContent>
        <TabsContent value="vehicles"><Vehicles /></TabsContent>
      </Tabs>
    </div>
  );
}

function Routes() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ name: "", code: "", fare_monthly: 0, stops_text: "" });
  const load = () => api.get("/transport/routes").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);
  const create = async (e) => {
    e.preventDefault();
    const stops = form.stops_text.split(",").map((s) => s.trim()).filter(Boolean);
    try { await api.post("/transport/routes", { name: form.name, code: form.code || null, stops, fare_monthly: Number(form.fare_monthly) }); toast.success("Route added"); setForm({ name: "", code: "", fare_monthly: 0, stops_text: "" }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="mt-4 space-y-4">
      <Card className="rounded-sm border-border">
        <CardContent className="p-4">
          <form onSubmit={create} className="grid md:grid-cols-5 gap-3 items-end">
            <div><Label className="text-xs">Name</Label><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm" data-testid="route-name" /></div>
            <div><Label className="text-xs">Code</Label><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="rounded-sm font-mono" /></div>
            <div><Label className="text-xs">Fare (₹/mo)</Label><Input type="number" min={0} value={form.fare_monthly} onChange={(e) => setForm({ ...form, fare_monthly: e.target.value })} className="rounded-sm font-mono" /></div>
            <div><Label className="text-xs">Stops (comma-sep)</Label><Input value={form.stops_text} onChange={(e) => setForm({ ...form, stops_text: e.target.value })} className="rounded-sm" placeholder="A, B, C" /></div>
            <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
          </form>
        </CardContent>
      </Card>
      <Card className="rounded-sm border-border"><CardContent className="p-0">
        <table className="w-full text-sm"><thead className="bg-secondary text-xs uppercase tracking-widest"><tr><th className="text-left px-4 py-3">Name</th><th className="text-left px-4 py-3">Code</th><th className="text-left px-4 py-3">Stops</th><th className="text-right px-4 py-3">Fare/mo</th></tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={4} className="text-center py-10 text-muted-foreground">No routes.</td></tr>}
            {items.map((r) => <tr key={r.id} className="border-t border-border"><td className="px-4 py-3">{r.name}</td><td className="px-4 py-3 font-mono">{r.code || "—"}</td><td className="px-4 py-3 text-xs">{(r.stops || []).join(" → ") || "—"}</td><td className="px-4 py-3 text-right font-mono">₹{r.fare_monthly.toLocaleString()}</td></tr>)}
          </tbody>
        </table>
      </CardContent></Card>
    </div>
  );
}

function Vehicles() {
  const [items, setItems] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [form, setForm] = useState({ registration_number: "", capacity: 40, route_id: "", driver_name: "", driver_phone: "" });
  const load = () => api.get("/transport/vehicles").then((r) => setItems(r.data));
  useEffect(() => { load(); api.get("/transport/routes").then((r) => setRoutes(r.data)); }, []);
  const create = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form, capacity: Number(form.capacity) };
      Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });
      await api.post("/transport/vehicles", payload);
      toast.success("Vehicle added"); setForm({ registration_number: "", capacity: 40, route_id: "", driver_name: "", driver_phone: "" }); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="mt-4 space-y-4">
      <Card className="rounded-sm border-border"><CardContent className="p-4">
        <form onSubmit={create} className="grid md:grid-cols-6 gap-3 items-end">
          <div><Label className="text-xs">Reg #</Label><Input required value={form.registration_number} onChange={(e) => setForm({ ...form, registration_number: e.target.value })} className="rounded-sm font-mono" data-testid="vehicle-reg" /></div>
          <div><Label className="text-xs">Capacity</Label><Input type="number" min={1} value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} className="rounded-sm font-mono" /></div>
          <div>
            <Label className="text-xs">Route</Label>
            <Select value={form.route_id} onValueChange={(v) => setForm({ ...form, route_id: v })}>
              <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{routes.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Driver</Label><Input value={form.driver_name} onChange={(e) => setForm({ ...form, driver_name: e.target.value })} className="rounded-sm" /></div>
          <div><Label className="text-xs">Driver phone</Label><Input value={form.driver_phone} onChange={(e) => setForm({ ...form, driver_phone: e.target.value })} className="rounded-sm font-mono" /></div>
          <Button type="submit" className="rounded-sm">Add</Button>
        </form>
      </CardContent></Card>
      <Card className="rounded-sm border-border"><CardContent className="p-0">
        <table className="w-full text-sm"><thead className="bg-secondary text-xs uppercase tracking-widest"><tr><th className="text-left px-4 py-3">Reg #</th><th className="text-right px-4 py-3">Capacity</th><th className="text-left px-4 py-3">Driver</th><th className="text-left px-4 py-3">Phone</th></tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={4} className="text-center py-10 text-muted-foreground">No vehicles.</td></tr>}
            {items.map((v) => <tr key={v.id} className="border-t border-border"><td className="px-4 py-3 font-mono">{v.registration_number}</td><td className="px-4 py-3 text-right font-mono">{v.capacity}</td><td className="px-4 py-3">{v.driver_name || "—"}</td><td className="px-4 py-3 font-mono">{v.driver_phone || "—"}</td></tr>)}
          </tbody>
        </table>
      </CardContent></Card>
    </div>
  );
}
