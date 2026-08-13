import {
  code, currencyInput, dateInput, email, endAfterStart, gstin, idList, numberInput,
  optionalText, password, phone, requiredText, timeInput, toPaise, z,
} from "../primitives";

export const locationSchema = z.object({
  name: requiredText("Location name", { min: 2, max: 200 }),
  code: code("Location code", { min: 1, max: 40 }),
  address: optionalText({ max: 500 }),
  city: optionalText({ max: 120 }),
  state: optionalText({ max: 100 }),
  postal_code: optionalText({ max: 20 }),
  phone: phone(),
  gstin,
  is_primary: z.boolean().default(false),
});

export const clientSchema = z.object({
  first_name: requiredText("First name", { min: 1, max: 100 }),
  last_name: optionalText({ max: 100 }),
  email: email({ optional: true }),
  phone: phone(),
  address: optionalText({ max: 1000 }),
  date_of_birth: dateInput({ label: "Date of birth", optional: true }),
  gender: optionalText({ max: 30 }),
  home_location_id: optionalText({ max: 80 }),
  notes: optionalText({ max: 5000 }),
  tags: z.preprocess((value) => typeof value === "string" ? value.split(",").map((item) => item.trim()).filter(Boolean) : value, z.array(requiredText("Tag", { max: 80 })).max(100, "Use no more than 100 tags")).default([]),
  whatsapp_consent: z.boolean().default(false),
  email_consent: z.boolean().default(false),
}).superRefine((value, context) => {
  if (value.whatsapp_consent && !value.phone) context.addIssue({ code: "custom", path: ["phone"], message: "Phone is required for WhatsApp consent" });
});

export const clientProfileEditSchema = z.object({
  first_name: requiredText("First name", { min: 1, max: 100 }),
  last_name: z.string().trim().max(100, "Last name is too long"),
  email: email({ optional: true }),
  phone: phone(),
  address: optionalText({ max: 1000 }),
  notes: optionalText({ max: 5000 }),
  status: z.enum(["active", "inactive", "blocked"]),
  whatsapp_consent: z.boolean().default(false),
  email_consent: z.boolean().default(false),
  version: numberInput({ label: "Profile version", min: 1, integer: true }),
}).superRefine((value, context) => {
  if (value.whatsapp_consent && !value.phone) context.addIssue({ code: "custom", path: ["phone"], message: "Phone is required for WhatsApp consent" });
});

export const clientMemorySchema = z.object({
  category: z.enum(["preference", "goal", "language", "concern", "service_preference", "communication"]),
  label: requiredText("Short label", { min: 2, max: 160 }),
  value: requiredText("Team note", { min: 2, max: 5000 }),
  visibility: z.enum(["team", "managers", "assigned_staff", "author_only", "clinical"]),
});

export const clientCommitmentSchema = z.object({
  title: requiredText("Follow-up", { min: 2, max: 240 }),
  description: optionalText({ max: 5000 }),
  due_at: dateInput({ label: "Due date", optional: true }),
});

export const clientMeasurementSchema = z.object({
  measured_on: dateInput({ label: "Measurement date" }),
  weight_kg: numberInput({ label: "Weight", min: 0, max: 1000, optional: true }),
  height_cm: numberInput({ label: "Height", min: 0, max: 400, optional: true }),
  body_fat_percent: numberInput({ label: "Body fat", min: 0, max: 100, optional: true }),
  waist_cm: numberInput({ label: "Waist", min: 0, max: 500, optional: true }),
  notes: optionalText({ max: 5000 }),
}).refine((value) => [value.weight_kg, value.height_cm, value.body_fat_percent, value.waist_cm].some((item) => item != null), {
  path: ["weight_kg"], message: "Enter at least one measurement",
});

export const profileFreezeSchema = z.object({
  frozen_from: dateInput({ label: "Freeze start" }),
  frozen_until: dateInput({ label: "Freeze end" }),
}).refine((value) => new Date(value.frozen_until) >= new Date(value.frozen_from), {
  path: ["frozen_until"], message: "Freeze end must be on or after the start date",
});

