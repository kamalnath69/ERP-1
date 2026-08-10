import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import CollegeStudentProfile from "./CollegeStudentProfile";


vi.mock("@/components/charts/BusinessChart", () => ({
  __esModule: true,
  default: ({ ariaLabel }) => ariaLabel || "Business chart",
}));


const studentQuery = {
  isLoading: false,
  isError: false,
  data: {
    readiness: {
      score: 82,
      coverage_percent: 90,
      band: "ready",
      rankable: true,
      policy_version: 2,
      calculated_at: "2026-08-06T10:00:00Z",
      factors: {
        academics: { value: 86, available: true },
        coding: { value: 78, available: true },
      },
      missing_evidence: ["training"],
    },
    fee_clearance: {
      status: "pending",
      assigned_count: 1,
      cleared_count: 0,
      open_invoice_count: 1,
    },
    career: {
      participation_status: "participating",
      placement_status: "seeking",
      resume_status: "approved",
      preferred_roles: ["Software Engineer"],
    },
    academics: [{ id: "term-1", cgpa: 8.6, active_backlogs: 0 }],
    attendance: [{ id: "attendance-1", attendance_percent: 91 }],
    coding: { account: { username: "asha-code" }, snapshots: [{ id: "coding-1", total: 145 }] },
    applications: [],
    interventions: [{
      id: "intervention-1",
      title: "Review system design feedback",
      note: "Schedule a follow-up mock interview",
      due_on: "2026-08-20",
      status: "open",
      priority: "high",
    }],
  },
};


test("renders readiness coverage and active student interventions", () => {
  const html = renderToStaticMarkup(<CollegeStudentProfile
    query={studentQuery}
    canReviewFees
    onReviewFees={vi.fn()}
  />);

  expect(html).toContain("Evidence-backed readiness");
  expect(html).toContain("90% coverage");
  expect(html).toContain("Evidence needs review");
  expect(html).toContain("Active interventions");
  expect(html).toContain("Review system design feedback");
  expect(html).not.toContain("Internship prerequisite");
});


test("keeps internship clearance focused in placements", () => {
  const html = renderToStaticMarkup(<CollegeStudentProfile
    query={studentQuery}
    defaultTab="placements"
    canReviewFees
    onReviewFees={vi.fn()}
  />);

  expect(html).toContain("Internship prerequisite");
  expect(html).toContain("Action needed");
  expect(html).toContain("Confirmed pending clearance blocks internship participation");
  expect(html).toContain("Review");
});
