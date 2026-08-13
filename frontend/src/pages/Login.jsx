import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useAuth } from "@/contexts/AuthContext";
import BrandLogo from "@/components/brand/BrandLogo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { applyApiErrors, firstApiError, FORM_OPTIONS, loginSchema } from "@/lib/validation";
import { LockKey, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Login() {
  const [needsMfa, setNeedsMfa] = useState(false);
  const [params] = useSearchParams();
  const location = useLocation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const form = useForm({ resolver: zodResolver(loginSchema(needsMfa)), defaultValues: { email: "", password: "", workspace: "", mfaCode: "" }, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, setError, setFocus, setValue } = form;
  useEffect(() => { if (params.get("expired")) toast.info("Your session expired. Please sign in again"); if (location.state?.email) setValue("email", location.state.email); if (location.state?.workspace) setValue("workspace", location.state.workspace); }, [location.state, params, setValue]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try { const user = await login(values.email, values.password, values.workspace || "", values.mfaCode || ""); navigate(user.is_super_admin ? "/super" : "/app"); }
    catch (error) {
      const detail = firstApiError(error, "Sign in failed");
      if (error.response?.status === 428) {
        setNeedsMfa(true);
        window.setTimeout(() => setFocus("mfaCode"), 0);
        toast.info("Enter the code from your authenticator app");
      } else if (detail === "Email is not verified") {
        sessionStorage.setItem("edvatiq.pending_verification", JSON.stringify({ email: values.email, org_slug: values.workspace || "" }));
        navigate("/verify-email", { state: { email: values.email, org_slug: values.workspace || "" } });
      } else {
        const normalized = applyApiErrors(error, setError, { aliases: { org_slug: "workspace", mfa_code: "mfaCode" }, fallback: "Sign in failed" });
        if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: detail });
      }
    }
  });
  return <AuthLayout eyebrow="Welcome back" title="Sign in to your business.">
    <Form {...form}><form noValidate onSubmit={submit} className="space-y-4 mt-6">
      <AuthField control={control} name="email" label="Work email"><Input type="email" autoComplete="email" /></AuthField>
      <AuthField control={control} name="password" label="Password" action={<Link to="/forgot-password" className="text-xs text-accent hover:underline">Forgot password?</Link>}><Input type="password" autoComplete="current-password" /></AuthField>
      <AuthField control={control} name="workspace" label="Business ID" hint="Only needed if this email is connected to more than one business."><Input placeholder="your-business" onChange={undefined} /></AuthField>
      {needsMfa && <AuthField control={control} name="mfaCode" label="Authenticator code" hint="Use a 6-digit authenticator code or one recovery code."><Input inputMode="numeric" autoComplete="one-time-code" /></AuthField>}
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" className="w-full rounded-xl h-11" loading={formState.isSubmitting} loadingText="Signing in...">Sign in</Button>
    </form></Form>
    <p className="text-sm text-center mt-5 text-muted-foreground">New to Edvatiq? <Link className="text-foreground font-medium" to="/register">Create your business</Link></p>
  </AuthLayout>;
}

export function AuthLayout({ eyebrow, title, children }) { return <div className="auth-shell auth-shell-login grid bg-background soft-glow"><aside className="auth-aside relative hidden flex-col justify-between overflow-hidden bg-primary text-primary-foreground xl:flex"><div className="absolute inset-0 paper-grid opacity-10" /><Link to="/" className="relative w-fit"><BrandLogo markClassName="h-11 w-11" nameClassName="font-display text-3xl text-primary-foreground" /></Link><div className="relative"><div className="auth-aside-icon grid h-14 w-14 place-items-center rounded-2xl bg-accent text-accent-foreground"><LockKey size={28} /></div><blockquote className="auth-aside-title mt-7 font-display text-5xl leading-tight">Your business memory deserves a secure front door.</blockquote><p className="auth-aside-copy mt-5 max-w-md text-white/60">Simple sign-in, verified accounts, and control over where you are signed in.</p></div><div className="relative flex items-center gap-2 text-sm text-white/40"><Sparkle />Edvatiq Business OS</div></aside><main className="auth-main"><div className="auth-main-inner"><div className="auth-card w-full max-w-md"><div className="auth-mobile-brand xl:hidden"><Link to="/" className="inline-flex"><BrandLogo markClassName="h-10 w-10" nameClassName="font-display text-2xl" /></Link></div><div className="overline">{eyebrow}</div><h1 className="auth-title mt-2 font-display text-3xl font-bold md:text-4xl">{title}</h1>{children}</div></div></main></div>; }
function AuthField({ control, name, label, action, hint, children }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><div className="flex items-center justify-between"><FormLabel>{label}</FormLabel>{action}</div><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "", onChange: (event) => field.onChange(name === "workspace" ? event.target.value.toLowerCase() : event) })}</FormControl>{hint && <FormDescription>{hint}</FormDescription>}<FormMessage /></FormItem>} />; }
