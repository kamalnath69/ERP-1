import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export default function Register() {
  const nav = useNavigate();
  const { registerOrg } = useAuth();
  const [form, setForm] = useState({
    organization_name: "",
    organization_slug: "",
    org_type: "college",
    admin_first_name: "",
    admin_last_name: "",
    admin_email: "",
    admin_password: "",
  });
  const [loading, setLoading] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target?.value ?? e });

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await registerOrg(form);
      toast.success("Your organization is live");
      nav("/app");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-secondary/30">
      <Card className="w-full max-w-2xl border border-border rounded-sm">
        <CardHeader>
          <div className="overline text-muted-foreground">Athena · Start free trial</div>
          <CardTitle className="font-display text-3xl tracking-tight">Provision your institution</CardTitle>
          <CardDescription>You will become the Principal / Administrator of a fresh tenant.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid md:grid-cols-2 gap-4" data-testid="register-form">
            <div className="space-y-2 md:col-span-2">
              <Label>Institution name</Label>
              <Input value={form.organization_name} onChange={set("organization_name")} required className="rounded-sm" data-testid="reg-org-name" />
            </div>
            <div className="space-y-2">
              <Label>URL slug</Label>
              <Input value={form.organization_slug} onChange={(e) => setForm({ ...form, organization_slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} required className="rounded-sm font-mono" placeholder="acme-college" data-testid="reg-org-slug" />
            </div>
            <div className="space-y-2">
              <Label>Type</Label>
              <Select value={form.org_type} onValueChange={(v) => setForm({ ...form, org_type: v })}>
                <SelectTrigger className="rounded-sm" data-testid="reg-org-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="school">School (K-12)</SelectItem>
                  <SelectItem value="college">College</SelectItem>
                  <SelectItem value="university">University</SelectItem>
                  <SelectItem value="training_institute">Training Institute</SelectItem>
                  <SelectItem value="coaching_centre">Coaching Centre</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>First name</Label>
              <Input value={form.admin_first_name} onChange={set("admin_first_name")} required className="rounded-sm" data-testid="reg-first-name" />
            </div>
            <div className="space-y-2">
              <Label>Last name</Label>
              <Input value={form.admin_last_name} onChange={set("admin_last_name")} required className="rounded-sm" data-testid="reg-last-name" />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label>Work email</Label>
              <Input type="email" value={form.admin_email} onChange={set("admin_email")} required className="rounded-sm" data-testid="reg-email" />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label>Password (min 8 chars)</Label>
              <Input type="password" value={form.admin_password} onChange={set("admin_password")} required minLength={8} className="rounded-sm" data-testid="reg-password" />
            </div>
            <div className="md:col-span-2 flex items-center justify-between pt-2">
              <Link to="/login" className="text-xs text-muted-foreground hover:underline">Already have an account?</Link>
              <Button type="submit" size="lg" className="rounded-sm" disabled={loading} data-testid="reg-submit-btn">
                {loading ? "Creating…" : "Create organization"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
