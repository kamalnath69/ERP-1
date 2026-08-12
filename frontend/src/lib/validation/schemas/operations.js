import {
  currencyInput, dateInput, email, endAfterStart, numberInput, optionalText, phone,
  requiredText, toPaise, validateFile, webUrl, z,
} from "../primitives";

export const documentUploadSchema = z.object({
  file: z.custom((value) => typeof File !== "undefined" && value instanceof File, "Choose a file"),
  visibility: z.enum(["team", "managers", "author_only"]),
}).superRefine((value, context) => {
  const message = validateFile(value.file, {
    label: "Document",
    maxBytes: 20 * 1024 * 1024,
    extensions: [".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png"],
    mimeTypes: [
      "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain", "image/jpeg", "image/png",
    ],
  });
  if (message) context.addIssue({ code: "custom", path: ["file"], message });
});

export const saleSchema = z.object({
  location_id: requiredText("Location"),
  client_id: optionalText({ max: 80 }),
  employee_id: optionalText({ max: 80 }),
  payment_method: z.enum(["cash", "card", "upi", "bank", "credit"]),
  paid: currencyInput({ label: "Amount paid", min: 0, optional: true }),
  discount: currencyInput({ label: "Invoice discount", min: 0, optional: true }),
  items: z.array(z.object({
    item_id: requiredText("Item"),
    quantity: numberInput({ label: "Quantity", positive: true }),
    discount: currencyInput({ label: "Line discount", min: 0, optional: true }),
  })).min(1, "Add at least one item"),
});

export const checkoutSchema = z.object({
  location_id: requiredText("Location"),
  client_id: optionalText({ max: 80 }),
  interstate: z.boolean().default(false),
  notes: optionalText({ max: 2000 }),
  lines: z.array(z.object({
    item_id: requiredText("Item"),
    quantity: numberInput({ label: "Quantity", positive: true }),
    discount: currencyInput({ label: "Line discount", min: 0, optional: true }),
  })).min(1, "Add at least one item").max(100, "An invoice can contain at most 100 items")
    .refine((lines) => new Set(lines.map((line) => line.item_id)).size === lines.length, "Each item can appear only once"),
}).transform((value) => ({
  ...value,
  lines: value.lines.map((line) => ({
    item_id: line.item_id,
    quantity_milli: Math.round(line.quantity * 1000),
    discount_paise: toPaise(line.discount || 0),
  })),
}));

export const invoicePaymentSchema = z.object({
  amount: currencyInput({ label: "Payment amount", positive: true }),
  method: z.enum(["cash", "card", "upi", "bank"]),
  reference: optionalText({ max: 160 }),
  version: numberInput({ label: "Invoice version", min: 1, integer: true, optional: true }),
}).transform((value) => ({ ...value, amount_paise: toPaise(value.amount) }));

export const invoiceVoidSchema = z.object({
  reason: requiredText("Void reason", { min: 3, max: 1000 }),
  version: numberInput({ label: "Invoice version", min: 1, integer: true, optional: true }),
});

export const membershipPlanSchema = z.object({
  name: requiredText("Plan name", { min: 2, max: 160 }),
  duration_days: numberInput({ label: "Duration", min: 1, max: 3650, integer: true }),
  price: currencyInput({ label: "Plan price", min: 0 }),
  joining_fee: currencyInput({ label: "Joining fee", min: 0, optional: true }),
  benefits: optionalText({ max: 2000 }),
}).transform((value) => ({
  name: value.name,
  duration_days: value.duration_days,
  price_paise: toPaise(value.price),
  joining_fee_paise: toPaise(value.joining_fee || 0),
  benefits: (value.benefits || "").split(",").map((item) => item.trim()).filter(Boolean),
}));

