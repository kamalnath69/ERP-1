import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LockKey, ShieldCheck, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [needsMfa, setNeedsMfa] = useState(false);
  const [loading, setLoading] = useState(false);
  const [params] = useSearchParams();
  const location = useLocation();
  const { login } = useAuth();
  const navigate = useNavigate();
  useEffect(() => { if (params.get("expired")) toast.info("Your session expired. Please sign in again"); if (location.state?.email) setEmail(location.state.email); if (location.state?.workspace) setWorkspace(location.state.workspace); }, [location.state, params]);
  const submit = async (event) => {
    event.preventDefault(); setLoading(true);
    try { const user = await login(email, password, workspace, mfaCode); navigate(user.is_super_admin ? "/super" : "/app"); }
    catch (error) {
      const detail = error.response?.data?.detail || "Sign in failed";
      if (error.response?.status === 428) {
        setNeedsMfa(true);
        toast.info("Enter the code from your authenticator app");
      } else if (detail === "Email is not verified") {
        sessionStorage.setItem("edvatiq.pending_verification", JSON.stringify({ email, org_slug: workspace }));
        navigate("/verify-email", { state: { email, org_slug: workspace } });
      } else toast.error(detail);
    } finally { setLoading(false); }
  };
  const demo = (kind = "gym") => {
    const selected = kind === "college"
      ? { email: "owner@crescent-college.edvatiq.com", workspace: "crescent-college" }
      : { email: "owner@pulse-fitness.edvatiq.com", workspace: "pulse-fitness" };
    setEmail(selected.email);
    setPassword("Owner@123");
    setWorkspace(selected.workspace);
  };
  return <AuthLayout eyebrow="Welcome back" title="Sign in to your business.">
    <form onSubmit={submit} className="space-y-4 mt-6">
      <Field label="Work email"><Input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></Field>
      <Field label="Password" action={<Link to="/forgot-password" className="text-xs text-accent hover:underline">Forgot password?</Link>}><Input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></Field>
      <Field label="Business ID" hint="Only needed if this email is connected to more than one business."><Input value={workspace} onChange={(event) => setWorkspace(event.target.value.toLowerCase())} placeholder="your-business" /></Field>
      {needsMfa && <Field label="Authenticator code" hint="Use a 6-digit authenticator code or one recovery code."><Input autoFocus inputMode="numeric" autoComplete="one-time-code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value.trim())} required /></Field>}
      <Button className="w-full rounded-xl h-11" disabled={loading}>{loading ? "Signing in..." : "Sign in"}</Button>
    </form>
    <div className="mt-4 flex items-center justify-between gap-3 rounded-xl bg-secondary/60 p-3 text-xs"><span className="text-muted-foreground">Explore a seeded workspace</span><span className="flex gap-3"><button type="button" onClick={() => demo("gym")} className="font-semibold text-foreground">Gym</button><button type="button" onClick={() => demo("college")} className="font-semibold text-foreground">College</button></span></div>
    <div className="flex gap-2 items-center text-xs text-muted-foreground mt-4"><ShieldCheck className="text-emerald-700 shrink-0" />Your account and business information are protected.</div>
    <p className="text-sm text-center mt-5 text-muted-foreground">New to Edvatiq? <Link className="text-foreground font-medium" to="/register">Create your business</Link></p>
  </AuthLayout>;
}

export function AuthLayout({ eyebrow, title, children }) { return <div className="auth-shell bg-background soft-glow grid lg:grid-cols-2"><aside className="auth-aside hidden lg:flex bg-primary text-primary-foreground flex-col justify-between relative overflow-hidden"><div className="absolute inset-0 paper-grid opacity-10" /><Link to="/" className="relative font-display text-3xl font-bold">Edvatiq</Link><div className="relative"><div className="auth-aside-icon w-14 h-14 rounded-2xl bg-accent text-accent-foreground grid place-items-center"><LockKey size={28} /></div><blockquote className="auth-aside-title font-display text-5xl mt-7 leading-tight">Your business memory deserves a secure front door.</blockquote><p className="auth-aside-copy text-white/60 mt-5 max-w-md">Simple sign-in, verified accounts, and control over where you are signed in.</p></div><div className="relative text-sm text-white/40 flex gap-2 items-center"><Sparkle />Edvatiq Business OS</div></aside><main className="auth-main"><div className="auth-main-inner"><div className="auth-card w-full max-w-md"><div className="auth-mobile-brand lg:hidden font-display text-3xl font-bold">Edvatiq</div><div className="overline">{eyebrow}</div><h1 className="auth-title font-display text-3xl md:text-4xl font-bold mt-2">{title}</h1>{children}</div></div></main></div>; }
function Field({ label, action, hint, children }) { return <div><div className="flex justify-between items-center"><Label>{label}</Label>{action}</div><div className="mt-2">{children}</div>{hint && <p className="text-xs text-muted-foreground mt-1.5">{hint}</p>}</div>; }
