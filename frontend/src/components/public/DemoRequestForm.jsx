import React, { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { CirclesFour, Code, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";

import { usePublicSite } from "@/components/public/PublicSiteLayout";
import { Button } from "@/components/ui/button";
import { FieldError, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import api from "@/lib/api";
import { applyApiErrors } from "@/lib/validation";

const enquirySchema = z.object({
  inquiry_type: z.enum(["product_demo", "client_project"]),
  name: z.string().trim().min(2, "Enter your name").max(160),
  work_email: z.string().trim().email("Enter a valid email").max(255),
  organization_name: z.string().trim().max(200).optional(),
  industry: z.enum(["gym", "salon", "clinic", "college", "other"]),
  role: z.string().trim().max(120).optional(),
  phone: z.string().trim().max(40).refine(
    (value) => !value || (/^[+\d()\-.\s]+$/.test(value) && value.replace(/\D/g, "").length >= 7),
    "Enter a valid phone number",
  ),
  message: z.string().trim().max(3000).optional(),
  website: z.string().max(200).optional(),
}).superRefine((values, context) => {
  if (values.inquiry_type === "product_demo" && !values.organization_name?.trim()) {
    context.addIssue({ code: "custom", path: ["organization_name"], message: "Enter your organization" });
  }
});

const emptyValues = (inquiryType) => ({
  inquiry_type: inquiryType,
  name: "",
  work_email: "",
  organization_name: "",
  industry: inquiryType === "product_demo" ? "college" : "other",
  role: "",
  phone: "",
  message: "",
  website: "",
});

export default function DemoRequestForm({ className = "", heading = true }) {
  const { site, loading: siteLoading } = usePublicSite();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedType = searchParams.get("inquiry") === "client_project" ? "client_project" : "product_demo";
  const privacyId = site?.legal_documents?.privacy?.id;
  const {
    register, handleSubmit, reset, setError, setValue, watch, trigger, clearErrors,
    formState: { errors, isSubmitting, isValid, touchedFields, submitCount },
  } = useForm({
    resolver: zodResolver(enquirySchema),
    mode: "onChange",
    reValidateMode: "onChange",
    defaultValues: emptyValues(requestedType),
  });
  const inquiryType = watch("inquiry_type");
  const project = inquiryType === "client_project";
  const organizationError = touchedFields.organization_name || submitCount > 0
    ? errors.organization_name
    : undefined;

  useEffect(() => {
    setValue("inquiry_type", requestedType, { shouldDirty: false, shouldValidate: false });
    clearErrors("organization_name");
  }, [requestedType, setValue, clearErrors]);

  const chooseType = (value) => {
    setValue("inquiry_type", value, { shouldDirty: true, shouldValidate: true });
    if (value === "client_project") setValue("industry", "other", { shouldDirty: false });
    clearErrors("organization_name");
    trigger("organization_name");
    const next = new URLSearchParams(searchParams);
    if (value === "client_project") next.set("inquiry", "client_project");
    else next.delete("inquiry");
    setSearchParams(next, { replace: true });
  };

  const submit = async (values) => {
    if (!privacyId) {
      setError("root.server", { message: "Online enquiries are temporarily unavailable. Email our team instead." });
      return;
    }
    try {
      await api.post("/public/demo-requests", {
        ...values,
        organization_name: values.organization_name?.trim() || null,
        privacy_document_id: privacyId,
        privacy_acknowledged: true,
      });
      reset(emptyValues(values.inquiry_type));
      toast.success(values.inquiry_type === "client_project" ? "Your project enquiry was received" : "Your demo request was received");
    } catch (error) {
      applyApiErrors(error, setError, { fallback: "Could not send your enquiry" });
    }
  };

  return <form onSubmit={handleSubmit(submit)} noValidate className={`rounded-[1.5rem] border bg-card p-5 text-foreground shadow-xl shadow-black/5 sm:p-7 ${className}`}>
    {heading && <div className="mb-6 border-b pb-5">
      <div className="overline">Choose a conversation</div>
      <h3 className="mt-2 text-2xl font-semibold">{project ? "Tell us what you want to build." : "See Edvatiq around your real work."}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{project ? "Share the workflow, users, and outcome you have in mind. A finished specification is not required." : "A little context helps us prepare the right workspace, permissions, and rollout discussion."}</p>
    </div>}
    <fieldset className="mb-6 grid gap-2 sm:grid-cols-2">
      <legend className="sr-only">Enquiry type</legend>
      <EnquiryChoice active={!project} icon={CirclesFour} title="Edvatiq product demo" copy="Explore the platform for your organization." onClick={() => chooseType("product_demo")} />
      <EnquiryChoice active={project} icon={Code} title="Custom software project" copy="Discuss a focused system or integration." onClick={() => chooseType("client_project")} />
      <input type="hidden" {...register("inquiry_type")} />
    </fieldset>
    <FormRootError error={errors.root?.server} className="mb-5" />
    {!siteLoading && !privacyId && <div className="mb-5 rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm leading-6 text-muted-foreground">Online enquiries are temporarily unavailable. Please email our team and we can still help.</div>}
    <div className="grid gap-5 sm:grid-cols-2">
      <ContactField required label="Name" id="enquiry-name" error={errors.name}><Input id="enquiry-name" autoComplete="name" {...register("name")} /></ContactField>
      <ContactField required label={project ? "Email" : "Work email"} id="enquiry-email" error={errors.work_email}><Input id="enquiry-email" type="email" autoComplete="email" {...register("work_email")} /></ContactField>
      <ContactField required={!project} label={project ? "Organization or venture (optional)" : "Organization"} id="enquiry-org" error={organizationError}><Input id="enquiry-org" autoComplete="organization" {...register("organization_name")} /></ContactField>
      <ContactField required label="Industry" id="enquiry-industry" error={errors.industry}><select id="enquiry-industry" {...register("industry")} className="flex h-11 w-full rounded-lg border border-input bg-background px-3 text-sm"><option value="college">College</option><option value="gym">Gym and fitness</option><option value="salon">Salon and spa</option><option value="clinic">Clinic</option><option value="other">Other</option></select></ContactField>
      <ContactField label="Your role" id="enquiry-role" error={errors.role}><Input id="enquiry-role" autoComplete="organization-title" {...register("role")} /></ContactField>
      <ContactField label="Phone" id="enquiry-phone" error={errors.phone}><Input id="enquiry-phone" type="tel" autoComplete="tel" {...register("phone")} /></ContactField>
      <div className="sm:col-span-2"><ContactField label={project ? "What do you want to build?" : "What should we prepare for?"} id="enquiry-message" error={errors.message}><Textarea id="enquiry-message" rows={4} {...register("message")} placeholder={project ? "Describe the workflow, users, current problem, or system you want to connect." : "Tell us about the workflow, team, or integration you want to discuss."} /></ContactField></div>
    </div>
    <input tabIndex={-1} autoComplete="off" aria-hidden="true" className="absolute -left-[10000px]" {...register("website")} />
    <div className="mt-6 flex flex-col gap-4 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
      <p className="max-w-md text-xs leading-5 text-muted-foreground">Submitting acknowledges our <Link to="/privacy" className="font-medium text-foreground underline underline-offset-2">Privacy Policy</Link>. This is not marketing consent.</p>
      <Button type="submit" loading={isSubmitting} loadingText="Sending..." disabled={isSubmitting || !isValid || !privacyId} className="w-full shrink-0 sm:w-auto"><Sparkle className="mr-1.5" />{project ? "Send project enquiry" : "Request a demo"}</Button>
    </div>
  </form>;
}

function EnquiryChoice({ active, icon: Icon, title, copy, onClick }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={`flex min-h-24 items-start gap-3 rounded-xl border p-3.5 text-left transition-[border-color,background-color,box-shadow] ${active ? "border-primary/35 bg-primary/[0.045] shadow-sm" : "bg-background hover:border-primary/20"}`}><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${active ? "bg-primary text-primary-foreground" : "bg-secondary text-primary"}`}><Icon size={18} /></span><span><strong className="block text-sm">{title}</strong><span className="mt-1 block text-[11px] leading-4 text-muted-foreground">{copy}</span></span></button>;
}

function ContactField({ label, id, error, required = false, children }) {
  const errorId = `${id}-error`;
  return <div className="space-y-2">
    <Label htmlFor={id}>{label}{required && <span className="ml-1 text-accent" aria-hidden="true">*</span>}</Label>
    {React.cloneElement(children, { "aria-invalid": Boolean(error), "aria-describedby": error ? errorId : undefined, required })}
    <FieldError id={errorId} error={error} />
  </div>;
}
