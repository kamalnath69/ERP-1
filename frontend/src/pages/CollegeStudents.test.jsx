import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";

import CollegeStudents from "./CollegeStudents";

const mocks = vi.hoisted(() => ({
  hierarchy: vi.fn(),
  summary: vi.fn(),
  page: vi.fn(),
}));

const hierarchy = {
  items: [{
    graduation_year: 2027,
    label: "Class of 2027",
    student_count: 40,
    placement_scope_count: 40,
    placed_count: 18,
    unplaced_count: 22,
    department_count: 1,
    section_count: 2,
    departments: [{
      id: "department-ece",
      name: "Electronics and Communication Engineering",
      code: "ECE",
      programs: [{
        id: "program-ece",
        name: "B.E. Electronics and Communication",
        code: "BE-ECE",
        sections: [
          { id: "ece-a", section: "A", cohort_name: "ECE 2027 A", student_count: 20 },
          { id: "ece-b", section: "B", cohort_name: "ECE 2027 B", student_count: 20 },
        ],
      }],
    }],
  }],
  summary: { batch_count: 1, student_count: 40 },
  capabilities: { placement: true },
};

const fullCapabilities = {
  readiness: true, placements: true, assessments: true, attendance: true,
  coding: true, documents: true, contact: true, create: true,
};

const studentPage = {
  items: [{
    id: "student-1", client_id: "client-1", name: "Asha Student",
    admission_number: "ECE-A-001", roll_number: "ROLL-001", graduation_year: 2027,
    section: "A", semester: 7,
    department: { id: "department-ece", code: "ECE", name: "Electronics" },
    program: { id: "program-ece", code: "BE-ECE", name: "B.E. ECE" },
    cgpa: 8.7, active_backlogs: 0, attendance_percent: 91,
    coding_total: 180, resume_status: "approved", placement_status: "seeking",
    readiness_band: "ready", readiness: { score: 82, coverage_percent: 90 },
  }],
  total: 1,
  next_cursor: null,
  has_more: false,
  capabilities: fullCapabilities,
};

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ can: () => true }),
}));

vi.mock("@/contexts/BusinessContext", () => ({
  useBusiness: () => ({ locations: [{ id: "campus-1", name: "Main Campus" }], locationId: "campus-1" }),
}));

vi.mock("@/features/college/collegeApi", () => ({
  useGetCollegeStudentHierarchyQuery: (...args) => mocks.hierarchy(...args),
  useGetCollegeStudentSummaryQuery: (...args) => mocks.summary(...args),
  useGetCollegeStudentsPageQuery: (...args) => mocks.page(...args),
  useAdmitCollegeStudentMutation: () => [vi.fn(() => ({ unwrap: vi.fn() })), { isLoading: false }],
}));

function LocationProbe() {
  const location = useLocation();
  return <output data-location>{location.pathname}{location.search}</output>;
}

async function renderPage(path = "/app/clients") {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter initialEntries={[path]}><CollegeStudents /><LocationProbe /></MemoryRouter>);
    await Promise.resolve();
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
      delete global.IS_REACT_ACT_ENVIRONMENT;
    },
  };
}

beforeEach(() => {
  mocks.hierarchy.mockReset().mockReturnValue({ data: hierarchy, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() });
  mocks.summary.mockReset().mockReturnValue({
    data: { total_students: 40, placement_ready: 14, needs_support: 8, placed_students: 18, capabilities: fullCapabilities },
    isLoading: false, isFetching: false, isError: false, refetch: vi.fn(),
  });
  mocks.page.mockReset().mockReturnValue({ data: studentPage, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() });
});

test("renders graduation batches at the root without mounting a roster", async () => {
  const view = await renderPage();
  expect(view.container.textContent).toContain("Choose a batch");
  expect(view.container.textContent).toContain("Class of 2027");
  expect(view.container.textContent).not.toContain("Student directory");
  expect(mocks.page.mock.calls.at(-1)[1]).toMatchObject({ skip: true });
  view.cleanup();
});

test("waits for the authorized hierarchy before querying a direct batch URL", async () => {
  mocks.hierarchy.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, isError: false, refetch: vi.fn() });
  const view = await renderPage("/app/clients?batch=2027");
  expect(view.container.getAttribute("aria-label") || view.container.textContent).toBeTruthy();
  expect(mocks.summary.mock.calls.at(-1)[1]).toMatchObject({ skip: true });
  expect(mocks.page.mock.calls.at(-1)[1]).toMatchObject({ skip: true });
  view.cleanup();
});

test("opens a batch as URL-backed workspace with its scoped directory", async () => {
  const view = await renderPage();
  const batchButton = [...view.container.querySelectorAll("button")].find((button) => button.textContent.includes("Class of 2027") && button.textContent.includes("40"));
  await act(async () => {
    batchButton.click();
    await Promise.resolve();
  });
  expect(view.container.querySelector("[data-location]").textContent).toBe("/app/clients?batch=2027");
  expect(view.container.textContent).toContain("Student directory");
  expect(view.container.textContent).toContain("Asha Student");
  expect(mocks.page.mock.calls.at(-1)[1]).toMatchObject({ skip: false });
  view.cleanup();
});

test("does not display retained overall metrics while the batch summary loads", async () => {
  const overall = {
    total_students: 110, placement_ready: 46, needs_support: 24,
    placed_students: 31, capabilities: fullCapabilities,
  };
  mocks.summary.mockImplementation((filters = {}) => filters.graduation_year ? {
    data: overall,
    currentData: undefined,
    isLoading: false,
    isFetching: true,
    isError: false,
    refetch: vi.fn(),
  } : {
    data: overall,
    currentData: overall,
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  });

  const view = await renderPage();
  expect(view.container.textContent).toContain("110");
  const batchButton = [...view.container.querySelectorAll("button")].find((button) => button.textContent.includes("Class of 2027") && button.textContent.includes("40"));
  await act(async () => {
    batchButton.click();
    await Promise.resolve();
  });
  expect(view.container.querySelector("[data-location]").textContent).toBe("/app/clients?batch=2027");
  expect(view.container.textContent).not.toContain("110");
  view.cleanup();
});

test("shows the active name and academic sort labels", async () => {
  const nameView = await renderPage("/app/clients?batch=2027");
  const nameSort = [...nameView.container.querySelectorAll('[role="combobox"]')]
    .find((control) => control.textContent.includes("Sort by name"));
  expect(nameSort).toBeTruthy();
  nameView.cleanup();

  const academicView = await renderPage("/app/clients?batch=2027&sort=academics_desc");
  const academicSort = [...academicView.container.querySelectorAll('[role="combobox"]')]
    .find((control) => control.textContent.includes("Best academics first"));
  expect(academicSort).toBeTruthy();
  academicView.cleanup();
});

test("hides evidence, readiness, and placement columns when the policy omits them", async () => {
  const limited = { contact: false, create: false };
  mocks.summary.mockReturnValue({
    data: { total_students: 40, placement_ready: null, needs_support: null, placed_students: null, capabilities: limited },
    isLoading: false, isFetching: false, isError: false, refetch: vi.fn(),
  });
  mocks.page.mockReturnValue({ ...mocks.page(), data: { ...studentPage, capabilities: limited } });
  const view = await renderPage("/app/clients?batch=2027");
  expect(view.container.textContent).toContain("Academic group");
  expect(view.container.textContent).not.toContain("Permitted evidence");
  expect(view.container.textContent).not.toContain("Placement outcome");
  expect(view.container.textContent).not.toContain("Evidence review");
  view.cleanup();
});