export const membershipSchema = z.object({
  client_id: requiredText("Client"),
  plan_id: requiredText("Membership plan"),
  starts_on: dateInput({ label: "Start date" }),
  payment_option: z.enum(["full", "partial", "later"]),
  partial_amount: currencyInput({ label: "Partial payment", positive: true, optional: true }),
  payment_method: z.enum(["cash", "card", "upi", "bank"]).nullable().optional(),
  payment_reference: optionalText({ max: 160 }),
  interstate: z.boolean().default(false),
}).superRefine((value, context) => {
  if (value.payment_option === "partial" && value.partial_amount == null) context.addIssue({ code: "custom", path: ["partial_amount"], message: "Enter the partial payment amount" });
  if (value.payment_option !== "later" && !value.payment_method) context.addIssue({ code: "custom", path: ["payment_method"], message: "Choose a payment method" });
});

export const membershipRenewalSchema = z.object({
  payment_option: z.enum(["full", "partial", "later"]),
  partial_amount: currencyInput({ label: "Partial payment", positive: true, optional: true }),
  payment_method: z.enum(["cash", "card", "upi", "bank"]).nullable().optional(),
  payment_reference: optionalText({ max: 160 }),
  interstate: z.boolean().default(false),
}).superRefine((value, context) => {
  if (value.payment_option === "partial" && value.partial_amount == null) context.addIssue({ code: "custom", path: ["partial_amount"], message: "Enter the partial payment amount" });
  if (value.payment_option !== "later" && !value.payment_method) context.addIssue({ code: "custom", path: ["payment_method"], message: "Choose a payment method" });
});

export const freezeMembershipSchema = z.object({
  frozen_from: dateInput({ label: "Freeze start" }),
  frozen_until: dateInput({ label: "Freeze end" }),
  reason: optionalText({ max: 1000 }),
  version: numberInput({ label: "Membership version", min: 1, integer: true }),
}).refine((value) => new Date(value.frozen_until) >= new Date(value.frozen_from), {
  path: ["frozen_until"], message: "Freeze end must be on or after the start date",
});

export const cancellationSchema = z.object({
  timing: z.enum(["now", "term_end"]),
  reason: requiredText("Cancellation reason", { min: 3, max: 2000 }),
  cancel_scheduled_renewal: z.boolean().default(false),
  version: numberInput({ label: "Membership version", min: 1, integer: true }),
});

export const gymCheckinSchema = z.object({
  membership_id: requiredText("Active membership"),
});

export const gymCoachingSchema = z.object({
  kind: z.enum(["trainers", "measurements", "workouts", "diets"]),
  client_id: requiredText("Client"),
  trainer_employee_id: optionalText({ max: 80 }),
  name: optionalText({ max: 180 }),
  details: optionalText({ max: 10000 }),
  weight: numberInput({ label: "Weight", min: 1, max: 1000, optional: true }),
  height: numberInput({ label: "Height", min: 30, max: 300, optional: true }),
  body_fat: numberInput({ label: "Body fat", min: 0, max: 100, optional: true }),
  notes: optionalText({ max: 5000 }),
}).superRefine((value, context) => {
  if (value.kind === "trainers" && !value.trainer_employee_id) {
    context.addIssue({ code: "custom", path: ["trainer_employee_id"], message: "Choose a trainer" });
  }
  if (["workouts", "diets"].includes(value.kind)) {
    if (!value.name || value.name.length < 2) context.addIssue({ code: "custom", path: ["name"], message: "Plan name is required" });
    if (!value.details) context.addIssue({ code: "custom", path: ["details"], message: "Plan guidance is required" });
  }
  if (value.kind === "measurements" && value.weight == null && value.height == null && value.body_fat == null) {
    context.addIssue({ code: "custom", path: ["weight"], message: "Enter at least one measurement" });
  }
});

export const gymClassBookingSchema = z.object({
  client_id: requiredText("Client"),
});

export const gymClassSchema = endAfterStart(z.object({
  name: requiredText("Class name", { min: 2, max: 160 }),
  trainer_employee_id: optionalText({ max: 80 }),
  starts_at: requiredText("Start time"),
  ends_at: requiredText("End time"),
  capacity: numberInput({ label: "Capacity", min: 1, max: 10000, integer: true }),
}), "starts_at", "ends_at", "Class end must be after its start");

