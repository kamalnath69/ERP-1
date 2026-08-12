import { requiredText, z } from "../primitives";

export const aiPromptSchema = z.object({
  question: requiredText("Question", { min: 1, max: 5000 }),
});

export const feedbackReasonSchema = z.object({
  reason: z.string().trim().max(500, "Feedback must be 500 characters or fewer"),
});

export const assistantPreferencesSchema = z.object({
  preferred_name: z.string().trim().max(60, "Preferred name must be 60 characters or fewer"),
  tone: z.enum(["professional", "friendly", "direct"]),
  detail: z.enum(["concise", "balanced", "detailed"]),
  formatting: z.enum(["auto", "bullets", "paragraphs"]),
  custom_instructions: z.string().trim().max(1500, "Custom instructions must be 1,500 characters or fewer"),
});
