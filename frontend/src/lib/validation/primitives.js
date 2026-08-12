import { z } from "zod";

const ordinaryText = (value) => typeof value === "string" ? value.trim() : value;
const blankToNull = (value) => {
  if (typeof value !== "string") return value;
  const normalized = value.trim();
  return normalized === "" ? null : normalized;
};

export const requiredText = (label = "This field", { min = 1, max = 5000 } = {}) => z.preprocess(
  ordinaryText,
  z.string().min(min, `${label} is required`).max(max, `${label} must be ${max} characters or fewer`),
);

export const optionalText = ({ max = 5000 } = {}) => z.preprocess(
  blankToNull,
  z.string().max(max, `Use ${max} characters or fewer`).nullable().optional(),
);

export const email = ({ optional = false } = {}) => {
  const schema = z.string().email("Enter a valid email address").max(254, "Email address is too long");
  return z.preprocess(optional ? blankToNull : ordinaryText, optional ? schema.nullable().optional() : schema);
};

export const phone = ({ optional = true } = {}) => {
  const schema = z.string().max(40, "Phone number is too long").refine((value) => {
    const digits = value.replace(/\D/g, "");
    return digits.length >= 7 && digits.length <= 15 && /^[+\d()\-\s.]+$/.test(value);
  }, "Enter a valid phone number");
  return z.preprocess(optional ? blankToNull : ordinaryText, optional ? schema.nullable().optional() : schema);
};

export const password = (label = "Password") => z.string()
  .min(10, `${label} must be at least 10 characters`)
  .max(128, `${label} must be 128 characters or fewer`)
  .refine((value) => /[a-z]/.test(value), `${label} must include a lowercase letter`)
  .refine((value) => /[A-Z]/.test(value), `${label} must include an uppercase letter`)
  .refine((value) => /\d/.test(value), `${label} must include a number`);

export const workspaceSlug = z.preprocess(
  ordinaryText,
  z.string()
    .min(2, "Business ID is required")
    .max(80, "Business ID must be 80 characters or fewer")
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use lowercase letters, numbers, and single hyphens"),
);

export const code = (label = "Code", { min = 1, max = 120 } = {}) => z.preprocess(
  ordinaryText,
  z.string().min(min, `${label} is required`).max(max, `${label} is too long`).regex(/^[A-Za-z0-9._/-]+$/, `${label} contains unsupported characters`),
);

export const gstin = z.preprocess(
  blankToNull,
  z.string().toUpperCase().regex(/^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]$/, "Enter a valid 15-character GSTIN").nullable().optional(),
);

export const webUrl = ({ optional = true } = {}) => {
  const schema = z.string().url("Enter a complete URL including https://").max(500, "URL is too long");
  return z.preprocess(optional ? blankToNull : ordinaryText, optional ? schema.nullable().optional() : schema);
};

function decimalValue(value) {
  if (typeof value === "number") return value;
  if (typeof value !== "string") return Number.NaN;
  const normalized = value.trim().replaceAll(",", "");
  if (!normalized || !/^-?\d+(?:\.\d+)?$/.test(normalized)) return Number.NaN;
  return Number(normalized);
}

export const numberInput = ({
  label = "Value", min, max, integer = false, optional = false, positive = false,
} = {}) => z.preprocess((value) => {
  if (optional && (value === "" || value == null)) return null;
  return decimalValue(value);
}, z.number({ error: `${label} must be a number` })
  .finite(`${label} must be a finite number`)
  .refine((value) => !integer || Number.isInteger(value), `${label} must be a whole number`)
  .refine((value) => !positive || value > 0, `${label} must be greater than zero`)
  .refine((value) => min == null || value >= min, `${label} must be at least ${min}`)
  .refine((value) => max == null || value <= max, `${label} must be at most ${max}`)
  .nullable()
  .refine((value) => optional || value != null, `${label} is required`));

export const currencyInput = ({ label = "Amount", min = 0, max, optional = false, positive = false } = {}) => z.preprocess(
  (value) => optional && (value === "" || value == null) ? null : value,
  z.union([z.string(), z.number()]).nullable().transform((value, context) => {
    if (value == null) return null;
    const amount = decimalValue(value);
    if (!Number.isFinite(amount) || !/^\d+(?:\.\d{1,2})?$/.test(String(value).trim().replaceAll(",", ""))) {
      context.addIssue({ code: "custom", message: `${label} must use at most two decimal places` });
      return z.NEVER;
    }
    if (positive && amount <= 0) context.addIssue({ code: "custom", message: `${label} must be greater than zero` });
    if (min != null && amount < min) context.addIssue({ code: "custom", message: `${label} must be at least ${min}` });
    if (max != null && amount > max) context.addIssue({ code: "custom", message: `${label} must be at most ${max}` });
    return amount;
  }),
).refine((value) => optional || value != null, `${label} is required`);

export const dateInput = ({ label = "Date", optional = false } = {}) => z.preprocess(
  optional ? blankToNull : ordinaryText,
  (optional ? z.string().nullable().optional() : z.string().min(1, `${label} is required`)).refine(
    (value) => value == null || !Number.isNaN(Date.parse(value)),
    `${label} is invalid`,
  ),
);

export const timeInput = ({ label = "Time", optional = false } = {}) => z.preprocess(
  optional ? blankToNull : ordinaryText,
  (optional ? z.string().nullable().optional() : z.string().min(1, `${label} is required`)).refine(
    (value) => value == null || /^([01]\d|2[0-3]):[0-5]\d$/.test(value),
    `${label} is invalid`,
  ),
);

export const mfaCode = z.string().min(6, "Enter your authentication code").max(64, "Authentication code is too long");

export const idList = (label, { min = 0, max = 100 } = {}) => z.array(z.string().min(1))
  .min(min, min ? `Choose at least ${min} ${label}` : undefined)
  .max(max, `Choose no more than ${max} ${label}`)
  .refine((values) => new Set(values).size === values.length, `${label} contains duplicate selections`);

export function toPaise(amount) {
  if (amount == null) return null;
  return Math.round((Number(amount) + Number.EPSILON) * 100);
}

export function endAfterStart(schema, startKey = "starts_at", endKey = "ends_at", message = "End must be after start") {
  return schema.refine((value) => {
    if (!value?.[startKey] || !value?.[endKey]) return true;
    return new Date(value[endKey]).getTime() > new Date(value[startKey]).getTime();
  }, { path: [endKey], message });
}

export function matchesField(schema, source, target, message) {
  return schema.refine((value) => value?.[source] === value?.[target], { path: [target], message });
}

export function validateFile(file, {
  label = "File", maxBytes = 10 * 1024 * 1024, extensions = [], mimeTypes = [], optional = false,
} = {}) {
  if (!file) return optional ? null : `${label} is required`;
  if (!(file instanceof File) || file.size <= 0) return `${label} is empty`;
  if (file.size > maxBytes) return `${label} must be ${Math.round(maxBytes / 1024 / 1024)} MB or smaller`;
  const extension = file.name.includes(".") ? `.${file.name.split(".").pop().toLowerCase()}` : "";
  if (extensions.length && !extensions.map((item) => item.toLowerCase()).includes(extension)) return `${label} type is not supported`;
  if (mimeTypes.length && file.type && !mimeTypes.includes(file.type)) return `${label} type is not supported`;
  return null;
}

export { z };