export const studentAdmissionSchema = z.object({
  first_name: requiredText("First name", { min: 1, max: 100 }),
  last_name: optionalText({ max: 100 }),
  email: email({ optional: true }),
  phone: phone(),
  admission_number: code("Admission number", { min: 2, max: 40 }),
  roll_number: optionalText({ max: 60 }),
  program_id: requiredText("Program"),
  cohort_id: requiredText("Cohort"),
  current_semester: numberInput({ label: "Current semester", min: 1, max: 16, integer: true }),
  admitted_on: dateInput({ label: "Admission date" }),
  home_location_id: optionalText({ max: 80 }),
});

export const collegeDepartmentSchema = z.object({
  name: requiredText("Department name", { min: 2, max: 180 }),
  code: code("Department code", { min: 2, max: 30 }),
  description: optionalText({ max: 1000 }),
});

export const collegeProgramSchema = z.object({
  department_id: requiredText("Department"),
  name: requiredText("Program name", { min: 2, max: 200 }),
  code: code("Program code", { min: 2, max: 40 }),
  degree_type: z.enum(["undergraduate", "postgraduate", "diploma", "certificate"]),
  duration_semesters: numberInput({ label: "Program duration", min: 1, max: 16, integer: true }),
});

export const collegeCohortSchema = z.object({
  program_id: requiredText("Program"),
  name: requiredText("Batch name", { min: 2, max: 120 }),
  code: code("Batch code", { min: 2, max: 50 }),
  admission_year: numberInput({ label: "Admission year", min: 2000, max: 2200, integer: true }),
  graduation_year: numberInput({ label: "Graduation year", min: 2000, max: 2200, integer: true }),
  current_semester: numberInput({ label: "Current semester", min: 1, max: 16, integer: true }),
  section: optionalText({ max: 20 }),
}).refine((value) => value.graduation_year >= value.admission_year, {
  path: ["graduation_year"], message: "Graduation year cannot be before admission year",
});

export const collegeBulkCohortSchema = z.object({
  program_id: requiredText("Program"),
  admission_year: numberInput({ label: "Admission year", min: 2000, max: 2200, integer: true }),
  graduation_year: numberInput({ label: "Graduation year", min: 2000, max: 2200, integer: true }),
  current_semester: numberInput({ label: "Current semester", min: 1, max: 16, integer: true }),
  sections: requiredText("Sections", { max: 300 }).transform((value) => value
    .split(",").map((item) => item.trim().toUpperCase() || "GENERAL").filter(Boolean)),
  code_prefix: optionalText({ max: 36 }),
}).superRefine((value, context) => {
  if (value.graduation_year < value.admission_year) context.addIssue({ code: "custom", path: ["graduation_year"], message: "Graduation year cannot be before admission year" });
  if (!value.sections.length) context.addIssue({ code: "custom", path: ["sections"], message: "Enter at least one section" });
  if (value.sections.some((section) => section.length > 20)) context.addIssue({ code: "custom", path: ["sections"], message: "Each section must be 20 characters or fewer" });
  if (new Set(value.sections).size !== value.sections.length) context.addIssue({ code: "custom", path: ["sections"], message: "Each section can appear only once" });
});

export const collegeTermSchema = z.object({
  name: requiredText("Term name", { min: 2, max: 80 }),
  academic_year: requiredText("Academic year", { min: 4, max: 20 }),
  term_number: numberInput({ label: "Term number", min: 1, max: 16, integer: true }),
  starts_on: dateInput({ label: "Start date" }),
  ends_on: dateInput({ label: "End date" }),
  status: z.enum(["planned", "active", "closed"]),
  is_current: z.boolean().default(false),
}).refine((value) => value.ends_on > value.starts_on, {
  path: ["ends_on"], message: "End date must be after start date",
});

