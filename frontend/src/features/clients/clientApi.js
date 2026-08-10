import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const clientTags = (clientId, ...resources) => [
  ...resourceTags("clients", clientId),
  ...resources.flatMap((resource) => resourceTags(resource)),
];

export const clientApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getClientWorkspace: builder.query({
      queryFn: ({ clientId, range }, api) => domainRequest({
        url: `/clients/${clientId}/workspace`,
        method: "GET",
        params: { range },
      }, api),
      providesTags: (_result, _error, { clientId }) => clientTags(clientId),
      keepUnusedDataFor: 180,
    }),
    getClientTimeline: builder.query({
      queryFn: ({ clientId, filter = "all", cursor, limit = 50 }, api) => domainRequest({
        url: `/clients/${clientId}/timeline`,
        method: "GET",
        params: {
          event_type: filter === "all" ? undefined : filter,
          cursor: cursor || undefined,
          limit,
        },
      }, api),
      providesTags: (_result, _error, { clientId }) => clientTags(clientId),
      keepUnusedDataFor: 300,
    }),
    getClientMedia: builder.query({
      queryFn: (clientId, api) => domainRequest({ url: `/clients/${clientId}/media`, method: "GET" }, api),
      providesTags: (_result, _error, clientId) => clientTags(clientId, "documents"),
      keepUnusedDataFor: 300,
    }),
    updateClient: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/clients/${clientId}`, method: "PATCH", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "dashboard", "search"),
    }),
    addClientMemory: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/clients/${clientId}/memory`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId),
    }),
    addClientCommitment: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/clients/${clientId}/commitments`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "dashboard"),
    }),
    updateClientCommitment: builder.mutation({
      queryFn: ({ clientId, commitmentId, ...data }, api) => domainRequest({
        url: `/clients/${clientId}/commitments/${commitmentId}`,
        method: "PATCH",
        data,
      }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "dashboard"),
    }),
    updateClientSignal: builder.mutation({
      queryFn: ({ signalId, ...data }, api) => domainRequest({ url: `/client-signals/${signalId}`, method: "PATCH", data }, api),
      invalidatesTags: clientTags(undefined, "dashboard"),
    }),
    uploadClientMedia: builder.mutation({
      queryFn: ({ clientId, formData }, api) => domainRequest({ url: `/clients/${clientId}/media`, method: "POST", data: formData }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "documents"),
    }),
    deleteClientMedia: builder.mutation({
      queryFn: ({ mediaId }, api) => domainRequest({ url: `/client-media/${mediaId}`, method: "DELETE" }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "documents"),
    }),
    askClientCopilot: builder.mutation({
      queryFn: ({ clientId, message }, api) => domainRequest({ url: `/ai/clients/${clientId}/chat`, method: "POST", data: { message } }, api),
      invalidatesTags: resourceTags("ai"),
    }),
    checkInClient: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/gym/members/${clientId}/check-in`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "gym", "dashboard"),
    }),
    checkOutClient: builder.mutation({
      queryFn: ({ clientId }, api) => domainRequest({ url: `/gym/members/${clientId}/check-out`, method: "POST" }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "gym", "dashboard"),
    }),
    addFitnessGoal: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/gym/members/${clientId}/goals`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "gym"),
    }),
    addCoachingNote: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/gym/members/${clientId}/coaching-notes`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "gym"),
    }),
    addWorkoutSession: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/gym/members/${clientId}/workout-sessions`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "gym"),
    }),
    updateSalonClientProfile: builder.mutation({
      queryFn: ({ clientId, ...data }, api) => domainRequest({ url: `/salon/clients/${clientId}/profile`, method: "PUT", data }, api),
      invalidatesTags: (_result, _error, { clientId }) => clientTags(clientId, "salon"),
    }),
  }),
});

export const {
  useGetClientWorkspaceQuery,
  useGetClientTimelineQuery,
  useGetClientMediaQuery,
  useUpdateClientMutation,
  useAddClientMemoryMutation,
  useAddClientCommitmentMutation,
  useUpdateClientCommitmentMutation,
  useUpdateClientSignalMutation,
  useUploadClientMediaMutation,
  useDeleteClientMediaMutation,
  useAskClientCopilotMutation,
  useCheckInClientMutation,
  useCheckOutClientMutation,
  useAddFitnessGoalMutation,
  useAddCoachingNoteMutation,
  useAddWorkoutSessionMutation,
  useUpdateSalonClientProfileMutation,
} = clientApi;
