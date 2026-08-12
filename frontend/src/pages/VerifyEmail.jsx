import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { AuthLayout } from "@/pages/Login";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { applyApiErrors, FORM_OPTIONS, verifyEmailSchema } from "@/lib/validation";
import { EnvelopeSimple, ShieldCheck } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function VerifyEmail() {
  const location = useLocation(); const navigate = useNavigate(); const { refreshMe } = useAuth();
  const saved = readPending(); const pending = location.state || saved || {};
  const [cooldown, setCooldown] = useState(0); const [deliveryFailed] = useState(pending.email_sent === false);
  const form = useForm({ resolver: zodResolver(verifyEmailSchema), defaultValues: { email: pending.email || "", orgSlug: pending.org_slug || "", code: "" }, ...FORM_OPTIONS });
  const { clearErrors, control, formState, getValues, handleSubmit, setError, trigger, watch } = form; const emailValue = watch("email");
  useEffect(() => { if (!cooldown) return undefined; const timer = setInterval(() => setCooldown((value) => Math.max(value - 1, 0)), 1000); return () => clearInterval(timer); }, [cooldown]);
  const verify = handleSubmit(async (values) => { clearErrors("root.server"); try { await api.post("/auth/email/verify", { email: values.email, org_slug: values.orgSlug || null, code: values.code }); sessionStorage.removeItem("edvatiq.pending_verification"); await refreshMe(); toast.success("Email verified"); navigate("/app"); } catch (error) { const normalized = applyApiErrors(error, setError, { aliases: { org_slug: "orgSlug" }, fallback: "Code could not be verified" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); } });
  const resend = async () => { if (cooldown || !(await trigger(["email", "orgSlug"]))) return; const values = getValues(); try { await api.post("/auth/email/request-code", { email: values.email, org_slug: values.orgSlug || null }); setCooldown(60); toast.info("If this account is awaiting verification, the email will arrive shortly"); } catch (error) { const normalized = applyApiErrors(error, setError, { aliases: { org_slug: "orgSlug" }, fallback: "Please wait before requesting another code" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); } };
  return <AuthLayout eyebrow="Verify ownership" title={deliveryFailed ? "Email delivery is delayed." : "Check your email."}><div className="w-12 h-12 rounded-2xl bg-accent/10 text-accent grid place-items-center mt-5"><EnvelopeSimple size={24} /></div><p className="text-sm text-muted-foreground mt-3">{deliveryFailed ? "We created your account, but your verification email could not be delivered. Try sending a new code shortly." : "Enter the six-digit code sent to your work email. It expires in 10 minutes and can be used once."}</p><Form {...form}><form noValidate onSubmit={verify} className="space-y-3 mt-5"><VerifyField control={control} name="email" label="Work email"><Input type="email" autoComplete="email" /></VerifyField><VerifyField control={control} name="orgSlug" label="Business ID"><Input autoComplete="organization" /></VerifyField><VerifyField control={control} name="code" label="Verification code"><Input inputMode="numeric" autoComplete="one-time-code" maxLength={6} className="text-center text-2xl tracking-[.45em] font-mono" /></VerifyField><FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full h-11" loading={formState.isSubmitting} loadingText="Verifying...">Verify and continue</Button></form></Form><Button type="button" variant="ghost" onClick={resend} disabled={!!cooldown || !emailValue} className="w-full text-sm mt-3">{cooldown ? `Resend available in ${cooldown}s` : "Send a new code"}</Button><div className="flex gap-2 text-xs text-muted-foreground mt-4"><ShieldCheck className="text-emerald-700 shrink-0" />Edvatiq never asks you to share this code by phone or chat.</div><p className="text-sm text-center mt-4"><Link to="/login" className="text-foreground font-medium">Back to sign in</Link></p></AuthLayout>;
}
function readPending() { try { return JSON.parse(sessionStorage.getItem("edvatiq.pending_verification")); } catch { return null; } }
function VerifyField({ control, name, label, children }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "", onChange: (event) => field.onChange(name === "code" ? event.target.value.replace(/\D/g, "") : name === "orgSlug" ? event.target.value.toLowerCase() : event) })}</FormControl><FormMessage /></FormItem>} />; }
