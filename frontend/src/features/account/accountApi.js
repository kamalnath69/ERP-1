import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

export const accountApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getMySessions: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/auth/sessions", method: "GET" }, api),
      providesTags: resourceTags("sessions"),
      keepUnusedDataFor: 30,
    }),
    revokeMySession: builder.mutation({
      queryFn: (sessionId, api) => domainRequest({ url: `/auth/sessions/${sessionId}`, method: "DELETE" }, api),
      invalidatesTags: resourceTags("sessions"),
    }),
    revokeAllMySessions: builder.mutation({
      queryFn: (_arg, api) => domainRequest({ url: "/auth/sessions/revoke-all", method: "POST" }, api),
      invalidatesTags: resourceTags("sessions"),
    }),
    updateMyProfile: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/users/me/profile", method: "PATCH", data }, api),
      invalidatesTags: resourceTags("account"),
    }),
    changeMyPassword: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/users/me/password", method: "POST", data }, api),
      invalidatesTags: resourceTags("sessions"),
    }),
    getMySecurity: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/users/me/security", method: "GET" }, api),
      providesTags: resourceTags("security"),
      keepUnusedDataFor: 60,
    }),
    startMyMfa: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/users/me/mfa/start", method: "POST", data }, api),
      invalidatesTags: resourceTags("security"),
    }),
    verifyMyMfa: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/users/me/mfa/verify", method: "POST", data }, api),
      invalidatesTags: resourceTags("security"),
    }),
    regenerateRecoveryCodes: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/users/me/mfa/recovery-codes", method: "POST", data }, api),
      invalidatesTags: resourceTags("security"),
    }),
    disableMyMfa: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/users/me/mfa/disable", method: "POST", data }, api),
      invalidatesTags: resourceTags("security"),
    }),
  }),
});

export const {
  useGetMySessionsQuery,
  useRevokeMySessionMutation,
  useRevokeAllMySessionsMutation,
  useUpdateMyProfileMutation,
  useChangeMyPasswordMutation,
  useGetMySecurityQuery,
  useStartMyMfaMutation,
  useVerifyMyMfaMutation,
  useRegenerateRecoveryCodesMutation,
  useDisableMyMfaMutation,
} = accountApi;
