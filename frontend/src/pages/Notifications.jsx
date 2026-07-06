import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { PaperPlane } from "@phosphor-icons/react";

export default function Notifications() {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const load = () => api.get("/notifications").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);
  const markRead = async (id) => { await api.post(`/notifications/${id}/read`); load(); };

  return (
    <div className="space-y-6" data-testid="notifications-page">
      <header className="flex items-baseline justify-between">
        <div><div className="overline text-muted-foreground">Notifications</div><h1 className="text-3xl font-display font-bold tracking-tight mt-1">Inbox</h1></div>
        {can("notifications.send") && <SendDialog onSent={load} />}
      </header>
      <div className="grid gap-2">
        {items.length === 0 && <div className="text-sm text-muted-foreground">No notifications.</div>}
        {items.map((n) => (
          <Card key={n.id} className={`rounded-sm border-border ${n.is_read ? "opacity-60" : ""}`}>
            <CardContent className="p-4 flex gap-4 items-baseline">
              <span className={`overline ${n.kind === "success" ? "text-emerald-600" : n.kind === "warning" ? "text-amber-600" : n.kind === "error" ? "text-destructive" : "text-accent"}`}>{n.kind}</span>
              <div className="flex-1">
                <div className="font-medium">{n.title}</div>
                {n.body && <div className="text-sm text-muted-foreground mt-1">{n.body}</div>}
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mt-2">
                  {new Date(n.created_at).toLocaleString()}
                </div>
              </div>
              {!n.is_read && <Button size="sm" variant="outline" onClick={() => markRead(n.id)} className="rounded-sm">Mark read</Button>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function SendDialog({ onSent }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", body: "", kind: "info", role_slug: "", all_users: false });
  const submit = async () => {
    if (!form.title) return toast.error("Title required");
    try {
      const payload = { title: form.title, body: form.body, kind: form.kind };
      if (form.role_slug) payload.role_slug = form.role_slug;
      else payload.all_users = true;
      const { data } = await api.post("/notifications-send", payload);
      toast.success(`Delivered to ${data.sent} users`);
      setOpen(false); setForm({ title: "", body: "", kind: "info", role_slug: "", all_users: false });
      onSent();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="rounded-sm" data-testid="new-notif-btn"><PaperPlane size={14} className="mr-2" /> Send notification</Button></DialogTrigger>
      <DialogContent className="rounded-sm">
        <DialogHeader><DialogTitle className="font-display tracking-tight">Send notification</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Title</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-sm" data-testid="notif-title" /></div>
          <div><Label>Body</Label><Textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} className="rounded-sm" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Kind</Label>
              <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
                <SelectContent>{["info", "success", "warning", "error"].map((k) => <SelectItem key={k} value={k}>{k}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Target role (or leave blank = all)</Label>
              <Select value={form.role_slug} onValueChange={(v) => setForm({ ...form, role_slug: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="All users" /></SelectTrigger>
                <SelectContent>{["principal", "faculty", "student", "parent", "hod", "class-advisor"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex justify-end"><Button onClick={submit} className="rounded-sm" data-testid="notif-send-submit">Send</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
