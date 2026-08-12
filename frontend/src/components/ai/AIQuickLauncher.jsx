import React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/form";
import { PaperPlaneRight, Sparkle } from "@phosphor-icons/react";
import { aiPromptSchema, FORM_OPTIONS } from "@/lib/validation";

export default function AIQuickLauncher({ open, onOpenChange }) {
  const location = useLocation();
  const navigate = useNavigate();
  const form = useForm({ resolver: zodResolver(aiPromptSchema), defaultValues: { question: "" }, ...FORM_OPTIONS });
  const { formState, handleSubmit, register, reset } = form;
  const ask = handleSubmit(({ question }) => {
    const value = question.trim();
    const params = new URLSearchParams({ ask: value });
    const contexts = [
      ["client", /^\/app\/clients\/([^/]+)/],
      ["employee", /^\/app\/team\/([^/]+)/],
      ["catalog", /^\/app\/catalog\/([^/]+)/],
    ];
    const context = contexts
      .map(([kind, pattern]) => [kind, location.pathname.match(pattern)])
      .find(([, match]) => match);
    if (context) {
      params.set("context_kind", context[0]);
      params.set("context_id", context[1][1]);
    }
    onOpenChange(false);
    reset();
    navigate(`/app/ai?${params}`);
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl rounded-3xl">
        <DialogHeader>
          <div className="w-11 h-11 rounded-xl bg-primary text-primary-foreground grid place-items-center mb-3">
            <Sparkle weight="fill" />
          </div>
          <DialogTitle className="font-display text-3xl">
            Ask your business
          </DialogTitle>
          <DialogDescription>
            Get a live answer, find document knowledge, or complete a business
            task.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={ask} noValidate className="mt-4">
          <div className="flex gap-2 rounded-2xl bg-secondary p-2">
            <input autoFocus maxLength={5000} {...register("question")} aria-invalid={Boolean(formState.errors.question)} aria-describedby="quick-question-error" className="min-w-0 flex-1 bg-transparent px-3 text-sm outline-none" placeholder="What needs your attention today?" />
            <Button className="rounded-xl" aria-label="Ask Edvatiq"><PaperPlaneRight /></Button>
          </div>
          <FieldError id="quick-question-error" error={formState.errors.question} className="mt-2 px-2" />
        </form>
      </DialogContent>
    </Dialog>
  );
}
