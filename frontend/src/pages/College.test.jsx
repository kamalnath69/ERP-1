import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import CollegeWorkspace from "./CollegeWorkspace";


vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ can: () => true }),
}));

vi.mock("@/components/ai/AIConversationProvider", () => ({
  useRegisterAIPageContext: () => {},
}));

vi.mock("@/components/charts/BusinessChart", () => ({
  default: () => <div>Academic trend chart</div>,
}));

vi.mock("@/features/college/collegeApi", () => {
  const emptyResult = { data: { items: [], next_cursor: null, has_more: false }, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() };
  const emptyPage = () => emptyResult;
  const mutation = () => [vi.fn(), { isLoading: false }];
  const applicationsResult = {
    data: { items: [{ id: "app-1", version: 1, current_stage_id: "stage-1", eligibility_status: "eligible", updated_at: "2026-08-10T10:00:00Z", student: { name: "Asha Raman", admission_number: "ADM-001" }, opportunity: { title: "Graduate Engineer" }, company: { name: "Northstar" }, stage: { name: "Applied", slug: "applied" } }], next_cursor: null, has_more: false },
    isLoading: false, isFetching: false, isError: false, refetch: vi.fn(),
  };
  const clearanceResult = {
    data: { items: [{ id: "student-1", student_name: "Asha Raman", admission_number: "ADM-001", program_name: "B.Tech CSE", cohort_name: "Class of 2027", clearance_status: "pending", source_updated_at: "2026-08-10T10:00:00Z" }], next_cursor: null, has_more: false },
    isLoading: false, isFetching: false, isError: false, refetch: vi.fn(),
  };
  const stagesResult = { data: { items: [{ id: "stage-1", name: "Applied", slug: "applied", is_enabled: true }] } };
  const referencesResult = { data: { offerings: [], programs: [], cohorts: [], courses: [] } };
  const departmentsResult = { ...emptyResult, data: { items: [{ id: "dept-aiml", name: "Artificial Intelligence and Machine Learning", code: "AIML", is_active: true, version: 1 }], next_cursor: null, has_more: false } };
  const programsResult = { ...emptyResult, data: { items: [{ id: "program-aiml", department_id: "dept-aiml", department_name: "Artificial Intelligence and Machine Learning", department_code: "AIML", name: "B.Tech Artificial Intelligence", code: "BTECH-AIML", duration_semesters: 8, is_active: true, version: 1 }], next_cursor: null, has_more: false } };
  const cohortsResult = { ...emptyResult, data: { items: [{ id: "aiml-a", program_id: "program-aiml", department_id: "dept-aiml", department_code: "AIML", program_code: "BTECH-AIML", name: "AI 2027 / A", code: "AIML-2027-A", admission_year: 2023, graduation_year: 2027, section: "A", current_semester: 7, is_active: true, version: 1 }], next_cursor: null, has_more: false } };
  const hierarchyResult = {
    data: {
      items: [{
        graduation_year: 2027,
        label: "Class of 2027",
        student_count: 40,
        placed_count: 18,
        unplaced_count: 22,
        department_count: 1,
        section_count: 2,
        departments: [{
          id: "dept-cse",
          name: "Computer Science and Engineering",
          code: "CSE",
          student_count: 40,
          placed_count: 18,
          unplaced_count: 22,
          section_count: 2,
          programs: [{
            id: "program-cse",
            name: "B.E. Computer Science",
            code: "BE-CSE",
            student_count: 40,
            placed_count: 18,
            unplaced_count: 22,
            section_count: 2,
            sections: [
              { id: "cse-a", name: "CSE A", section: "A", current_semester: 7, student_count: 20, placed_count: 10, unplaced_count: 10 },
              { id: "cse-b", name: "CSE B", section: "B", current_semester: 7, student_count: 20, placed_count: 8, unplaced_count: 12 },
            ],
          }],
        }],
      }],
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  };
  const leaderboardsResult = { data: { readiness: [], coding: [], academics: [], improvement: [] }, isLoading: false };
  const policyResult = { data: { name: "Placement readiness", weights: { academics: 25 }, minimum_coverage_percent: 60 }, isError: false, refetch: vi.fn() };
  const academicSummaryResult = {
    currentData: {
      scope: { term: { id: "term-7", name: "Semester 7", academic_year: "2026-27", status: "active" } },
      metrics: { students_in_scope: 40, average_attendance_percent: 86.4, results_coverage_percent: 90, active_assessments: 3 },
      attendance_trend: [{ date: "2026-08-01", attendance_percent: 86.4 }],
      result_coverage: { students_with_results: 36, students_in_scope: 40, percent: 90 },
      structure: { departments: 1, programs: 1, cohorts: 2, courses: 6, ready: true },
      freshness: { last_erp_sync_at: null, last_exchange_at: null, stale_connectors: 0, connector_count: 0 },
      attention: [],
      capabilities: { structure: true, students: true, attendance: true, results: true, assessments: true, integrations: true, exchange: true },
    },
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  };
  return {
    useGetCollegeApplicationsQuery: () => applicationsResult,
    useGetCollegeAcademicHierarchyQuery: () => hierarchyResult,
    useGetCollegeAcademicSummaryQuery: () => academicSummaryResult,
    useGetCollegeDepartmentsPageQuery: () => departmentsResult,
    useGetCollegeProgramsPageQuery: () => programsResult,
    useGetCollegeTermsPageQuery: emptyPage,
    useGetCollegeCoursesPageQuery: emptyPage,
    useGetCollegeOfferingsPageQuery: emptyPage,
    useGetCollegePipelineStagesQuery: () => stagesResult,
    useGetCollegeInternshipClearancePageQuery: () => clearanceResult,
    useGetCollegeReferencesQuery: () => referencesResult,
    useGetCollegeAcademicEvidencePageQuery: emptyPage,
    useGetCollegeAssessmentRegisterQuery: emptyPage,
    useGetCollegeAssessmentsPageQuery: emptyPage,
    useGetCollegeAssessmentSchemesPageQuery: emptyPage,
    useGetCollegeAttendanceRegisterQuery: emptyPage,
    useGetCollegeAttendanceSessionsPageQuery: emptyPage,
    useGetCollegeCohortsPageQuery: () => cohortsResult,
    useGetCollegeCompaniesQuery: emptyPage,
    useGetCollegeImportsQuery: emptyPage,
    useGetCollegeIntegrationsQuery: emptyPage,
    useGetCollegeIntegrationCredentialsQuery: emptyPage,
    useGetCollegeLeaderboardsQuery: () => leaderboardsResult,
    useGetCollegeOpportunitiesQuery: emptyPage,
    useGetCollegeReadinessPolicyQuery: () => policyResult,
    useGetCollegeStudentIntelligenceQuery: emptyPage,
    useCommitCollegeImportMutation: mutation,
    useCreateCollegeApplicationMutation: mutation,
    useCreateCollegeAssessmentMutation: mutation,
    useCreateCollegeAttendanceMutation: mutation,
    useCreateCollegeCohortMutation: mutation,
    useCreateCollegeCohortsBulkMutation: mutation,
    useCreateCollegeCompanyMutation: mutation,
    useCreateCollegeCourseMutation: mutation,
    useCreateCollegeDepartmentMutation: mutation,
    useCreateCollegeIntegrationMutation: mutation,
    useCreateCollegeIntegrationCredentialMutation: mutation,
    useCreateCollegeExamCycleMutation: mutation,
    useCreateCollegeOfferingMutation: mutation,
    useCreateCollegeOpportunityMutation: mutation,
    useCreateCollegeProgramMutation: mutation,
    useCreateCollegeTermMutation: mutation,
    useMoveCollegeApplicationStageMutation: mutation,
    usePreviewCollegeCsvImportMutation: mutation,
    useQueueCollegeIntegrationSyncMutation: mutation,
    useRevokeCollegeIntegrationCredentialMutation: mutation,
    useRotateCollegeIntegrationCredentialMutation: mutation,
    useSaveCollegeAttendanceMutation: mutation,
    useSaveCollegeScoresMutation: mutation,
    useSetCollegeAcademicRecordArchivedMutation: mutation,
    useUpdateCollegeAcademicRecordMutation: mutation,
    useUpdateCollegeIntegrationMutation: mutation,
  };
});


async function renderAt(path) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter initialEntries={[path]}><Routes>
      <Route path="/app/college" element={<CollegeWorkspace workspace="placement" />} />
      <Route path="/app/academics" element={<CollegeWorkspace workspace="academics" />} />
    </Routes></MemoryRouter>);
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


