import {
  applyApiErrors, appointmentSchema, catalogItemSchema, clinicalEncounterDraftSchema, currencyInput,
  gymCoachingSchema, normalizeApiError, prescriptionDraftSchema, stockTransferSchema,
} from "./index";

test("currency inputs reject non-finite and over-precise values", () => {
  const amount = currencyInput({ label: "Amount", positive: true });

  expect(amount.safeParse("10.25").success).toBe(true);
  expect(amount.safeParse("10.257").success).toBe(false);
  expect(amount.safeParse("Infinity").success).toBe(false);
  expect(amount.safeParse("NaN").success).toBe(false);
  expect(amount.safeParse("0").success).toBe(false);
});

test("catalog validation normalizes money and enforces service duration", () => {
  const base = {
    name: "  Personal training  ", sku: " PT-01 ", item_type: "service",
    description: "", hsn_sac: "", price: "499.50", cost: "100", tax_rate: "18",
    duration_minutes: "", unit: "session", tax_inclusive: false, track_stock: false,
  };

  const invalid = catalogItemSchema.safeParse(base);
  expect(invalid.success).toBe(false);
  expect(invalid.error.issues.some((issue) => issue.path.join(".") === "duration_minutes")).toBe(true);

  const valid = catalogItemSchema.parse({ ...base, duration_minutes: "60" });
  expect(valid.name).toBe("Personal training");
  expect(valid.sku).toBe("PT-01");
  expect(valid.price_paise).toBe(49950);
  expect(valid.tax_rate_bps).toBe(1800);
});

test("cross-field schemas reject invalid relationships", () => {
  expect(stockTransferSchema.safeParse({
    item_id: "item-1", source_location_id: "loc-1", destination_location_id: "loc-1",
    quantity: "2", batch_number: "", reason: "Rebalance stock",
  }).success).toBe(false);

  expect(appointmentSchema.safeParse({
    location_id: "loc-1", client_id: "client-1", employee_id: null, service_id: null,
    starts_at: "2026-08-12T12:00", ends_at: "2026-08-12T11:30", source: "phone", notes: "",
  }).success).toBe(false);
});

test("API validation errors map nested field paths without exposing submitted values", () => {
  const normalized = normalizeApiError({ response: { status: 422, data: {
    detail: [{ loc: ["body", "items", 0, "quantity"], type: "value_error", msg: "Quantity must be positive" }],
    error: { code: "validation_error", message: "Please correct the highlighted fields." },
  } } });

  expect(normalized.status).toBe(422);
  expect(normalized.fieldErrors["items.0.quantity"]).toEqual(["Quantity must be positive"]);
  expect(JSON.stringify(normalized)).not.toContain("submitted-value");
});

test("clinical and coaching schemas enforce conditional evidence", () => {
  expect(clinicalEncounterDraftSchema.safeParse({
    chief_complaint: "Review", clinical_notes: "x".repeat(15001), assessment: "", plan: "",
    follow_up_on: "", version: 1,
  }).success).toBe(false);

  expect(gymCoachingSchema.safeParse({
    kind: "measurements", client_id: "client-1", trainer_employee_id: "", name: "", details: "",
    weight: "", height: "", body_fat: "", notes: "",
  }).success).toBe(false);

  expect(prescriptionDraftSchema.safeParse({
    medicine_item_id: "manual", medicine_name: "", dosage: "1 tablet", frequency: "Daily",
    duration: "5 days", instructions: "",
  }).success).toBe(false);
});

test("non-validation API failures become form-level errors", () => {
  const errors = {};
  applyApiErrors(
    { response: { status: 409, data: { detail: "This record changed on another screen" } } },
    (path, value) => { errors[path] = value.message; },
  );

  expect(errors["root.server"]).toBe("This record changed on another screen");
});
