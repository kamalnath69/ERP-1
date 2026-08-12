import {
  currencyInput, email, gstin, idList, mfaCode, numberInput, optionalText, phone, requiredText,
  toPaise, workspaceSlug, z,
} from "../primitives";

export const identitySettingsSchema = z.object({
  name: requiredText("Business name", { min: 2, max: 200 }),
  legal_name: optionalText({ max: 200 }),
  gstin,
  timezone: requiredText("Timezone", { max: 80 }).refine((value) => {
    try { Intl.DateTimeFormat(undefined, { timeZone: value }); return true; } catch { return false; }
  }, "Enter a valid IANA timezone such as Asia/Kolkata"),
  contact_email: email({ optional: true }),
  contact_phone: phone(),
  invoice_prefix: requiredText("Invoice prefix", { min: 1, max: 20 }).pipe(z.string().regex(/^[A-Za-z0-9-]+$/, "Use letters, numbers, and hyphens only")),
  description: optionalText({ max: 5000 }),
});

export const taxSettingsSchema = z.object({
  prices_include_tax: z.boolean(),
  default_tax_rate_bps: numberInput({ label: "Default tax rate", min: 0, max: 10000, integer: true }),
});

export const industryRequestSchema = z.object({
  requested_industry: z.enum(["gym", "salon", "clinic", "college"]),
  reason: requiredText("Reason", { min: 20, max: 2000 }),
});

export const securitySettingsSchema = z.object({
  mfa_policy: z.enum(["optional", "privileged", "all"]),
});

export const roleSchema = z.object({
  name: requiredText("Role name", { min: 2, max: 120 }),
  description: optionalText({ max: 1000 }),
  permission_ids: z.array(z.string()).max(500, "Too many permissions selected"),
});

export const accessConfigurationSchema = z.object({
  role_ids: idList("role", { max: 100 }),
  permission_overrides: z.array(z.object({
    permission_id: requiredText("Permission"),
    granted: z.boolean(),
  })).max(1000, "Too many personal permission adjustments")
    .refine((rows) => new Set(rows.map((row) => row.permission_id)).size === rows.length, "A permission can be adjusted only once"),
  location_mode: z.enum(["full", "restricted"]),
  location_ids: idList("location", { max: 500 }),
  client_mode: z.enum(["all", "assigned", "selected"]),
  client_ids: idList("record", { max: 5000 }),
  version: numberInput({ label: "Access version", min: 1, integer: true, optional: true }),
}).superRefine((value, context) => {
  if (value.location_mode === "restricted" && !value.location_ids.length) context.addIssue({ code: "custom", path: ["location_ids"], message: "Choose at least one location" });
  if (value.client_mode === "selected" && !value.client_ids.length) context.addIssue({ code: "custom", path: ["client_ids"], message: "Choose at least one record" });
});

export const conversationRenameSchema = z.object({
  title: requiredText("Conversation title", { min: 1, max: 120 }),
});

export const assistantPreferenceSchema = z.object({
  preferred_name: optionalText({ max: 80 }),
  tone: z.enum(["professional", "friendly", "direct"]),
  detail: z.enum(["concise", "balanced", "detailed"]),
  formatting: z.enum(["auto", "bullets", "paragraphs"]),
  custom_instructions: optionalText({ max: 1500 }),
});

export const planAssignmentSchema = z.object({
  plan_version_id: requiredText("Plan version"),
  billing_interval: z.enum(["monthly", "annual"]),
  change_timing: z.enum(["immediate", "cycle_end"]),
  reason: requiredText("Business reason", { min: 5, max: 500 }),
});

export const featureOverrideSchema = z.object({
  feature_code: requiredText("Feature or limit"),
  value: z.union([z.boolean(), z.number(), z.null()]),
  reason: requiredText("Reason", { min: 8, max: 1000 }),
});

export const refundSchema = z.object({
  amount: currencyInput({ label: "Refund amount", positive: true }),
  reason: requiredText("Refund reason", { min: 8, max: 1000 }),
  mfa_code: mfaCode,
}).transform((value) => ({ ...value, amount_paise: toPaise(value.amount) }));

export const walletRechargeSchema = z.object({
  credits: numberInput({ label: "AI credits", min: 1, max: 10_000_000, integer: true }),
  reason: requiredText("Recharge reason", { min: 5, max: 500 }),
  mfa_code: mfaCode,
});

export const platformTeamSchema = z.object({
  email: email(),
  first_name: requiredText("First name", { min: 1, max: 120 }),
  last_name: optionalText({ max: 120 }),
  role_id: requiredText("Platform role"),
});

export const ownerTransferSchema = z.object({
  new_owner_user_id: requiredText("New owner"),
  reason: requiredText("Transfer reason", { min: 8, max: 1000 }),
  mfa_code: mfaCode,
  confirmation: workspaceSlug,
});

export const organizationDeletionSchema = z.object({
  reason: requiredText("Deletion reason", { min: 12, max: 2000 }),
  mfa_code: mfaCode,
  confirmation: workspaceSlug,
});

export const approvalDecisionSchema = z.object({
  note: optionalText({ max: 1000 }),
  mfa_code: z.string().max(64).optional(),
});

export const supportSessionSchema = z.object({
  organization_id: requiredText("Organization"),
  target_user_id: requiredText("Target user"),
  reason: requiredText("Support reason", { min: 8, max: 1000 }),
  ticket_reference: requiredText("Ticket reference", { min: 3, max: 120 }),
  mode: z.enum(["read_only", "limited_write"]),
});

export const rechargePackSchema = z.object({
  name: requiredText("Pack name", { min: 2, max: 100 }),
  credits: numberInput({ label: "Credits", min: 1, max: 10_000_000, integer: true }),
  price: currencyInput({ label: "Price", positive: true }),
  tax_enabled: z.boolean(),
  gst_rate: numberInput({ label: "GST rate", min: 0, max: 100 }),
  is_active: z.boolean(),
  display_order: numberInput({ label: "Display order", min: 0, integer: true }),
}).transform((value) => ({
  ...value,
  price_paise: toPaise(value.price),
  gst_rate_bps: Math.round(value.gst_rate * 100),
}));
