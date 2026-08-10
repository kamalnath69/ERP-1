import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AuthLayout } from "@/pages/Login";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import PasswordStrength, { isPasswordAcceptable } from "@/components/PasswordStrength";
import { toast } from "sonner";

export default function PlatformInvite() {
  const [form, setForm] = useState({ email: "", code: "", password: "", confirm: "" }); const [saving, setSaving] = useState(false);
  const { refreshMe } = useAuth(); const navigate = useNavigate(); const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const passwordReady = isPasswordAcceptable(form.password);
  const submit = async (event) => { event.preventDefault(); if (!passwordReady) { toast.error("Please choose a stronger password"); return; } if (form.password !== form.confirm) { toast.error("Passwords do not match"); return; } setSaving(true); try { await api.post("/auth/platform-invite/accept", { email: form.email, code: form.code, new_password: form.password }); await refreshMe(); navigate("/super"); } catch (error) { toast.error(error.response?.data?.detail || "Invitation could not be accepted"); } finally { setSaving(false); } };
  return <AuthLayout eyebrow="Platform team" title="Activate your account."><form className="space-y-4 mt-6" onSubmit={submit}><Field label="Work email"><Input type="email" value={form.email} onChange={(event) => set("email", event.target.value)} required /></Field><Field label="Invitation code"><Input inputMode="numeric" maxLength={6} value={form.code} onChange={(event) => set("code", event.target.value.replace(/\D/g, ""))} required /></Field><Field label="Create password"><Input type="password" value={form.password} onChange={(event) => set("password", event.target.value)} required /><PasswordStrength password={form.password} compact /></Field><Field label="Confirm password"><Input type="password" value={form.confirm} onChange={(event) => set("confirm", event.target.value)} required />{form.confirm && <p className={`text-xs mt-1 ${form.confirm === form.password ? "text-emerald-700" : "text-red-600"}`}>{form.confirm === form.password ? "Passwords match" : "Passwords do not match"}</p>}</Field><Button className="w-full" disabled={saving || form.code.length !== 6 || !passwordReady || form.confirm !== form.password}>{saving ? "Activating..." : "Activate account"}</Button></form></AuthLayout>;
}

function Field({ label, children }) { return <label className="block"><Label>{label}</Label><div className="mt-2">{children}</div></label>; }