export const equipmentSchema = z.object({
  name: requiredText("Equipment name", { min: 2, max: 180 }),
  asset_code: requiredText("Asset code", { min: 1, max: 100 }),
  purchased_on: dateInput({ label: "Purchase date", optional: true }),
  next_service_on: dateInput({ label: "Next service date", optional: true }),
  notes: optionalText({ max: 5000 }),
}).refine((value) => !value.purchased_on || !value.next_service_on || new Date(value.next_service_on) >= new Date(value.purchased_on), {
  path: ["next_service_on"], message: "Next service cannot be before the purchase date",
});

export const patientSchema = z.object({
  client_id: requiredText("Patient identity"),
  abha_number: optionalText({ max: 50 }),
  blood_group: optionalText({ max: 10 }),
  emergency_phone: phone(),
});

export const encounterSchema = z.object({
  location_id: requiredText("Location"),
  patient_id: requiredText("Patient"),
  practitioner_employee_id: requiredText("Practitioner"),
  appointment_id: optionalText({ max: 80 }),
  chief_complaint: requiredText("Chief complaint", { min: 2, max: 5000 }),
});

export const clinicalEncounterDraftSchema = z.object({
  chief_complaint: optionalText({ max: 5000 }),
  clinical_notes: optionalText({ max: 15000 }),
  assessment: optionalText({ max: 10000 }),
  plan: optionalText({ max: 10000 }),
  follow_up_on: dateInput({ label: "Follow-up date", optional: true }),
  version: numberInput({ label: "Encounter version", min: 1, integer: true }),
});

export const diagnosisSchema = z.object({
  description: requiredText("Diagnosis", { min: 2, max: 2000 }),
});

export const prescriptionDraftSchema = z.object({
  medicine_item_id: requiredText("Medicine"),
  medicine_name: optionalText({ max: 180 }),
  dosage: requiredText("Dosage", { max: 120 }),
  frequency: requiredText("Frequency", { max: 120 }),
  duration: requiredText("Duration", { max: 120 }),
  instructions: optionalText({ max: 2000 }),
}).superRefine((value, context) => {
  if (value.medicine_item_id === "manual" && !value.medicine_name) {
    context.addIssue({ code: "custom", path: ["medicine_name"], message: "Medicine name is required" });
  }
});

export const labTestSchema = z.object({
  name: requiredText("Test name", { min: 2, max: 180 }),
  code: requiredText("Test code", { min: 1, max: 80 }),
  price: currencyInput({ label: "Price", min: 0, optional: true }),
}).transform((value) => ({
  name: value.name,
  code: value.code,
  price_paise: toPaise(value.price || 0),
  reference_ranges: {},
}));

export const labOrderSchema = z.object({
  encounter_id: requiredText("Open encounter"),
  test_id: requiredText("Lab test"),
});

export const dispenseSchema = z.object({
  items: z.array(z.object({
    prescription_item_id: requiredText("Prescription item"),
    quantity: numberInput({ label: "Quantity", positive: true }),
    available: numberInput({ label: "Available stock", min: 0 }),
    batch_number: optionalText({ max: 120 }),
  })).min(1, "No inventory-linked medicine is available"),
}).superRefine((value, context) => {
  value.items.forEach((item, index) => {
    if (item.quantity > item.available) context.addIssue({ code: "custom", path: ["items", index, "quantity"], message: `Only ${item.available} is available` });
  });
}).transform((value) => ({
  items: value.items.map((item) => ({
    prescription_item_id: item.prescription_item_id,
    quantity_milli: Math.round(item.quantity * 1000),
    batch_number: item.batch_number || "",
  })),
}));

