import React, { useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { patchUser, fetchMe } from "@/store/slices/authSlice";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import AvatarUploader from "@/components/AvatarUploader";
import { toast } from "sonner";
import { FloppyDisk, Key } from "@phosphor-icons/react";

export default function MyProfile() {
  const { user, organization, roles, permissions } = useAuth();
  const dispatch = useDispatch();

  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    phone: "",
    designation: "",
    bio: "",
    avatar_base64: null,
  });
  const [saving, setSaving] = useState(false);

  // Password change
  const [pw, setPw] = useState({ current_password: "", new_password: "", confirm: "" });
  const [pwSaving, setPwSaving] = useState(false);

  useEffect(() => {
    if (user) {
      setForm({
        first_name: user.first_name || "",
        last_name: user.last_name || "",
        phone: user.phone || "",
        designation: user.designation || "",
        bio: user.bio || "",
        avatar_base64: user.avatar_base64 || null,
      });
    }
  }, [user]);

  const initials = (user?.first_name?.[0] || "?") + (user?.last_name?.[0] || "");

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.patch("/users/me/profile", form);
      dispatch(patchUser(data));
      dispatch(fetchMe());
      toast.success("Profile updated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async () => {
    if (pw.new_password !== pw.confirm) {
      toast.error("New passwords do not match");
      return;
    }
    if (pw.new_password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setPwSaving(true);
    try {
      await api.post("/users/me/password", {
        current_password: pw.current_password,
        new_password: pw.new_password,
      });
      toast.success("Password changed");
      setPw({ current_password: "", new_password: "", confirm: "" });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to change password");
    } finally {
      setPwSaving(false);
    }
  };

  if (!user) return null;

  return (
    <div className="space-y-6 max-w-4xl" data-testid="my-profile-page">
      <header>
        <div className="overline text-muted-foreground">Account</div>
        <h1 className="text-4xl font-display font-bold tracking-tight mt-1">My Profile</h1>
        <p className="text-sm text-muted-foreground mt-2">
          {user.email} · {organization?.name || "Platform"}
        </p>
      </header>

      <Card className="rounded-sm border-border">
        <CardHeader>
          <CardTitle className="font-display text-lg">Profile details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <AvatarUploader
            value={form.avatar_base64}
            onChange={(v) => setForm((f) => ({ ...f, avatar_base64: v }))}
            initials={initials}
          />

          <div className="grid md:grid-cols-2 gap-4">
            <Field label="First name">
              <Input
                value={form.first_name}
                onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))}
                data-testid="profile-first-name"
              />
            </Field>
            <Field label="Last name">
              <Input
                value={form.last_name}
                onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))}
                data-testid="profile-last-name"
              />
            </Field>
            <Field label="Phone">
              <Input
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                data-testid="profile-phone"
              />
            </Field>
            <Field label="Designation">
              <Input
                value={form.designation}
                onChange={(e) => setForm((f) => ({ ...f, designation: e.target.value }))}
                placeholder="e.g. Principal, HOD Physics"
                data-testid="profile-designation"
              />
            </Field>
          </div>

          <Field label="Bio">
            <Textarea
              rows={3}
              value={form.bio}
              onChange={(e) => setForm((f) => ({ ...f, bio: e.target.value }))}
              placeholder="A short bio…"
              data-testid="profile-bio"
            />
          </Field>

          <div className="flex justify-end">
            <Button onClick={save} disabled={saving} className="rounded-sm" data-testid="profile-save-btn">
              <FloppyDisk size={14} className="mr-2" /> {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm border-border">
        <CardHeader>
          <CardTitle className="font-display text-lg">Roles &amp; permissions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <div className="overline text-muted-foreground">Assigned roles</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(roles || []).length === 0 ? (
                <span className="text-sm text-muted-foreground">No roles assigned.</span>
              ) : (
                roles.map((r) => (
                  <span key={r.id || r.slug} className="text-xs border border-border px-2 py-1 rounded-sm uppercase tracking-widest">
                    {r.name}
                  </span>
                ))
              )}
            </div>
          </div>
          <Separator />
          <div>
            <div className="overline text-muted-foreground">Effective permissions ({permissions?.length || 0})</div>
            <div className="mt-2 flex flex-wrap gap-1.5 max-h-64 overflow-y-auto">
              {(permissions || []).map((code) => (
                <span key={code} className="text-[11px] font-mono border border-border px-2 py-0.5">
                  {code}
                </span>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm border-border">
        <CardHeader>
          <CardTitle className="font-display text-lg flex items-center gap-2">
            <Key size={16} /> Change password
          </CardTitle>
        </CardHeader>
        <CardContent className="grid md:grid-cols-3 gap-4">
          <Field label="Current password">
            <Input
              type="password"
              value={pw.current_password}
              onChange={(e) => setPw((p) => ({ ...p, current_password: e.target.value }))}
              data-testid="pw-current"
            />
          </Field>
          <Field label="New password">
            <Input
              type="password"
              value={pw.new_password}
              onChange={(e) => setPw((p) => ({ ...p, new_password: e.target.value }))}
              data-testid="pw-new"
            />
          </Field>
          <Field label="Confirm new password">
            <Input
              type="password"
              value={pw.confirm}
              onChange={(e) => setPw((p) => ({ ...p, confirm: e.target.value }))}
              data-testid="pw-confirm"
            />
          </Field>
          <div className="md:col-span-3 flex justify-end">
            <Button onClick={changePassword} disabled={pwSaving} variant="outline" className="rounded-sm" data-testid="pw-save-btn">
              {pwSaving ? "Saving…" : "Update password"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <Label className="overline text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
