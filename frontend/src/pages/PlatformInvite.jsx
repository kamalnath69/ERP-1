import React from "react";
import { useNavigate } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import api from "@/lib/api";
import { AuthLayout } from "@/pages/Login";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import PasswordStrength from "@/components/PasswordStrength";
import { applyApiErrors, FORM_OPTIONS, platformInviteSchema } from "@/lib/validation";

export default function PlatformInvite() {
  const { refreshMe } = useAuth(); const navigate = useNavigate();
  const form = useForm({ resolver: zodResolver(platformInviteSchema), defaultValues: { email: "", code: "", password: "", confirm: "" }, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, setError, watch } = form; const passwordValue = watch("password"); const confirmation = watch("confirm");
  const submit = handleSubmit(async (values) => { clearErrors("root.server"); try { await api.post("/auth/platform-invite/accept", { email: values.email, code: values.code, new_password: values.password }); await refreshMe(); navigate("/super"); } catch (error) { const normalized = applyApiErrors(error, setError, { aliases: { new_password: "password" }, fallback: "Invitation could not be accepted" }); if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message }); } });
  return <AuthLayout eyebrow="Platform team" title="Activate your account."><Form {...form}><form noValidate className="space-y-4 mt-6" onSubmit={submit}><InviteField control={control} name="email" label="Work email"><Input type="email" autoComplete="email" /></InviteField><InviteField control={control} name="code" label="Invitation code"><Input inputMode="numeric" autoComplete="one-time-code" maxLength={200} /></InviteField><InviteField control={control} name="password" label="Create password"><Input type="password" autoComplete="new-password" maxLength={128} /></InviteField><PasswordStrength password={passwordValue || ""} compact /><InviteField control={control} name="confirm" label="Confirm password"><Input type="password" autoComplete="new-password" maxLength={128} /></InviteField>{confirmation && <p className={`text-xs ${confirmation === passwordValue ? "text-emerald-700" : "text-red-600"}`}>{confirmation === passwordValue ? "Passwords match" : "Passwords do not match"}</p>}<FormRootError error={formState.errors.root?.server} /><Button type="submit" className="w-full" loading={formState.isSubmitting} loadingText="Activating...">Activate account</Button></form></Form></AuthLayout>;
}

function InviteField({ control, name, label, children }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "", onChange: (event) => field.onChange(name === "code" ? event.target.value.replace(/\s/g, "") : event) })}</FormControl><FormMessage /></FormItem>} />; }