test("opens College on the live placement pipeline with universal navigation", async () => {
  const view = await renderAt("/app/college");
  expect(view.container.textContent).toContain("Placement workspace");
  expect(view.container.textContent).toContain("Live pipeline");
  expect(view.container.textContent).toContain("Asha Raman");
  expect(view.container.textContent).toContain("Graduate Engineer");
  expect(view.container.textContent).not.toContain("ERP synchronization");
  expect(view.container.textContent).not.toContain("Academic structure");
  expect(view.container.textContent).not.toContain("Revenue");
  expect(view.container.textContent).not.toContain("Invoices");
  view.cleanup();
});

test("opens Academics on a scoped overview with data operations navigation", async () => {
  const view = await renderAt("/app/academics");
  expect(view.container.textContent).toContain("Academic workspace");
  expect(view.container.textContent).toContain("Academic overview");
  expect(view.container.textContent).toContain("Semester 7");
  expect(view.container.textContent).toContain("Attendance trend");
  expect(view.container.textContent).toContain("ERP synchronization");
  expect(view.container.textContent).toContain("Data exchange");
  expect(view.container.textContent).not.toContain("Live pipeline");
  view.cleanup();
});


test("keeps fee evidence as a compact internship-clearance administration view", async () => {
  const view = await renderAt("/app/college?section=clearance");
  expect(view.container.textContent).toContain("Internship eligibility clearance");
  expect(view.container.textContent).toContain("Clearance is an eligibility signal, not a billing workflow");
  expect(view.container.textContent).toContain("Asha Raman");
  expect(view.container.textContent).toContain("Action needed");
  expect(view.container.textContent).not.toContain("Outstanding amount");
  view.cleanup();
});


test("opens legacy batch links in the managed academic structure console", async () => {
  const view = await renderAt("/app/college?section=batches");
  expect(view.container.textContent).toContain("Academic workspace");
  expect(view.container.textContent).toContain("Academic structure");
  expect(view.container.textContent).toContain("Start with placement essentials");
  expect(view.container.textContent).toContain("Departments");
  expect(view.container.textContent).toContain("Batches & sections");
  expect(view.container.textContent).toContain("ERP-safe ownership");
  view.cleanup();
});
