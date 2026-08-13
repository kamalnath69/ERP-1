import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const collegeTags = () => [
  ...resourceTags("college"),
  ...resourceTags("dashboard"),
];

const mutation = (url, method = "POST") => ({
  queryFn: (data, api) => domainRequest({ url, method, data }, api),
  invalidatesTags: collegeTags,
});

export function collegeFilterParams(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value == null || value === "" || value === "all") return;
    const apiKey = key === "cohortIds" ? "cohort_ids" : key;
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item != null && item !== "") params.append(apiKey, String(item));
      });
    } else {
      params.append(apiKey, String(value));
    }
  });
  return params;
}

const academicPage = (url) => ({
  queryFn: (filters = {}, api) => domainRequest({ url, method: "GET", params: filters }, api),
  providesTags: resourceTags("college"),
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
    getCollegeAcademicHierarchy: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/college/academic-hierarchy", method: "GET" }, api),
      providesTags: resourceTags("college"),
      keepUnusedDataFor: 120,
    }),
    getCollegeCohortsPage: builder.query({
      queryFn: ({ q, departmentId, programId, cohortId, graduationYear, section, active, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/cohorts/page", method: "GET",
        params: {
          q: q || undefined,
          department_id: departmentId || undefined,
          program_id: programId || undefined,
          cohort_id: cohortId || undefined,
          graduation_year: graduationYear || undefined,
          section: section || undefined,
          active,
          cursor: cursor || undefined,
          limit,
        },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeDepartmentsPage: builder.query(academicPage("/college/departments/page")),
    getCollegeProgramsPage: builder.query(academicPage("/college/programs/page")),
    getCollegeTermsPage: builder.query(academicPage("/college/terms/page")),
    getCollegeCoursesPage: builder.query(academicPage("/college/courses/page")),
    getCollegeOfferingsPage: builder.query(academicPage("/college/offerings/page")),
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
    getCollegeAssessmentSchemesPage: builder.query({
      queryFn: ({ q, domain, status, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/assessment-schemes/page",
        method: "GET",
        params: {
          q: q || undefined,
          domain: domain === "all" ? undefined : domain,
          status: status === "all" ? undefined : status,
          cursor: cursor || undefined,
          limit,
        },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeEffectiveAssessmentScheme: builder.query({
      queryFn: ({ domain, programId, cohortId, termId }, api) => domainRequest({
        url: "/college/assessment-schemes/effective",
        method: "GET",
        params: {
          domain,
          program_id: programId || undefined,
          cohort_id: cohortId || undefined,
          term_id: termId || undefined,
        },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeAssessmentReadinessMappings: builder.query({
      queryFn: (schemeId, api) => domainRequest({
        url: `/college/assessment-schemes/${schemeId}/readiness-mappings`,
        method: "GET",
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeExamCyclesPage: builder.query({
      queryFn: ({ domain, termId, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/college/exam-cycles/page",
        method: "GET",
        params: {
          domain: domain === "all" ? undefined : domain,
          term_id: termId || undefined,
          cursor: cursor || undefined,
          limit,
        },
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
        params: collegeFilterParams(filters),
      }, api),
      providesTags: resourceTags("college"),
      keepUnusedDataFor: 60,
    }),
    getCollegeStudentIntelligence: builder.query({
      queryFn: (filters = {}, api) => domainRequest({
        url: "/college/student-intelligence",
        method: "GET",
        params: collegeFilterParams(filters),
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
    getDataExchangeResources: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/data-exchange/resources", method: "GET" }, api),
      providesTags: resourceTags("college"),
    }),
    getDataExchangeResourceSchema: builder.query({
      queryFn: ({ resourceKey, cycleId }, api) => domainRequest({
        url: `/data-exchange/resources/${resourceKey}/schema`,
        method: "GET",
        params: { cycle_id: cycleId || undefined },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getDataExchangeRuns: builder.query({
      queryFn: ({ operation, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/data-exchange/runs",
        method: "GET",
        params: { operation: operation === "all" ? undefined : operation, cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getDataExchangeRun: builder.query({
      queryFn: (runId, api) => domainRequest({
        url: `/data-exchange/runs/${runId}`,
        method: "GET",
      }, api),
      providesTags: resourceTags("college"),
    }),
    getDataExchangeRunRows: builder.query({
      queryFn: ({ runId, status, cursor, limit = 50 }, api) => domainRequest({
        url: `/data-exchange/runs/${runId}/rows`,
        method: "GET",
        params: { status: status || "all", cursor: cursor || undefined, limit },
      }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeIntegrations: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/college/integrations", method: "GET" }, api),
      providesTags: resourceTags("college"),
    }),
    getCollegeIntegrationCredentials: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/college/integrations/credentials", method: "GET" }, api),
      providesTags: resourceTags("college"),
    }),
    createCollegeIntegration: builder.mutation(mutation("/college/integrations")),
    updateCollegeIntegration: builder.mutation({
      queryFn: ({ connectorId, ...data }, api) => domainRequest({
        url: `/college/integrations/${connectorId}`,
        method: "PATCH",
        data,
      }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeIntegrationCredential: builder.mutation(mutation("/college/integrations/credentials")),
    rotateCollegeIntegrationCredential: builder.mutation({
      queryFn: ({ credentialId, version, expiresAt }, api) => domainRequest({
        url: `/college/integrations/credentials/${credentialId}/rotate`,
        method: "POST",
        data: { version, expires_at: expiresAt || null },
      }, api),
      invalidatesTags: collegeTags,
    }),
    revokeCollegeIntegrationCredential: builder.mutation({
      queryFn: ({ credentialId, version }, api) => domainRequest({
        url: `/college/integrations/credentials/${credentialId}`,
        method: "DELETE",
        data: { version },
      }, api),
      invalidatesTags: collegeTags,
    }),
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
    updateCollegeAcademicRecord: builder.mutation({
      queryFn: ({ resource, id, data }, api) => domainRequest({
        url: `/college/${resource}/${id}`, method: "PATCH", data,
      }, api),
      invalidatesTags: collegeTags,
    }),
    setCollegeAcademicRecordArchived: builder.mutation({
      queryFn: ({ resource, id, archived, version, reason }, api) => domainRequest({
        url: `/college/${resource}/${id}/${archived ? "archive" : "restore"}`,
        method: "POST",
        data: { version, reason },
      }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeCohortsBulk: builder.mutation(mutation("/college/cohorts/bulk")),
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
    createCollegeAssessmentScheme: builder.mutation(mutation("/college/assessment-schemes")),
    updateCollegeAssessmentScheme: builder.mutation({
      queryFn: ({ schemeId, data }, api) => domainRequest({
        url: `/college/assessment-schemes/${schemeId}`, method: "PATCH", data,
      }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeAssessmentSchemeVersion: builder.mutation({
      queryFn: ({ schemeId, data }, api) => domainRequest({
        url: `/college/assessment-schemes/${schemeId}/versions`, method: "POST", data,
      }, api),
      invalidatesTags: collegeTags,
    }),
    assignCollegeAssessmentScheme: builder.mutation({
      queryFn: ({ schemeId, data }, api) => domainRequest({
        url: `/college/assessment-schemes/${schemeId}/assignments`, method: "POST", data,
      }, api),
      invalidatesTags: collegeTags,
    }),
    saveCollegeAssessmentReadinessMapping: builder.mutation({
      queryFn: ({ schemeId, data }, api) => domainRequest({
        url: `/college/assessment-schemes/${schemeId}/readiness-mappings`, method: "PUT", data,
      }, api),
      invalidatesTags: collegeTags,
    }),
    createCollegeExamCycle: builder.mutation(mutation("/college/exam-cycles")),
    saveCollegeScores: builder.mutation({
      queryFn: ({ assessmentId, scores, publish, correctionReason }, api) => domainRequest({
        url: `/college/assessments/${assessmentId}/scores`, method: "PUT", data: {
          scores,
          publish,
          correction_reason: correctionReason || null,
        },
      }, api),
      invalidatesTags: collegeTags,
    }),
    createDataExchangeTemplate: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/data-exchange/templates", method: "POST", data }, api),
      invalidatesTags: collegeTags,
    }),
    createDataExchangeImport: builder.mutation({
      queryFn: ({ file, resourceKey, scope = {}, idempotencyKey, correctionReason }, api) => {
        const data = new FormData();
        data.append("file", file);
        data.append("resource_key", resourceKey);
        data.append("scope", JSON.stringify(scope));
        data.append("idempotency_key", idempotencyKey);
        if (correctionReason) data.append("correction_reason", correctionReason);
        return domainRequest({ url: "/data-exchange/imports", method: "POST", data }, api);
      },
      invalidatesTags: collegeTags,
    }),
    createDataExchangeExport: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/data-exchange/exports", method: "POST", data }, api),
      invalidatesTags: collegeTags,
    }),
    commitDataExchangeRun: builder.mutation({
      queryFn: ({ runId, correctionReason }, api) => domainRequest({
        url: `/data-exchange/runs/${runId}/commit`, method: "POST",
        data: { correction_reason: correctionReason || null },
      }, api),
      invalidatesTags: collegeTags,
    }),
    cancelDataExchangeRun: builder.mutation({
      queryFn: (runId, api) => domainRequest({ url: `/data-exchange/runs/${runId}/cancel`, method: "POST" }, api),
      invalidatesTags: collegeTags,
    }),
    downloadDataExchangeArtifact: builder.mutation({
      queryFn: ({ runId, kind }, api) => domainRequest({
        url: `/data-exchange/runs/${runId}/artifacts/${kind}`,
        method: "GET",
        responseType: "blob",
      }, api),
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
  useGetCollegeAcademicHierarchyQuery,
  useGetCollegeCohortsPageQuery,
  useGetCollegeDepartmentsPageQuery,
  useGetCollegeProgramsPageQuery,
  useGetCollegeTermsPageQuery,
  useGetCollegeCoursesPageQuery,
  useGetCollegeOfferingsPageQuery,
  useGetCollegeAcademicEvidencePageQuery,
  useGetCollegeAttendanceSessionsPageQuery,
  useGetCollegeAttendanceRegisterQuery,
  useGetCollegeAssessmentsPageQuery,
  useGetCollegeAssessmentRegisterQuery,
  useGetCollegeAssessmentSchemesPageQuery,
  useGetCollegeEffectiveAssessmentSchemeQuery,
  useGetCollegeAssessmentReadinessMappingsQuery,
  useGetCollegeExamCyclesPageQuery,
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
  useGetDataExchangeResourcesQuery,
  useGetDataExchangeResourceSchemaQuery,
  useGetDataExchangeRunsQuery,
  useGetDataExchangeRunQuery,
  useGetDataExchangeRunRowsQuery,
  useGetCollegeIntegrationsQuery,
  useGetCollegeIntegrationCredentialsQuery,
  useCreateCollegeIntegrationMutation,
  useUpdateCollegeIntegrationMutation,
  useCreateCollegeIntegrationCredentialMutation,
  useRotateCollegeIntegrationCredentialMutation,
  useRevokeCollegeIntegrationCredentialMutation,
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
  useUpdateCollegeAcademicRecordMutation,
  useSetCollegeAcademicRecordArchivedMutation,
  useCreateCollegeCohortsBulkMutation,
  useAdmitCollegeStudentMutation,
  useCreateCollegeAttendanceMutation,
  useSaveCollegeAttendanceMutation,
  useCreateCollegeAssessmentMutation,
  useCreateCollegeAssessmentSchemeMutation,
  useUpdateCollegeAssessmentSchemeMutation,
  useCreateCollegeAssessmentSchemeVersionMutation,
  useAssignCollegeAssessmentSchemeMutation,
  useSaveCollegeAssessmentReadinessMappingMutation,
  useCreateCollegeExamCycleMutation,
  useSaveCollegeScoresMutation,
  useCreateDataExchangeTemplateMutation,
  useCreateDataExchangeImportMutation,
  useCreateDataExchangeExportMutation,
  useCommitDataExchangeRunMutation,
  useCancelDataExchangeRunMutation,
  useDownloadDataExchangeArtifactMutation,
  useCreateCollegeFeePlanMutation,
  useAssignCollegeStudentFeeMutation,
} = collegeApi;