export const collegeCourseSchema = z.object({
  department_id: requiredText("Department"),
  name: requiredText("Course name", { min: 2, max: 200 }),
  code: code("Course code", { min: 2, max: 40 }),
  credits: numberInput({ label: "Credits", min: 0, max: 30, integer: true }),
  course_type: z.enum(["core", "elective", "lab", "project", "audit"]),
});

export const collegeOfferingSchema = z.object({
  term_id: requiredText("Term"),
  course_id: requiredText("Course"),
  cohort_id: requiredText("Batch"),
  room: optionalText({ max: 60 }),
});

export const academicLifecycleSchema = z.object({
  reason: requiredText("Reason", { min: 3, max: 500 }),
});

export const employeeSchema = z.object({
  employee_number: optionalText({ max: 50 }),
  first_name: requiredText("First name", { min: 1, max: 100 }),
  last_name: optionalText({ max: 100 }),
  email: email({ optional: true }),
  phone: phone(),
  designation: optionalText({ max: 120 }),
  salary: currencyInput({ label: "Monthly salary", optional: true }),
  joining_date: dateInput({ label: "Joining date", optional: true }),
  location_ids: idList("location", { min: 1 }),
  create_login: z.boolean().default(false),
  password: z.string().optional(),
  role_ids: z.array(z.string()).default([]),
}).superRefine((value, context) => {
  if (!value.create_login) return;
  const passwordResult = password("Temporary password").safeParse(value.password || "");
  if (!passwordResult.success) context.addIssue({ code: "custom", path: ["password"], message: passwordResult.error.issues[0].message });
  if (!value.email) context.addIssue({ code: "custom", path: ["email"], message: "Email is required for login access" });
  if (!value.role_ids.length) context.addIssue({ code: "custom", path: ["role_ids"], message: "Choose at least one starting role" });
}).transform((value) => ({ ...value, salary_paise: toPaise(value.salary) }));

export const employeeProfileSchema = z.object({
  first_name: requiredText("First name", { min: 1, max: 100 }),
  last_name: z.string().trim().max(100, "Last name is too long"),
  email: email({ optional: true }),
  phone: phone(),
  designation: optionalText({ max: 120 }),
  specialties: z.array(requiredText("Specialty", { max: 120 })).max(50, "Use no more than 50 specialties").default([]),
  salary: currencyInput({ label: "Monthly salary", min: 0, optional: true }),
  joining_date: dateInput({ label: "Joining date", optional: true }),
  status: z.enum(["active", "on_leave", "inactive"]),
  location_ids: idList("location", { min: 1 }),
  version: numberInput({ label: "Employee version", min: 1, integer: true }),
}).transform((value) => ({ ...value, salary_paise: toPaise(value.salary) }));

export const catalogItemSchema = z.object({
  name: requiredText("Item name", { min: 2, max: 180 }),
  sku: code("SKU", { min: 1, max: 80 }),
  item_type: z.enum(["product", "service", "medicine", "lab_test"]),
  category_id: optionalText({ max: 80 }),
  description: optionalText({ max: 5000 }),
  hsn_sac: optionalText({ max: 20 }),
  price: currencyInput({ label: "Selling price", min: 0 }),
  cost: currencyInput({ label: "Cost price", min: 0, optional: true }),
  tax_rate: numberInput({ label: "Tax rate", min: 0, max: 100, optional: true }),
  duration_minutes: numberInput({ label: "Duration", min: 1, max: 1440, integer: true, optional: true }),
  unit: requiredText("Unit", { max: 30 }),
  tax_inclusive: z.boolean().default(false),
  track_stock: z.boolean().default(true),
}).superRefine((value, context) => {
  if (value.item_type === "service" && value.duration_minutes == null) {
    context.addIssue({ code: "custom", path: ["duration_minutes"], message: "Duration is required for a service" });
  }
}).transform((value) => ({
  ...value,
  price_paise: toPaise(value.price),
  cost_paise: toPaise(value.cost || 0),
  tax_rate_bps: value.tax_rate == null ? 0 : Math.round(value.tax_rate * 100),
}));

