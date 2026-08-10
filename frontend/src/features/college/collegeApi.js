import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const collegeTags = () => [
  ...resourceTags("college"),
  ...resourceTags("dashboard"),
];

const mutation = (url, method = "POST") => ({
  queryFn: (data, api) => domainRequest({ url, method, data }, api),
  invalidatesTags: collegeTags,
});

export const collegeApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getCollegeWorkspace: builder.query({
      queryFn: ({ locationId, range = 30 }, api) => domainRequest({
        url: "/college/workspace",
        method: "GET",
        params: { location_id: locationId || undefined, range },
      }, api),
      providesTags: resourceTags("college"),
      keepUnusedDataFor: 90,
    }),
    getCollegeReferences: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/college/references", method: "GET" }, api),
      providesTags: resourceTags("college"),
      keepUnusedDataFor: 300,
    }),
    getCollegeCohortsPage: builder.query({
      queryFn: ({ q, programId, active, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/cohorts/page", method: "GET",
        params: { q: q || undefined, program_id: programId || undefined, active, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeAcademicEvidencePage: builder.query({
      queryFn: ({ kind = "term_results", q, cohortId, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/academic-evidence/page", method: "GET",
        params: { kind, q: q || undefined, cohort_id: cohortId || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeAttendanceSessionsPage: builder.query({
      queryFn: ({ cohortId, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/attendance/sessions/page", method: "GET",
        params: { cohort_id: cohortId || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeAttendanceRegister: builder.query({
      queryFn: ({ sessionId, q, cursor, limit = 50 }, api) => domainRequest({
        url: `/college/attendance/${sessionId}/register`, method: "GET",
        params: { q: q || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeAssessmentsPage: builder.query({
      queryFn: ({ cohortId, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/assessments/page", method: "GET",
        params: { cohort_id: cohortId || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeAssessmentRegister: builder.query({
      queryFn: ({ assessmentId, q, cursor, limit = 50 }, api) => domainRequest({
        url: `/college/assessments/${assessmentId}/register`, method: "GET",
        params: { q: q || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeInternshipClearancePage: builder.query({
      queryFn: ({ q, clearance = "all", cohortId, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/internship-clearance/page", method: "GET",
        params: { q: q || undefined, clearance, cohort_id: cohortId || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegePlacementDashboard: builder.query({
      queryFn: (filters = {}, api) => domainRequest({
        url: "/college/placement-dashboard",
        method: "GET",
        params: filters,
      }, api),
      providesTags: resourceTags("college"),
      keepUnusedDataFor: 60,
    }),
    getCollegeStudentIntelligence: builder.query({
      queryFn: (filters = {}, api) => domainRequest({
        url: "/college/student-intelligence",
        method: "GET",
        params: filters,
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeReadinessPolicy: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/college/readiness-policy", method: "GET" }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeStudentPlacementProfile: builder.query({
      queryFn: (studentId, api) => domainRequest({
        url: `/college/students/${studentId}/intelligence`,
        method: "GET",
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeLeaderboards: builder.query({
      queryFn: (filters = {}, api) => domainRequest({
        url: "/college/leaderboards",
        method: "GET",
        params: filters,
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeOpportunities: builder.query({
      queryFn: (filters = {}, api) => domainRequest({ url: "/college/opportunities", method: "GET", params: filters }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeCompanies: builder.query({
      queryFn: (filters = {}, api) => domainRequest({ url: "/college/companies", method: "GET", params: filters }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegePipelineStages: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/college/pipeline/stages", method: "GET" }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeApplications: builder.query({
      queryFn: (filters = {}, api) => domainRequest({ url: "/college/applications", method: "GET", params: filters }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeImports: builder.query({
      queryFn: (filters = {}, api) => domainRequest({ url: "/college/imports", method: "GET", params: filters }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeIntegrations: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/college/integrations", method: "GET" }, api),
      providesTags: resourceTags("college"),
    }),
    createCollegeIntegration: builder.mutation(mutation("/college/integrations")),
    queueCollegeIntegrationSync: builder.mutation({
      queryFn: ({ connectorId, resourceTypes, idempotencyKey }, api) => domainRequest({
        url: `/college/integrations/${connectorId}/sync`,
        method: "POST",
        data: {
          resource_types: resourceTypes,
          idempotency_key: idempotencyKey,
        },
      }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeCompany: builder.mutation(mutation("/college/companies")),
    createCollegeOpportunity: builder.mutation(mutation("/college/opportunities")),
    createCollegeApplication: builder.mutation(mutation("/college/applications")),
    moveCollegeApplicationStage: builder.mutation({
      queryFn: ({ applicationId, stageId, version, reason }, api) => domainRequest({
        url: `/college/applications/${applicationId}/stage`,
        method: "PATCH",
        data: { stage_id: stageId, version, reason: reason || null },
      }, api),
      invalidatesTags: collegeTags,
    }),
    recomputeCollegeReadiness: builder.mutation(mutation("/college/readiness/recompute")),
    previewCollegeImport: builder.mutation(mutation("/college/imports/preview")),
    previewCollegeCsvImport: builder.mutation({
      queryFn: ({ file, resourceType, mapping = {} }, api) => {
        const data = new FormData();
        data.append("resource_type", resourceType);
        data.append("mapping_json", JSON.stringify(mapping));
        data.append("file", file);
        return domainRequest({ url: "/college/imports/csv/preview", method: "POST", data }, api);
      },
      invalidatesTags: collegeTags,
    }),
    commitCollegeImport: builder.mutation({
      queryFn: (runId, api) => domainRequest({ url: `/college/imports/${runId}/commit`, method: "POST" }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeDepartment: builder.mutation(mutation("/college/departments")),
    createCollegeProgram: builder.mutation(mutation("/college/programs")),
    createCollegeTerm: builder.mutation(mutation("/college/terms")),
    createCollegeCohort: builder.mutation(mutation("/college/cohorts")),
    createCollegeCourse: builder.mutation(mutation("/college/courses")),
    createCollegeOffering: builder.mutation(mutation("/college/offerings")),
    admitCollegeStudent: builder.mutation({
      ...mutation("/college/students"),
      invalidatesTags: () => [...collegeTags(), ...resourceTags("clients")],
    }),
    createCollegeAttendance: builder.mutation(mutation("/college/attendance")),
    saveCollegeAttendance: builder.mutation({
      queryFn: ({ sessionId, records }, api) => domainRequest({
        url: `/college/attendance/${sessionId}/records`, method: "PUT", data: { records },
      }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeAssessment: builder.mutation(mutation("/college/assessments")),
    saveCollegeScores: builder.mutation({
      queryFn: ({ assessmentId, scores, publish }, api) => domainRequest({
        url: `/college/assessments/${assessmentId}/scores`, method: "PUT", data: { scores, publish },
      }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeFeePlan: builder.mutation(mutation("/college/fee-plans")),
    assignCollegeStudentFee: builder.mutation({
      ...mutation("/college/student-fees"),
      invalidatesTags: () => [...collegeTags(), ...resourceTags("sales")],
    }),
  }),
});

export const {
  useGetCollegeWorkspaceQuery,
  useGetCollegeReferencesQuery,
  useGetCollegeCohortsPageQuery,
  useGetCollegeAcademicEvidencePageQuery,
  useGetCollegeAttendanceSessionsPageQuery,
  useGetCollegeAttendanceRegisterQuery,
  useGetCollegeAssessmentsPageQuery,
  useGetCollegeAssessmentRegisterQuery,
  useGetCollegeInternshipClearancePageQuery,
  useGetCollegePlacementDashboardQuery,
  useGetCollegeStudentIntelligenceQuery,
  useGetCollegeReadinessPolicyQuery,
  useGetCollegeStudentPlacementProfileQuery,
  useGetCollegeLeaderboardsQuery,
  useGetCollegeOpportunitiesQuery,
  useGetCollegeCompaniesQuery,
  useGetCollegePipelineStagesQuery,
  useGetCollegeApplicationsQuery,
  useGetCollegeImportsQuery,
  useGetCollegeIntegrationsQuery,
  useCreateCollegeIntegrationMutation,
  useQueueCollegeIntegrationSyncMutation,
  useCreateCollegeCompanyMutation,
  useCreateCollegeOpportunityMutation,
  useCreateCollegeApplicationMutation,
  useMoveCollegeApplicationStageMutation,
  useRecomputeCollegeReadinessMutation,
  usePreviewCollegeImportMutation,
  usePreviewCollegeCsvImportMutation,
  useCommitCollegeImportMutation,
  useCreateCollegeDepartmentMutation,
  useCreateCollegeProgramMutation,
  useCreateCollegeTermMutation,
  useCreateCollegeCohortMutation,
  useCreateCollegeCourseMutation,
  useCreateCollegeOfferingMutation,
  useAdmitCollegeStudentMutation,
  useCreateCollegeAttendanceMutation,
  useSaveCollegeAttendanceMutation,
  useCreateCollegeAssessmentMutation,
  useSaveCollegeScoresMutation,
  useCreateCollegeFeePlanMutation,
  useAssignCollegeStudentFeeMutation,
} = collegeApi;