export const companySchema = z.object({
  name: requiredText("Company name", { min: 2, max: 200 }),
  industry: optionalText({ max: 100 }),
  website: webUrl(),
  contact_name: optionalText({ max: 160 }),
  contact_email: email({ optional: true }),
  contact_phone: phone(),
  notes: optionalText({ max: 5000 }),
});

export const opportunitySchema = z.object({
  company_id: requiredText("Company"),
  title: requiredText("Role or drive title", { min: 2, max: 220 }),
  opportunity_type: z.enum(["campus_drive", "internship", "off_campus", "apprenticeship"]),
  status: z.enum(["draft", "published", "active", "closed", "cancelled"]),
  opens_at: dateInput({ label: "Opening date", optional: true }),
  deadline_at: dateInput({ label: "Deadline", optional: true }),
  drive_at: dateInput({ label: "Drive date", optional: true }),
  work_location: optionalText({ max: 180 }),
  minimum_cgpa: numberInput({ label: "Minimum CGPA", min: 0, max: 10, optional: true }),
  maximum_backlogs: numberInput({ label: "Maximum backlogs", min: 0, max: 100, integer: true, optional: true }),
  minimum_attendance: numberInput({ label: "Minimum attendance", min: 0, max: 100, optional: true }),
  minimum_solved: numberInput({ label: "Minimum solved", min: 0, integer: true, optional: true }),
}).superRefine((value, context) => {
  if (value.opens_at && value.deadline_at && new Date(value.deadline_at) < new Date(value.opens_at)) context.addIssue({ code: "custom", path: ["deadline_at"], message: "Deadline cannot be before opening" });
  if (value.deadline_at && value.drive_at && new Date(value.drive_at) < new Date(value.deadline_at)) context.addIssue({ code: "custom", path: ["drive_at"], message: "Drive date cannot be before the deadline" });
});

export const attendanceRecordSchema = z.object({
  student_profile_id: requiredText("Student"),
  status: z.enum(["present", "absent", "late", "excused"]),
  note: optionalText({ max: 300 }),
});

export const attendanceRecordsSchema = z.array(attendanceRecordSchema).min(1, "Change at least one attendance row")
  .refine((rows) => new Set(rows.map((row) => row.student_profile_id)).size === rows.length, "A student can appear only once");

export const assessmentScoreSchema = z.object({
  student_profile_id: requiredText("Student"),
  marks_awarded: currencyInput({ label: "Marks", min: 0, optional: true }),
  grade: optionalText({ max: 12 }),
  feedback: optionalText({ max: 2000 }),
});

export const assessmentScoresSchema = z.array(assessmentScoreSchema).min(1, "Change at least one score row")
  .refine((rows) => new Set(rows.map((row) => row.student_profile_id)).size === rows.length, "A student can appear only once");

export const attendanceSessionSchema = z.object({
  offering_id: requiredText("Course offering"),
  held_on: dateInput({ label: "Held on" }),
  starts_at: optionalText({ max: 5 }),
  ends_at: optionalText({ max: 5 }),
  topic: optionalText({ max: 300 }),
}).superRefine((value, context) => {
  if (Boolean(value.starts_at) !== Boolean(value.ends_at)) context.addIssue({ code: "custom", path: [value.starts_at ? "ends_at" : "starts_at"], message: "Enter both start and end time" });
  if (value.starts_at && value.ends_at && value.ends_at <= value.starts_at) context.addIssue({ code: "custom", path: ["ends_at"], message: "End time must be after start time" });
});

export const collegeAssessmentSchema = z.object({
  offering_id: requiredText("Course offering"),
  title: requiredText("Assessment title", { min: 2, max: 180 }),
  assessment_type: z.enum(["internal", "assignment", "quiz", "practical", "project", "semester"]),
  max_marks: currencyInput({ label: "Maximum marks", positive: true }),
  weightage_bps: numberInput({ label: "Weightage", min: 0, max: 10000, integer: true }),
  due_on: dateInput({ label: "Due date", optional: true }),
  status: z.enum(["draft", "published", "closed"]),
});

