import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { API_BASE } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { CheckCircle } from "@phosphor-icons/react";

export default function PublicAdmissions() {
  const { slug } = useParams();
  const [org, setOrg] = useState(null);
  const [form, setForm] = useState({
    first_name: "", last_name: "", email: "", phone: "", date_of_birth: "",
    prev_school: "", interest_department: "",
    parent_name: "", parent_phone: "", parent_email: "", notes: "",
  });
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    axios.get(`${API_BASE}/public/organization/${slug}`).then((r) => setOrg(r.data)).catch(() => setOrg(null));
  }, [slug]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = { org_slug: slug, ...form };
      Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });
      await axios.post(`${API_BASE}/public/admissions`, payload);
      setSubmitted(true);
    } catch (err) {
      toast.error(err.response?.data?.detail?.[0]?.msg || err.response?.data?.detail || "Application failed");
    }
  };

  if (!org && slug) {
    return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Loading admissions portal…</div>;
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-secondary/30">
        <Card className="rounded-sm border-border max-w-md">
          <CardContent className="p-10 text-center">
            <CheckCircle size={48} weight="fill" className="mx-auto text-emerald-600" />
            <h1 className="mt-4 font-display text-2xl tracking-tight">Application received</h1>
            <p className="text-sm text-muted-foreground mt-2">
              {org?.name} will get back to you shortly on <span className="font-mono">{form.email}</span>.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background" data-testid="public-admissions-page">
      <nav className="border-b border-border">
        <div className="max-w-4xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-display font-bold tracking-tight">{org?.name}</span>
            <span className="overline">Admissions</span>
          </div>
          <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Powered by Athena</div>
        </div>
      </nav>
      <section className="max-w-4xl mx-auto px-6 py-12">
        <div className="overline text-accent">Apply now</div>
        <h1 className="text-4xl sm:text-5xl font-display font-bold tracking-tight mt-3">Join {org?.name}.</h1>
        <p className="mt-4 text-muted-foreground max-w-2xl">Fill in the details below. Your application enters the admissions team's queue immediately — expect an email within 2 working days.</p>

        <Card className="rounded-sm border-border mt-10">
          <CardContent className="p-6 md:p-10">
            <form onSubmit={submit} className="grid md:grid-cols-2 gap-4" data-testid="admissions-form">
              <div className="md:col-span-2 overline">Applicant</div>
              <div><Label>First name *</Label><Input required value={form.first_name} onChange={set("first_name")} className="rounded-sm" data-testid="app-first-name" /></div>
              <div><Label>Last name *</Label><Input required value={form.last_name} onChange={set("last_name")} className="rounded-sm" data-testid="app-last-name" /></div>
              <div><Label>Email *</Label><Input required type="email" value={form.email} onChange={set("email")} className="rounded-sm" data-testid="app-email" /></div>
              <div><Label>Phone</Label><Input value={form.phone} onChange={set("phone")} className="rounded-sm font-mono" /></div>
              <div><Label>Date of birth</Label><Input type="date" value={form.date_of_birth} onChange={set("date_of_birth")} className="rounded-sm font-mono" /></div>
              <div><Label>Interested in (dept / stream)</Label><Input value={form.interest_department} onChange={set("interest_department")} className="rounded-sm" /></div>
              <div className="md:col-span-2"><Label>Previous school / college</Label><Input value={form.prev_school} onChange={set("prev_school")} className="rounded-sm" /></div>

              <div className="md:col-span-2 overline pt-6">Parent / Guardian</div>
              <div><Label>Name</Label><Input value={form.parent_name} onChange={set("parent_name")} className="rounded-sm" /></div>
              <div><Label>Phone</Label><Input value={form.parent_phone} onChange={set("parent_phone")} className="rounded-sm font-mono" /></div>
              <div className="md:col-span-2"><Label>Email</Label><Input type="email" value={form.parent_email} onChange={set("parent_email")} className="rounded-sm" /></div>

              <div className="md:col-span-2"><Label>Anything else?</Label><Textarea value={form.notes} onChange={set("notes")} className="rounded-sm" /></div>

              <div className="md:col-span-2 flex justify-end pt-4">
                <Button type="submit" size="lg" className="rounded-sm" data-testid="app-submit-btn">Submit application</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
