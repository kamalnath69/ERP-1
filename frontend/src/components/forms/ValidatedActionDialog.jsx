import React, { useEffect, useRef } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage,
  FormRootError,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrors, FORM_OPTIONS } from "@/lib/validation";

function ActionField({ definition, control }) {
  return <FormField
    control={control}
    name={definition.name}
    render={({ field }) => <FormItem>
      <FormLabel>{definition.label}</FormLabel>
      <FormControl>
        {definition.type === "textarea" ? <Textarea
          {...field}
          value={field.value ?? ""}
          rows={definition.rows || 4}
          placeholder={definition.placeholder}
          maxLength={definition.maxLength}
        /> : definition.type === "select" ? <select
          {...field}
          value={field.value ?? ""}
          className="h-10 w-full rounded-lg border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/35"
        >
          {definition.placeholder && <option value="">{definition.placeholder}</option>}
          {(definition.options || []).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select> : <Input
          {...field}
          value={field.value ?? ""}
          type={definition.type || "text"}
          placeholder={definition.placeholder}
          autoComplete={definition.autoComplete}
          inputMode={definition.inputMode}
          maxLength={definition.maxLength}
          min={definition.min}
          max={definition.max}
          step={definition.step}
        />}
      </FormControl>
      {definition.description && <FormDescription>{definition.description}</FormDescription>}
      <FormMessage />
    </FormItem>}
  />;
}

/** A consistent, retry-safe dialog for privileged and destructive operations. */
export function ValidatedActionDialog({
  open,
  onOpenChange,
  title,
  description,
  impact,
  schema,
  defaultValues,
  fields = [],
  submitLabel = "Continue",
  loadingText = "Working...",
  variant = "default",
  onSubmit,
  resetKey,
}) {
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues,
    ...FORM_OPTIONS,
  });
  const defaultsRef = useRef(defaultValues);
  defaultsRef.current = defaultValues;
  const { clearErrors, control, formState, handleSubmit, reset, setError } = form;

  useEffect(() => {
    if (open) reset(defaultsRef.current);
  }, [open, reset, resetKey]);

  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await onSubmit(values);
      reset(defaultsRef.current);
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError);
      if (!Object.keys(normalized.fieldErrors).length && !normalized.formErrors.length) {
        setError("root.server", { type: "server", message: normalized.message });
      }
    }
  });

  const setOpen = (next) => {
    if (!next && formState.isSubmitting) return;
    onOpenChange(next);
  };

  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {description && <DialogDescription>{description}</DialogDescription>}
      </DialogHeader>
      {impact && <div className={`rounded-xl border px-3 py-2.5 text-sm ${variant === "destructive" ? "border-destructive/25 bg-destructive/5" : "bg-secondary/60"}`}>
        <span className="font-semibold">Impact: </span>{impact}
      </div>}
      <Form {...form}>
        <form className="space-y-4" noValidate onSubmit={submit}>
          {fields.map((definition) => <ActionField key={definition.name} definition={definition} control={control} />)}
          <FormRootError error={formState.errors.root?.server} />
          <DialogFooter className="gap-2 pt-2">
            <Button type="button" variant="outline" disabled={formState.isSubmitting} onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant={variant} loading={formState.isSubmitting} loadingText={loadingText}>{submitLabel}</Button>
          </DialogFooter>
        </form>
      </Form>
    </DialogContent>
  </Dialog>;
}
