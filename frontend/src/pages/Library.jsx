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

export default function Library() {
  return (
    <div className="space-y-6" data-testid="library-page">
      <header>
        <div className="overline text-muted-foreground">Library</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Books & loans</h1>
      </header>
      <Tabs defaultValue="books">
        <TabsList className="rounded-sm bg-secondary"><TabsTrigger value="books" className="rounded-sm">Books</TabsTrigger><TabsTrigger value="loans" className="rounded-sm">Loans</TabsTrigger></TabsList>
        <TabsContent value="books"><Books /></TabsContent>
        <TabsContent value="loans"><Loans /></TabsContent>
      </Tabs>
    </div>
  );
}

function Books() {
  const [books, setBooks] = useState([]);
  const [form, setForm] = useState({ title: "", author: "", isbn: "", category: "", total_copies: 1 });
  const load = () => api.get("/library/books").then((r) => setBooks(r.data));
  useEffect(() => { load(); }, []);
  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/library/books", { ...form, total_copies: Number(form.total_copies) }); toast.success("Book added"); setForm({ title: "", author: "", isbn: "", category: "", total_copies: 1 }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="mt-4 space-y-4">
      <Card className="rounded-sm border-border">
        <CardContent className="p-4">
          <form onSubmit={create} className="grid md:grid-cols-6 gap-3 items-end">
            <div className="md:col-span-2"><Label className="text-xs">Title</Label><Input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-sm" data-testid="book-title" /></div>
            <div><Label className="text-xs">Author</Label><Input value={form.author} onChange={(e) => setForm({ ...form, author: e.target.value })} className="rounded-sm" /></div>
            <div><Label className="text-xs">ISBN</Label><Input value={form.isbn} onChange={(e) => setForm({ ...form, isbn: e.target.value })} className="rounded-sm font-mono" /></div>
            <div><Label className="text-xs">Copies</Label><Input type="number" min={1} value={form.total_copies} onChange={(e) => setForm({ ...form, total_copies: e.target.value })} className="rounded-sm font-mono" /></div>
            <Button type="submit" className="rounded-sm"><Plus size={14} className="mr-1" /> Add</Button>
          </form>
        </CardContent>
      </Card>
      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest"><tr><th className="text-left px-4 py-3">Title</th><th className="text-left px-4 py-3">Author</th><th className="text-left px-4 py-3">ISBN</th><th className="text-right px-4 py-3">Available / Total</th></tr></thead>
            <tbody>
              {books.length === 0 && <tr><td colSpan={4} className="text-center py-10 text-muted-foreground">No books.</td></tr>}
              {books.map((b) => (
                <tr key={b.id} className="border-t border-border"><td className="px-4 py-3">{b.title}</td><td className="px-4 py-3">{b.author || "—"}</td><td className="px-4 py-3 font-mono text-xs">{b.isbn || "—"}</td><td className="px-4 py-3 text-right font-mono">{b.available_copies} / {b.total_copies}</td></tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function Loans() {
  const [loans, setLoans] = useState([]);
  const [books, setBooks] = useState([]);
  const [students, setStudents] = useState([]);
  const [form, setForm] = useState({ book_id: "", student_id: "", due_on: "" });
  const load = () => api.get("/library/loans").then((r) => setLoans(r.data));
  useEffect(() => {
    load(); api.get("/library/books").then((r) => setBooks(r.data));
    api.get("/students").then((r) => setStudents(r.data));
  }, []);
  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/library/loans", form); toast.success("Loan created"); setForm({ book_id: "", student_id: "", due_on: "" }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const ret = async (id) => { await api.post(`/library/loans/${id}/return`); load(); toast.success("Returned"); };
  return (
    <div className="mt-4 space-y-4">
      <Card className="rounded-sm border-border">
        <CardContent className="p-4">
          <form onSubmit={create} className="grid md:grid-cols-4 gap-3 items-end">
            <div>
              <Label className="text-xs">Book</Label>
              <Select value={form.book_id} onValueChange={(v) => setForm({ ...form, book_id: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{books.filter((b) => b.available_copies > 0).map((b) => <SelectItem key={b.id} value={b.id}>{b.title}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Student</Label>
              <Select value={form.student_id} onValueChange={(v) => setForm({ ...form, student_id: v })}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{students.map((s) => <SelectItem key={s.id} value={s.id}>{s.first_name} {s.last_name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label className="text-xs">Due</Label><Input type="date" value={form.due_on} onChange={(e) => setForm({ ...form, due_on: e.target.value })} className="rounded-sm font-mono" /></div>
            <Button type="submit" className="rounded-sm">Issue</Button>
          </form>
        </CardContent>
      </Card>
      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest"><tr><th className="text-left px-4 py-3">Book</th><th className="text-left px-4 py-3">Student</th><th className="text-left px-4 py-3">Borrowed</th><th className="text-left px-4 py-3">Due</th><th className="text-left px-4 py-3">Returned</th><th></th></tr></thead>
            <tbody>
              {loans.length === 0 && <tr><td colSpan={6} className="text-center py-10 text-muted-foreground">No loans.</td></tr>}
              {loans.map((l) => {
                const b = books.find((x) => x.id === l.book_id);
                const s = students.find((x) => x.id === l.student_id);
                return (
                  <tr key={l.id} className="border-t border-border">
                    <td className="px-4 py-3">{b?.title || l.book_id.slice(0,8)}</td>
                    <td className="px-4 py-3">{s ? `${s.first_name} ${s.last_name}` : l.student_id.slice(0,8)}</td>
                    <td className="px-4 py-3 font-mono text-xs">{l.borrowed_on}</td>
                    <td className="px-4 py-3 font-mono text-xs">{l.due_on || "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs">{l.returned_on || "—"}</td>
                    <td className="px-4 py-3">{!l.returned_on && <Button size="sm" variant="outline" onClick={() => ret(l.id)} className="rounded-sm">Return</Button>}</td>
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
