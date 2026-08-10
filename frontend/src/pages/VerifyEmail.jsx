import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { AuthLayout } from "@/pages/Login";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EnvelopeSimple, ShieldCheck } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function VerifyEmail() {
  const location = useLocation(); const navigate = useNavigate(); const { refreshMe } = useAuth();
  const saved = readPending(); const pending = location.state || saved || {};
  const [email, setEmail] = useState(pending.email || ""); const [orgSlug, setOrgSlug] = useState(pending.org_slug || "");
  const [code, setCode] = useState(""); const [loading, setLoading] = useState(false); const [cooldown, setCooldown] = useState(0); const [deliveryFailed] = useState(pending.email_sent === false);
  useEffect(() => { if (!cooldown) return undefined; const timer = setInterval(() => setCooldown((value) => Math.max(value - 1, 0)), 1000); return () => clearInterval(timer); }, [cooldown]);
  const verify = async (event) => { event.preventDefault(); setLoading(true); try { await api.post("/auth/email/verify", { email, org_slug: orgSlug || null, code }); sessionStorage.removeItem("edvatiq.pending_verification"); await refreshMe(); toast.success("Email verified"); navigate("/app"); } catch (error) { toast.error(error.response?.data?.detail || "Code could not be verified"); } finally { setLoading(false); } };
  const resend = async () => { if (cooldown) return; try { await api.post("/auth/email/request-code", { email, org_slug: orgSlug || null }); setCooldown(60); toast.info("If this account is awaiting verification, the email will arrive shortly"); } catch (error) { toast.error(error.response?.data?.detail || "Please wait before requesting another code"); } };
  return <AuthLayout eyebrow="Verify ownership" title={deliveryFailed ? "Email delivery is delayed." : "Check your email."}><div className="w-12 h-12 rounded-2xl bg-accent/10 text-accent grid place-items-center mt-5"><EnvelopeSimple size={24} /></div><p className="text-sm text-muted-foreground mt-3">{deliveryFailed ? "We created your account, but your verification email could not be delivered. Try sending a new code shortly." : "Enter the six-digit code sent to your work email. It expires in 10 minutes and can be used once."}</p><form onSubmit={verify} className="space-y-3 mt-5"><Field label="Work email"><Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></Field><Field label="Business ID"><Input value={orgSlug} onChange={(event) => setOrgSlug(event.target.value.toLowerCase())} /></Field><Field label="Verification code"><Input inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" className="text-center text-2xl tracking-[.45em] font-mono" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} required /></Field><Button className="w-full h-11" disabled={loading || code.length !== 6}>{loading ? "Verifying..." : "Verify and continue"}</Button></form><button onClick={resend} disabled={!!cooldown || !email} className="w-full text-sm text-muted-foreground mt-3 hover:text-foreground disabled:opacity-50">{cooldown ? `Resend available in ${cooldown}s` : "Send a new code"}</button><div className="flex gap-2 text-xs text-muted-foreground mt-4"><ShieldCheck className="text-emerald-700 shrink-0" />Edvatiq never asks you to share this code by phone or chat.</div><p className="text-sm text-center mt-4"><Link to="/login" className="text-foreground font-medium">Back to sign in</Link></p></AuthLayout>;
}
function readPending() { try { return JSON.parse(sessionStorage.getItem("edvatiq.pending_verification")); } catch { return null; } }
function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