export const catalogProfileSchema = z.object({
  name: requiredText("Item name", { min: 2, max: 180 }),
  item_type: z.enum(["product", "service", "medicine", "lab_test"]),
  description: optionalText({ max: 5000 }),
  hsn_sac: optionalText({ max: 20 }),
  price: currencyInput({ label: "Selling price", min: 0 }),
  cost: currencyInput({ label: "Cost price", min: 0, optional: true }),
  tax_rate: numberInput({ label: "GST rate", min: 0, max: 100, optional: true }),
  duration_minutes: numberInput({ label: "Duration", min: 1, max: 1440, integer: true, optional: true }),
  unit: requiredText("Unit", { max: 30 }),
  tax_inclusive: z.boolean(),
  track_stock: z.boolean(),
  is_active: z.boolean(),
  version: numberInput({ label: "Catalog version", min: 1, integer: true }),
}).superRefine((value, context) => {
  if (value.item_type === "service" && value.duration_minutes == null) {
    context.addIssue({ code: "custom", path: ["duration_minutes"], message: "Duration is required for a service" });
  }
}).transform((value) => ({
  ...value,
  price_paise: toPaise(value.price),
  cost_paise: toPaise(value.cost || 0),
  tax_rate_bps: value.tax_rate == null ? 0 : Math.round(value.tax_rate * 100),
}));

export const stockAdjustmentSchema = z.object({
  location_id: requiredText("Location"),
  item_id: requiredText("Item"),
  quantity: numberInput({ label: "Quantity", positive: true }),
  direction: z.enum(["add", "remove"]),
  reason: requiredText("Reason", { min: 3, max: 500 }),
  batch_number: optionalText({ max: 120 }),
  expires_on: dateInput({ label: "Expiry date", optional: true }),
  reorder_level: numberInput({ label: "Reorder level", min: 0, optional: true }),
}).transform((value) => ({
  ...value,
  quantity_delta_milli: Math.round(value.quantity * 1000) * (value.direction === "remove" ? -1 : 1),
  reorder_level_milli: value.reorder_level == null ? null : Math.round(value.reorder_level * 1000),
}));

export const stockTransferSchema = z.object({
  item_id: requiredText("Item"),
  source_location_id: requiredText("Source location"),
  destination_location_id: requiredText("Destination location"),
  quantity: numberInput({ label: "Quantity", positive: true }),
  batch_number: optionalText({ max: 120 }),
  reason: requiredText("Reason", { min: 3, max: 500 }),
}).refine((value) => value.source_location_id !== value.destination_location_id, {
  path: ["destination_location_id"], message: "Choose a different destination location",
}).transform((value) => ({ ...value, quantity_milli: Math.round(value.quantity * 1000) }));

export const appointmentSchema = endAfterStart(z.object({
  location_id: requiredText("Location"),
  client_id: requiredText("Client or student"),
  employee_id: optionalText({ max: 80 }),
  service_id: optionalText({ max: 80 }),
  starts_at: requiredText("Start time"),
  ends_at: requiredText("End time"),
  source: z.enum(["staff", "walk_in", "phone", "online", "ai"]).default("staff"),
  notes: optionalText({ max: 5000 }),
}), "starts_at", "ends_at", "End time must be after start time");

export const courseScheduleSchema = z.object({
  term_id: requiredText("Term"),
  course_id: requiredText("Course"),
  cohort_id: requiredText("Cohort"),
  faculty_employee_id: optionalText({ max: 80 }),
  weekday: numberInput({ label: "Weekday", min: 0, max: 6, integer: true }),
  room: optionalText({ max: 80 }),
  starts_at: timeInput({ label: "Start time" }),
  ends_at: timeInput({ label: "End time" }),
}).refine((value) => value.ends_at > value.starts_at, { path: ["ends_at"], message: "End time must be after start time" });
