import React from "react";
import { Link } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { toast } from "sonner";

import { usePublicSite } from "@/components/public/PublicSiteLayout";
import { Button } from "@/components/ui/button";
import { FieldError, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import api from "@/lib/api";
import { applyApiErrors } from "@/lib/validation";

const demoRequestSchema = z.object({
  name: z.string().trim().min(2, "Enter your name").max(160),
  work_email: z.string().trim().email("Enter a valid work email").max(255),
  organization_name: z.string().trim().min(2, "Enter your organization").max(200),
  industry: z.enum(["gym", "salon", "clinic", "college", "other"]),
  role: z.string().trim().max(120).optional(),
  phone: z.string().trim().max(40).refine(
    (value) => !value || (/^[+\d()\-.\s]+$/.test(value) && value.replace(/\D/g, "").length >= 7),
    "Enter a valid phone number",
  ),
  message: z.string().trim().max(3000).optional(),
  website: z.string().max(200).optional(),
});

export default function DemoRequestForm({ className = "", heading = true }) {
  const { site, loading: siteLoading } = usePublicSite();
  const privacyId = site?.legal_documents?.privacy?.id;
  const { register, handleSubmit, reset, setError, formState: { errors, isSubmitting, isValid } } = useForm({
    resolver: zodResolver(demoRequestSchema),
    mode: "onChange",
    reValidateMode: "onChange",
    defaultValues: {
      name: "",
      work_email: "",
      organization_name: "",
      industry: "college",
      role: "",
      phone: "",
      message: "",
      website: "",
    },
  });

  const submit = async (values) => {
    if (!privacyId) {
      setError("root.server", { message: "Demo requests are temporarily unavailable. Email our team instead." });
      return;
    }
    try {
      await api.post("/public/demo-requests", {
        ...values,
        privacy_document_id: privacyId,
        privacy_acknowledged: true,
      });
      reset();
      toast.success("Your demo request was received");
    } catch (error) {
      applyApiErrors(error, setError, { fallback: "Could not send your request" });
    }
  };

  return <form onSubmit={handleSubmit(submit)} noValidate className={`rounded-2xl border bg-card p-5 text-foreground shadow-xl shadow-black/5 sm:p-7 ${className}`}>
    {heading && <div className="mb-6 border-b pb-5">
      <div className="overline">Request details</div>
      <h2 className="mt-2 text-2xl font-semibold">Tell us about your organization.</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">A little context helps us prepare a relevant workspace and integration discussion.</p>
    </div>}
    <FormRootError error={errors.root?.server} className="mb-5" />
    {!siteLoading && !privacyId && <div className="mb-5 rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm leading-6 text-muted-foreground">Online requests are temporarily unavailable. Please email our team and we can still help.</div>}
    <div className="grid gap-5 sm:grid-cols-2">
      <ContactField required label="Name" id="demo-name" error={errors.name}><Input id="demo-name" autoComplete="name" {...register("name")} /></ContactField>
      <ContactField required label="Work email" id="demo-email" error={errors.work_email}><Input id="demo-email" type="email" autoComplete="email" {...register("work_email")} /></ContactField>
      <ContactField required label="Organization" id="demo-org" error={errors.organization_name}><Input id="demo-org" autoComplete="organization" {...register("organization_name")} /></ContactField>
      <ContactField required label="Industry" id="demo-industry" error={errors.industry}><select id="demo-industry" {...register("industry")} className="flex h-11 w-full rounded-lg border border-input bg-background px-3 text-sm"><option value="college">College</option><option value="gym">Gym and fitness</option><option value="salon">Salon and spa</option><option value="clinic">Clinic</option><option value="other">Other</option></select></ContactField>
      <ContactField label="Your role" id="demo-role" error={errors.role}><Input id="demo-role" {...register("role")} /></ContactField>
      <ContactField label="Phone" id="demo-phone" error={errors.phone}><Input id="demo-phone" type="tel" autoComplete="tel" {...register("phone")} /></ContactField>
      <div className="sm:col-span-2"><ContactField label="What should we prepare for?" id="demo-message" error={errors.message}><Textarea id="demo-message" rows={4} {...register("message")} placeholder="Tell us about the workflow, team, or integration you want to discuss." /></ContactField></div>
    </div>
    <input tabIndex={-1} autoComplete="off" aria-hidden="true" className="absolute -left-[10000px]" {...register("website")} />
    <div className="mt-6 flex flex-col gap-4 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
      <p className="max-w-md text-xs leading-5 text-muted-foreground">Submitting acknowledges our <Link to="/privacy" className="font-medium text-foreground underline underline-offset-2">Privacy Policy</Link>. This is not marketing consent.</p>
      <Button type="submit" loading={isSubmitting} loadingText="Sending..." disabled={isSubmitting || !isValid || !privacyId} className="w-full shrink-0 sm:w-auto">Request a demo</Button>
    </div>
  </form>;
}

function ContactField({ label, id, error, required = false, children }) {
  const errorId = `${id}-error`;
  return <div className="space-y-2">
    <Label htmlFor={id}>{label}{required && <span className="ml-1 text-accent" aria-hidden="true">*</span>}</Label>
    {React.cloneElement(children, { "aria-invalid": Boolean(error), "aria-describedby": error ? errorId : undefined, required })}
    <FieldError id={errorId} error={error} />
  </div>;
}