export const collegeApplicationSchema = z.object({
  opportunity_id: requiredText("Opportunity"),
  student_profile_id: requiredText("Student"),
  notes: optionalText({ max: 5000 }),
});

export const collegeConnectorSchema = z.object({
  name: requiredText("Connection name", { min: 2, max: 120 }),
  base_url: webUrl({ optional: false }).refine((value) => value.startsWith("https://"), "Use a secure HTTPS URL"),
  auth_mode: z.enum(["bearer", "header"]),
  auth_header: optionalText({ max: 100 }),
  api_key: z.string().min(1, "API key is required").max(2000, "API key is too long"),
  sync_interval_hours: numberInput({ label: "Sync interval", min: 1, max: 168, integer: true }),
}).superRefine((value, context) => {
  if (value.auth_mode === "header" && !value.auth_header) context.addIssue({ code: "custom", path: ["auth_header"], message: "Header name is required" });
  if (value.auth_header && !/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/.test(value.auth_header)) context.addIssue({ code: "custom", path: ["auth_header"], message: "Header name is invalid" });
});

export const collegeDriveSchema = z.object({
  company_id: requiredText("Company"),
  title: requiredText("Opportunity title", { min: 2, max: 220 }),
  opportunity_type: z.enum(["campus_drive", "internship", "off_campus", "apprenticeship"]),
  status: z.enum(["draft", "published", "active", "closed", "cancelled"]),
  deadline_at: optionalText({ max: 40 }),
  drive_at: optionalText({ max: 40 }),
  work_location: optionalText({ max: 180 }),
  employment_type: optionalText({ max: 50 }),
  package_min: currencyInput({ label: "Minimum package", min: 0, optional: true }),
  package_max: currencyInput({ label: "Maximum package", min: 0, optional: true }),
  minimum_cgpa: numberInput({ label: "Minimum CGPA", min: 0, max: 10, optional: true }),
  maximum_active_backlogs: numberInput({ label: "Maximum active backlogs", min: 0, max: 100, integer: true, optional: true }),
  minimum_attendance: numberInput({ label: "Minimum attendance", min: 0, max: 100, optional: true }),
  minimum_solved: numberInput({ label: "Minimum solved problems", min: 0, integer: true, optional: true }),
}).superRefine((value, context) => {
  if (value.package_min != null && value.package_max != null && value.package_max < value.package_min) context.addIssue({ code: "custom", path: ["package_max"], message: "Maximum package must be at least the minimum" });
  if (value.deadline_at && Number.isNaN(Date.parse(value.deadline_at))) context.addIssue({ code: "custom", path: ["deadline_at"], message: "Application deadline is invalid" });
  if (value.drive_at && Number.isNaN(Date.parse(value.drive_at))) context.addIssue({ code: "custom", path: ["drive_at"], message: "Drive date is invalid" });
  if (value.deadline_at && value.drive_at && new Date(value.drive_at) < new Date(value.deadline_at)) context.addIssue({ code: "custom", path: ["drive_at"], message: "Drive date cannot be before the deadline" });
}).transform((value) => {
  const eligibility_rules = {};
  ["minimum_cgpa", "maximum_active_backlogs", "minimum_attendance", "minimum_solved"].forEach((key) => {
    if (value[key] != null) eligibility_rules[key] = value[key];
  });
  return {
    company_id: value.company_id,
    title: value.title,
    opportunity_type: value.opportunity_type,
    status: value.status,
    opens_at: null,
    deadline_at: value.deadline_at ? new Date(value.deadline_at).toISOString() : null,
    drive_at: value.drive_at ? new Date(value.drive_at).toISOString() : null,
    work_location: value.work_location,
    employment_type: value.employment_type,
    package_min_paise: toPaise(value.package_min),
    package_max_paise: toPaise(value.package_max),
    role_description: null,
    eligibility_rules,
    rounds: [],
  };
});
