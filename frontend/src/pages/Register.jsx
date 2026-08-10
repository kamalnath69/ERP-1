import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import PasswordStrength, { isPasswordAcceptable } from "@/components/PasswordStrength";
import { Barbell, CheckCircle, CircleNotch, GraduationCap, Scissors, Stethoscope, XCircle } from "@phosphor-icons/react";
import { toast } from "sonner";

const industries = [
  { id: "gym", label: "Gym & fitness", icon: Barbell, desc: "Memberships, check-ins and coaching" },
  { id: "salon", label: "Salon & spa", icon: Scissors, desc: "Appointments, services and checkout" },
  { id: "clinic", label: "Outpatient clinic", icon: Stethoscope, desc: "Queue, clinical records, lab and pharmacy" },
  { id: "college", label: "College & higher education", icon: GraduationCap, desc: "Students, academics, coding readiness and placements" },
];

const businessId = (value) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

export default function Register() {
  const { registerOrg } = useAuth(); const navigate = useNavigate();
  const [step, setStep] = useState(1); const [loading, setLoading] = useState(false); const [slugState, setSlugState] = useState({ status: "idle", message: "" });
  const [form, setForm] = useState({ industry: "gym", organization_name: "", organization_slug: "", location_name: "Main Location", city: "", admin_first_name: "", admin_last_name: "", admin_email: "", admin_password: "", admin_password_confirm: "" });
  const set = (key) => (event) => { const value = event.target.value; setForm((old) => ({ ...old, [key]: value, ...(key === "organization_name" ? { organization_slug: businessId(value) } : {}) })); };

  useEffect(() => {
    const value = form.organization_slug;
    if (!value || value.length < 2) { setSlugState({ status: "idle", message: value ? "Use at least 2 characters" : "", suggestions: [] }); return undefined; }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) { setSlugState({ status: "invalid", message: "Use lowercase letters, numbers, and single hyphens", suggestions: [] }); return undefined; }
    const controller = new AbortController(); setSlugState({ status: "checking", message: "Checking availability...", suggestions: [] });
    const timer = setTimeout(() => api.get("/auth/organization-id/availability", { params: { value }, signal: controller.signal }).then(({ data }) => setSlugState({ status: data.available ? "available" : "taken", message: data.message, suggestions: data.suggestions || [] })).catch((error) => { if (error.code !== "ERR_CANCELED") setSlugState({ status: "error", message: "Could not check right now. Try again.", suggestions: [] }); }), 350);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [form.organization_slug]);

  const detailsReady = Boolean(form.organization_name.trim() && form.location_name.trim() && slugState.status === "available");
  const passwordReady = isPasswordAcceptable(form.admin_password);
  const passwordsMatch = Boolean(form.admin_password_confirm && form.admin_password_confirm === form.admin_password);
  const submit = async (event) => {
    event.preventDefault(); if (!passwordReady) { toast.error("Please choose a stronger password"); return; } if (!passwordsMatch) { toast.error("Passwords do not match"); return; } setLoading(true);
    try {
      const payload = { ...form, admin_password_confirm: undefined };
      const result = await registerOrg(payload); const pending = { email: result.email, org_slug: result.organization_slug, email_sent: result.email_sent };
      sessionStorage.setItem("edvatiq.pending_verification", JSON.stringify(pending)); toast.success(result.email_sent ? "Verification code sent" : "Account created. Configure SMTP or resend the code"); navigate("/verify-email", { state: pending });
    } catch (error) {
      const detail = error.response?.data?.detail || "Could not create your business";
      if (detail === "Organization slug already exists") { setStep(2); setSlugState({ status: "taken", message: "Already used by another business", suggestions: [] }); toast.info("That Business ID was just taken. Choose another or sign in."); }
      else toast.error(detail);
    } finally { setLoading(false); }
  };

  return <div className="auth-shell bg-background soft-glow grid lg:grid-cols-[.8fr_1.2fr]">
    <aside className="auth-aside auth-register-aside hidden lg:flex bg-primary text-primary-foreground flex-col justify-between relative overflow-hidden"><div className="absolute inset-0 paper-grid opacity-10" /><Link to="/" className="relative font-display text-3xl font-bold">Edvatiq</Link><div className="relative"><div className="overline text-accent">Ready from day one</div><h1 className="auth-register-title font-display text-5xl xl:text-6xl font-bold mt-4 leading-[1.02]">Build your operating workspace.</h1><div className="auth-register-benefits space-y-3 mt-6 text-white/65">{["Confirm your email", "Invite staff with the right access", "See where you are signed in"].map((text) => <div className="flex gap-2" key={text}><CheckCircle className="text-accent shrink-0" />{text}</div>)}</div></div><div className="relative text-sm text-white/40">Built for growing teams / GST-ready / Multi-location</div></aside>
    <main className="auth-main"><div className="auth-register-inner w-full max-w-2xl mx-auto"><div className="auth-mobile-brand lg:hidden font-display text-3xl font-bold">Edvatiq</div><div className="flex gap-2 mb-5">{[1, 2, 3].map((item) => <div key={item} className={`h-1.5 flex-1 rounded-full ${item <= step ? "bg-accent" : "bg-secondary"}`} />)}</div>
      <form onSubmit={submit}>
        {step === 1 && <section><div className="overline">Step 1 of 3</div><h2 className="font-display text-3xl md:text-4xl font-bold mt-2">What kind of organization do you manage?</h2><div className="grid gap-3 mt-5 sm:grid-cols-2">{industries.map((item) => <button type="button" key={item.id} onClick={() => setForm({ ...form, industry: item.id })} className={`text-left border rounded-2xl p-4 ${form.industry === item.id ? "border-accent ring-2 ring-accent/15 bg-accent/5" : "bg-card"}`}><item.icon size={26} /><div className="font-semibold mt-3">{item.label}</div><div className="text-xs text-muted-foreground mt-1.5">{item.desc}</div></button>)}</div><Button type="button" className="w-full rounded-xl mt-5" onClick={() => setStep(2)}>Continue</Button></section>}
        {step === 2 && <section><div className="overline">Step 2 of 3</div><h2 className="font-display text-3xl md:text-4xl font-bold mt-2">Tell us about your business.</h2><div className="grid sm:grid-cols-2 gap-3 mt-5"><Field label="Business name"><Input required value={form.organization_name} onChange={set("organization_name")} /></Field><Field label="Business ID" hint="This becomes your permanent sign-in ID."><div className="relative"><Input required value={form.organization_slug} onChange={(event) => setForm((old) => ({ ...old, organization_slug: businessId(event.target.value) }))} aria-describedby="business-id-status" className={slugState.status === "available" ? "border-emerald-500 pr-10" : slugState.status === "taken" || slugState.status === "invalid" ? "border-red-400 pr-10" : "pr-10"} />{slugState.status === "checking" && <CircleNotch className="absolute right-3 top-2.5 animate-spin text-muted-foreground" />}{slugState.status === "available" && <CheckCircle weight="fill" className="absolute right-3 top-2.5 text-emerald-600" />}{["taken", "invalid", "error"].includes(slugState.status) && <XCircle weight="fill" className="absolute right-3 top-2.5 text-red-500" />}</div><div id="business-id-status" className={`text-xs mt-1.5 ${slugState.status === "available" ? "text-emerald-700" : ["taken", "invalid", "error"].includes(slugState.status) ? "text-red-600" : "text-muted-foreground"}`}>{slugState.message}</div>{slugState.suggestions?.length > 0 && <div className="flex flex-wrap gap-1.5 mt-2">{slugState.suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setForm((old) => ({ ...old, organization_slug: suggestion }))} className="text-[11px] border rounded-full px-2.5 py-1 hover:border-accent">{suggestion}</button>)}</div>}{slugState.status === "taken" && <Link to="/login" state={{ workspace: form.organization_slug }} className="inline-block text-xs font-semibold text-accent mt-2">Already yours? Sign in</Link>}</Field><Field label="First location"><Input required value={form.location_name} onChange={set("location_name")} /></Field><Field label="City"><Input value={form.city} onChange={set("city")} /></Field></div><Nav back={() => setStep(1)} next={() => detailsReady && setStep(3)} disabled={!detailsReady} /></section>}
        {step === 3 && <section><div className="overline">Step 3 of 3</div><h2 className="font-display text-3xl md:text-4xl font-bold mt-2">Create the business owner.</h2><div className="grid sm:grid-cols-2 gap-3 mt-5"><Field label="First name"><Input required value={form.admin_first_name} onChange={set("admin_first_name")} /></Field><Field label="Last name"><Input value={form.admin_last_name} onChange={set("admin_last_name")} /></Field><div className="sm:col-span-2"><Field label="Work email"><Input type="email" autoComplete="email" required value={form.admin_email} onChange={set("admin_email")} /></Field></div><div className="sm:col-span-2"><Field label="Password"><Input type="password" autoComplete="new-password" minLength={10} required value={form.admin_password} onChange={set("admin_password")} /><PasswordStrength password={form.admin_password} compact /></Field></div><div className="sm:col-span-2"><Field label="Confirm password"><Input type="password" autoComplete="new-password" minLength={10} required value={form.admin_password_confirm} onChange={set("admin_password_confirm")} />{form.admin_password_confirm && <p className={`text-xs mt-1 ${passwordsMatch ? "text-emerald-700" : "text-red-600"}`}>{passwordsMatch ? "Passwords match" : "Passwords do not match"}</p>}</Field></div></div><div className="flex gap-3 mt-5"><Button type="button" variant="outline" onClick={() => setStep(2)}>Back</Button><Button disabled={loading || !passwordReady || !passwordsMatch} className="flex-1">{loading ? "Creating..." : "Create business"}</Button></div></section>}
      </form><p className="text-sm text-muted-foreground mt-5 text-center">Already use Edvatiq? <Link to="/login" className="text-foreground font-medium">Sign in</Link></p>
    </div></main>
  </div>;
}

function Field({ label, hint, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</div>; }
function Nav({ back, next, disabled }) { return <div className="flex gap-3 mt-5"><Button type="button" variant="outline" onClick={back}>Back</Button><Button type="button" className="flex-1" disabled={disabled} onClick={next}>Continue</Button></div>; }
