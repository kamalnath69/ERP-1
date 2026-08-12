import {
  email, matchesField, mfaCode, optionalText, password, phone, requiredText, workspaceSlug, z,
} from "../primitives";

const optionalWorkspace = z.preprocess(
  (value) => typeof value === "string" && !value.trim() ? null : value,
  workspaceSlug.nullable().optional(),
);

export const loginSchema = (requiresMfa = false) => z.object({
  email: email(),
  password: z.string().min(1, "Password is required").max(128, "Password is too long"),
  workspace: optionalWorkspace,
  mfaCode: requiresMfa ? mfaCode : z.string().max(64).optional(),
});

export const verifyEmailSchema = z.object({
  email: email(),
  orgSlug: optionalWorkspace,
  code: z.string().regex(/^\d{6}$/, "Enter the six-digit verification code"),
});

export const forgotPasswordRequestSchema = z.object({
  email: email(),
  org_slug: optionalWorkspace,
});

export const resetPasswordSchema = matchesField(z.object({
  email: email(),
  org_slug: optionalWorkspace,
  code: z.string().regex(/^\d{6}$/, "Enter the six-digit verification code"),
  new_password: password("New password"),
  confirm: z.string(),
}), "new_password", "confirm", "Passwords do not match");

export const platformInviteSchema = matchesField(z.object({
  email: email(),
  code: z.string().min(6, "Invitation code is required").max(200, "Invitation code is invalid"),
  password: password(),
  confirm: z.string(),
}), "password", "confirm", "Passwords do not match");

export const registrationSchema = matchesField(z.object({
  industry: z.enum(["gym", "salon", "clinic", "college"]),
  organization_name: requiredText("Organization name", { min: 2, max: 200 }),
  organization_slug: workspaceSlug,
  location_name: requiredText("Primary location", { min: 2, max: 200 }),
  city: optionalText({ max: 120 }),
  state: optionalText({ max: 100 }),
  admin_first_name: requiredText("First name", { min: 1, max: 120 }),
  admin_last_name: optionalText({ max: 120 }),
  admin_email: email(),
  admin_phone: phone(),
  admin_password: password(),
  admin_password_confirm: z.string().min(1, "Confirm your password"),
  plan: requiredText("Plan", { min: 2, max: 60 }),
  billing_interval: z.enum(["monthly", "annual"]),
}), "admin_password", "admin_password_confirm", "Passwords do not match");

export const myProfileSchema = z.object({
  first_name: requiredText("First name", { min: 1, max: 100 }),
  last_name: z.string().trim().max(100, "Last name is too long"),
  phone: z.string().trim().max(40, "Phone is too long").refine(
    (value) => !value || (/^[+\d()\-.\s]+$/.test(value) && value.replace(/\D/g, "").length >= 7 && value.replace(/\D/g, "").length <= 15),
    "Enter a valid phone number",
  ),
  designation: optionalText({ max: 200 }),
  bio: optionalText({ max: 5000 }),
  avatar_base64: z.union([
    z.null(),
    z.string().max(500_000, "Avatar is too large").regex(/^data:image\/(?:jpeg|png|webp);base64,/, "Choose a JPG, PNG, or WebP image"),
  ]),
});

export const passwordChangeSchema = matchesField(z.object({
  current_password: z.string().min(1, "Current password is required").max(128, "Current password is too long"),
  new_password: password("New password"),
  confirm: z.string().min(1, "Confirm your new password"),
}), "new_password", "confirm", "Passwords do not match");

export const mfaStartSchema = z.object({
  current_password: z.string().min(1, "Current password is required").max(128, "Current password is too long"),
});

export const mfaVerifySchema = z.object({
  code: z.string().regex(/^\d{6}$/, "Enter the six-digit authenticator code"),
});

export const mfaSensitiveSchema = z.object({
  current_password: z.string().min(1, "Current password is required").max(128, "Current password is too long"),
  code: z.string().min(6, "Enter an authenticator or recovery code").max(64, "Authentication code is too long"),
});
