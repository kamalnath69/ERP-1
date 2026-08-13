import { collegeFilterParams } from "./collegeApi";

test("serializes cohort comparisons as repeated cohort_ids parameters", () => {
  const params = collegeFilterParams({
    cohort_ids: ["aiml-2026-a", "aiml-2027-a"],
    readiness_band: "ready",
  });

  expect(params.getAll("cohort_ids")).toEqual(["aiml-2026-a", "aiml-2027-a"]);
  expect(params.get("readiness_band")).toBe("ready");
});

