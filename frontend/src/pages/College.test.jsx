import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

import CollegeWorkspace from "./CollegeWorkspace";


vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ can: () => true }),
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
  const leaderboardsResult = { data: { readiness: [], coding: [], academics: [], improvement: [] }, isLoading: false };
  const policyResult = { data: { name: "Placement readiness", weights: { academics: 25 }, minimum_coverage_percent: 60 }, isError: false, refetch: vi.fn() };
  return {
    useGetCollegeApplicationsQuery: () => applicationsResult,
    useGetCollegePipelineStagesQuery: () => stagesResult,
    useGetCollegeInternshipClearancePageQuery: () => clearanceResult,
    useGetCollegeReferencesQuery: () => referencesResult,
    useGetCollegeAcademicEvidencePageQuery: emptyPage,
    useGetCollegeAssessmentRegisterQuery: emptyPage,
    useGetCollegeAssessmentsPageQuery: emptyPage,
    useGetCollegeAttendanceRegisterQuery: emptyPage,
    useGetCollegeAttendanceSessionsPageQuery: emptyPage,
    useGetCollegeCohortsPageQuery: emptyPage,
    useGetCollegeCompaniesQuery: emptyPage,
    useGetCollegeImportsQuery: emptyPage,
    useGetCollegeIntegrationsQuery: emptyPage,
    useGetCollegeLeaderboardsQuery: () => leaderboardsResult,
    useGetCollegeOpportunitiesQuery: emptyPage,
    useGetCollegeReadinessPolicyQuery: () => policyResult,
    useGetCollegeStudentIntelligenceQuery: emptyPage,
    useCommitCollegeImportMutation: mutation,
    useCreateCollegeApplicationMutation: mutation,
    useCreateCollegeAssessmentMutation: mutation,
    useCreateCollegeAttendanceMutation: mutation,
    useCreateCollegeCompanyMutation: mutation,
    useCreateCollegeIntegrationMutation: mutation,
    useCreateCollegeOpportunityMutation: mutation,
    useMoveCollegeApplicationStageMutation: mutation,
    usePreviewCollegeCsvImportMutation: mutation,
    useQueueCollegeIntegrationSyncMutation: mutation,
    useSaveCollegeAttendanceMutation: mutation,
    useSaveCollegeScoresMutation: mutation,
  };
});


async function renderAt(path) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter initialEntries={[path]}><CollegeWorkspace /></MemoryRouter>);
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
  expect(view.container.textContent).toContain("ERP synchronization");
  expect(view.container.textContent).not.toContain("Revenue");
  expect(view.container.textContent).not.toContain("Invoices");
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
