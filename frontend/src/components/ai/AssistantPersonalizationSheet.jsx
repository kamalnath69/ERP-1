import React, { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { FieldError, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { useSaveMyPreferenceMutation } from "@/store/api/workspaceApi";
import { applyApiErrors, assistantPreferencesSchema, FORM_OPTIONS } from "@/lib/validation";

export const ASSISTANT_DEFAULTS = Object.freeze({
  preferred_name: "",
  tone: "professional",
  detail: "concise",
  formatting: "auto",
  custom_instructions: "",
});

export function assistantPreferences(context) {
  return { ...ASSISTANT_DEFAULTS, ...(context?.preferences?.assistant?.value || {}) };
}

export default function AssistantPersonalizationSheet({ open, onOpenChange }) {
  const { user } = useAuth();
  const { context, refresh } = useBusiness();
  const saved = context?.preferences?.assistant;
  const [savePreference, saveState] = useSaveMyPreferenceMutation();
  const formApi = useForm({ resolver: zodResolver(assistantPreferencesSchema), defaultValues: ASSISTANT_DEFAULTS, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  const form = watch();

  useEffect(() => {
    if (open) reset(assistantPreferences(context));
  }, [context, open, reset]);

  const save = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await savePreference({
        namespace: "assistant",
        value: values,
        version: saved?.version,
      }).unwrap();
      await refresh();
      toast.success("Assistant preferences saved");
      onOpenChange(false);
    } catch (error) {
      if (error?.status === 409) {
        await refresh();
        setError("root.server", { type: "conflict", message: "These preferences changed on another device. Review the latest values and try again." });
        toast.error("These preferences changed on another device. Review the latest values and try again.");
      } else {
        const normalized = applyApiErrors(error, setError, { fallback: "Assistant preferences could not be saved" });
        toast.error(normalized.message);
      }
    }
  });

  const close = (next) => { if (!next && (formState.isSubmitting || saveState.isLoading)) return; onOpenChange(next); };

  return <Sheet open={open} onOpenChange={close}>
    <SheetContent className="premium-scrollbar flex w-full flex-col overflow-y-auto sm:max-w-lg">
      <SheetHeader className="text-left">
        <div className="mb-2 grid h-11 w-11 place-items-center rounded-2xl bg-primary text-primary-foreground">
          <Sparkle size={21} weight="fill" className="text-accent" />
        </div>
        <SheetTitle className="font-display text-3xl">Personalize Edvatiq</SheetTitle>
        <SheetDescription>
          Choose how your business assistant speaks to you. These settings are private to your account.
        </SheetDescription>
      </SheetHeader>

      <div className="flex-1 space-y-6 py-6">
        <div className="space-y-2">
          <Label htmlFor="assistant-preferred-name">What should Edvatiq call you?</Label>
          <Input
            id="assistant-preferred-name"
            maxLength={60}
            {...register("preferred_name")}
            aria-invalid={Boolean(formState.errors.preferred_name)}
            placeholder={user?.first_name || "Your preferred name"}
          />
          <FieldError error={formState.errors.preferred_name} />
          <p className="text-xs leading-5 text-muted-foreground">Leave this blank to use your profile first name.</p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <PreferenceSelect
            id="assistant-tone"
            label="Tone"
            value={form.tone}
            onChange={(value) => setValue("tone", value, { shouldDirty: true, shouldValidate: true })}
            options={[["professional", "Professional"], ["friendly", "Friendly"], ["direct", "Direct"]]}
          />
          <PreferenceSelect
            id="assistant-detail"
            label="Answer length"
            value={form.detail}
            onChange={(value) => setValue("detail", value, { shouldDirty: true, shouldValidate: true })}
            options={[["concise", "Concise"], ["balanced", "Balanced"], ["detailed", "Detailed"]]}
          />
        </div>

        <PreferenceSelect
          id="assistant-formatting"
          label="Preferred formatting"
          value={form.formatting}
          onChange={(value) => setValue("formatting", value, { shouldDirty: true, shouldValidate: true })}
          options={[["auto", "Choose automatically"], ["bullets", "Bullets and steps"], ["paragraphs", "Plain paragraphs"]]}
        />

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor="assistant-custom-instructions">Custom instructions</Label>
            <span className="text-[10px] tabular-nums text-muted-foreground">{form.custom_instructions.length}/1500</span>
          </div>
          <Textarea
            id="assistant-custom-instructions"
            rows={7}
            maxLength={1500}
            {...register("custom_instructions")}
            aria-invalid={Boolean(formState.errors.custom_instructions)}
            placeholder="For example: Avoid jargon. Start with the action I should take, then show supporting details."
          />
          <FieldError error={formState.errors.custom_instructions} />
          <p className="text-xs leading-5 text-muted-foreground">
            Instructions shape presentation only. Access rules, business facts, confirmations, and tool safety cannot be changed.
          </p>
        </div>

        <div className="rounded-2xl border bg-surface-subtle p-4 text-sm">
          <div className="font-semibold">Language follows each message</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            English, Tamil, and Tanglish are detected from your current message, regardless of the saved tone.
          </p>
        </div>
      </div>

      <FormRootError error={formState.errors.root?.server} />

      <SheetFooter className="sticky bottom-0 border-t bg-background py-4 sm:justify-between">
        <Button type="button" variant="ghost" onClick={() => reset(ASSISTANT_DEFAULTS)} disabled={saveState.isLoading || formState.isSubmitting}>
          Reset defaults
        </Button>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saveState.isLoading || formState.isSubmitting}>Cancel</Button>
          <Button type="button" onClick={save} disabled={!formState.isValid} loading={saveState.isLoading || formState.isSubmitting} loadingText="Saving preferences...">Save preferences</Button>
        </div>
      </SheetFooter>
    </SheetContent>
  </Sheet>;
}

function PreferenceSelect({ id, label, value, onChange, options }) {
  return <div className="space-y-2">
    <Label htmlFor={id}>{label}</Label>
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id}><SelectValue /></SelectTrigger>
      <SelectContent>
        {options.map(([option, text]) => <SelectItem key={option} value={option}>{text}</SelectItem>)}
      </SelectContent>
    </Select>
  </div>;
}
