import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";

import {
  AttentionCard,
  collegeDashboardLayout,
  collegeDashboardFilterStorageKey,
  dashboardFiltersForAccess,
  groupAttentionRows,
  resolveCollegeDashboardProfile,
} from "./PlacementDashboard";

test("uses deterministic College role precedence", () => {
  expect(resolveCollegeDashboardProfile([{ slug: "faculty" }, { slug: "owner" }])).toBe("leadership");
  expect(resolveCollegeDashboardProfile([{ slug: "placement-coordinator" }, { slug: "faculty" }])).toBe("operations");
  expect(resolveCollegeDashboardProfile([{ slug: "class_advisor" }])).toBe("academic_support");
  expect(resolveCollegeDashboardProfile([], ["college.opportunities.manage"])).toBe("operations");
  expect(resolveCollegeDashboardProfile([], ["college.attendance.mark"])).toBe("academic_support");
  expect(resolveCollegeDashboardProfile([], ["college.view"])).toBe("overview");
});

test("composes every College profile in its intended lane order", () => {
  expect(collegeDashboardLayout("leadership")).toEqual({
    primary: ["attendance", "departments", "attention"],
    supporting: ["readiness", "funnel", "brief", "drives"],
  });
  expect(collegeDashboardLayout("operations").primary).toEqual(["attention", "drives", "funnel"]);
  expect(collegeDashboardLayout("academic_support").primary).toEqual(["attention", "attendance", "departments"]);
  expect(collegeDashboardLayout("unknown")).toEqual(collegeDashboardLayout("overview"));
});

test("groups duplicate student warnings into one preview row", () => {
  const grouped = groupAttentionRows([
    {
      student_id: "student-1",
      client_id: "client-1",
      name: "Lokesh Menon",
      admission_number: "COL-2023-0080",
      reason: "Low attendance",
      value: 68.5,
    },
    {
      student_id: "student-1",
      client_id: "client-1",
      name: "Lokesh Menon",
      admission_number: "COL-2023-0080",
      reason: "Resume incomplete",
      value: "draft",
    },
    {
      student_id: "student-2",
      client_id: "client-2",
      name: "Anika Rao",
      reason: "Active backlogs",
      value: 2,
    },
  ]);

  expect(grouped).toHaveLength(2);
  expect(grouped[0]).toMatchObject({
    name: "Lokesh Menon",
    admission_number: "COL-2023-0080",
    lowAttendance: 68.5,
  });
  expect(grouped[0].issues.map((issue) => issue.reason)).toEqual(["Low attendance", "Resume incomplete"]);
});

test("drops saved filters immediately when the access version changes", () => {
  const oldKey = collegeDashboardFilterStorageKey("college-1", "user-1", 4);
  const newKey = collegeDashboardFilterStorageKey("college-1", "user-1", 5);
  const stale = {
    key: oldKey,
    values: { department_id: "department-outside-new-scope", cohort_id: "cohort-1" },
  };

  expect(newKey).not.toBe(oldKey);
  expect(dashboardFiltersForAccess(stale, newKey)).toEqual({
    academic_year: "all",
    graduation_year: "all",
    department_id: "all",
    program_id: "all",
    cohort_id: "all",
  });
});

test("renders compact sparse and empty support states and caps dense previews", () => {
  const row = (index) => ({
    student_id: `student-${index}`,
    client_id: `client-${index}`,
    name: `Student ${index}`,
    reason: index === 1 ? "Low attendance" : "Resume incomplete",
    value: index === 1 ? 68 : "draft",
  });
  const dense = renderToStaticMarkup(<AttentionCard rows={[1, 2, 3, 4, 5].map(row)} total={5} navigate={() => {}} />);
  const sparse = renderToStaticMarkup(<AttentionCard rows={[row(1)]} total={1} navigate={() => {}} />);
  const empty = renderToStaticMarkup(<AttentionCard rows={[]} total={0} navigate={() => {}} />);

  expect((dense.match(/Student [1-5]/g) || [])).toHaveLength(4);
  expect(dense).toContain("Showing 4 of 5");
  expect(dense).toContain("View all students");
  expect(sparse).not.toContain("View all students");
  expect(empty).toContain("No urgent evidence gaps");
  expect(empty).not.toContain("min-h-[220px]");
});

test("uses authorized destinations for support record and view-all actions", async () => {
  const navigate = vi.fn();
  const container = document.createElement("div");
  const root = createRoot(container);
  const rows = [1, 2, 3, 4, 5].map((index) => ({
    student_id: `student-${index}`,
    client_id: `client-${index}`,
    name: `Student ${index}`,
    reason: "Resume incomplete",
  }));

  await act(async () => root.render(<AttentionCard rows={rows} total={5} navigate={navigate} />));
  const actions = [...container.querySelectorAll("button")];
  const studentAction = actions.find((button) => button.textContent.includes("Student 1"));
  const viewAllAction = actions.find((button) => button.textContent.includes("View all students"));

  act(() => studentAction.click());
  expect(navigate).toHaveBeenLastCalledWith("/app/clients/client-1");
  act(() => viewAllAction.click());
  expect(navigate).toHaveBeenLastCalledWith("/app/college?section=readiness");
  act(() => root.unmount());
});
