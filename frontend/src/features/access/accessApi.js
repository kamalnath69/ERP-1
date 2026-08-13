import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const tags = () => resourceTags("access");

export const accessApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getAccessWorkspace: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/access/workspace", method: "GET", params: { include_directories: false } }, api),
      providesTags: tags,
      keepUnusedDataFor: 300,
    }),
    getAccessUsersPage: builder.query({
      queryFn: ({ q, status = "all", cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/access/users/page",
        method: "GET",
        params: { q: q || undefined, status, cursor: cursor || undefined, limit },
      }, api),
      providesTags: (result) => [
        ...tags(),
        ...(result?.items || []).map((row) => ({ type: "Resource", id: `access:${row.id}` })),
      ],
      keepUnusedDataFor: 120,
    }),
    getAccessCatalog: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/access/catalog", method: "GET" }, api),
      providesTags: tags,
      keepUnusedDataFor: 300,
    }),
    getAccessPeoplePage: builder.query({
      queryFn: ({ q, status = "all", cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/access/people/page",
        method: "GET",
        params: { q: q || undefined, status, cursor: cursor || undefined, limit },
      }, api),
      providesTags: tags,
      keepUnusedDataFor: 120,
    }),
    getAccessStudentsPage: builder.query({
      queryFn: ({ q, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/access/students/page",
        method: "GET",
        params: { q: q || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: tags,
      keepUnusedDataFor: 120,
    }),
    getAccessClientsPage: builder.query({
      queryFn: ({ q, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/access/clients/page",
        method: "GET",
        params: { q: q || undefined, cursor: cursor || undefined, limit },
      }, api),
      providesTags: tags,
      keepUnusedDataFor: 120,
    }),
    getAccessConfiguration: builder.query({
      queryFn: (userId, api) => domainRequest({ url: `/access/users/${userId}/configuration`, method: "GET" }, api),
      providesTags: (_result, _error, userId) => resourceTags("access", userId),
      keepUnusedDataFor: 120,
    }),
    previewAccess: builder.mutation({
      queryFn: ({ userId, configuration }, api) => domainRequest({ url: `/access/users/${userId}/preview`, method: "POST", data: configuration }, api),
    }),
    saveAccess: builder.mutation({
      queryFn: ({ userId, configuration }, api) => domainRequest({ url: `/access/users/${userId}/configuration`, method: "PUT", data: configuration }, api),
      invalidatesTags: (_result, _error, { userId }) => [...tags(), ...resourceTags("access", userId), ...resourceTags("team"), ...resourceTags("auth")],
    }),
    getEnterprisePolicy: builder.query({
      queryFn: (userId, api) => domainRequest({ url: `/access/users/${userId}/policy`, method: "GET" }, api),
      providesTags: (_result, _error, userId) => resourceTags("access", userId),
    }),
    getEffectivePolicy: builder.query({
      queryFn: (userId, api) => domainRequest({ url: `/access/users/${userId}/effective`, method: "GET" }, api),
      providesTags: (_result, _error, userId) => resourceTags("access", userId),
    }),
    previewEnterprisePolicy: builder.mutation({
      queryFn: ({ userId, policy }, api) => domainRequest({
        url: `/access/users/${userId}/policy/preview`, method: "POST", data: policy,
      }, api),
    }),
    saveEnterprisePolicy: builder.mutation({
      queryFn: ({ userId, policy }, api) => domainRequest({
        url: `/access/users/${userId}/policy`, method: "PUT", data: policy,
      }, api),
      invalidatesTags: (_result, _error, { userId }) => [
        ...tags(), ...resourceTags("access", userId), ...resourceTags("team"), ...resourceTags("auth"),
      ],
    }),
    getAccessDelegation: builder.query({
      queryFn: (userId, api) => domainRequest({ url: `/access/delegations/${userId}`, method: "GET" }, api),
      providesTags: (_result, _error, userId) => resourceTags("access", `delegation:${userId}`),
    }),
    saveAccessDelegation: builder.mutation({
      queryFn: ({ userId, delegation }, api) => domainRequest({
        url: `/access/delegations/${userId}`, method: "PUT", data: delegation,
      }, api),
      invalidatesTags: (_result, _error, { userId }) => [
        ...tags(), ...resourceTags("access", `delegation:${userId}`), ...resourceTags("auth"),
      ],
    }),
    createGuidedRoleTemplate: builder.mutation({
      queryFn: (template, api) => domainRequest({
        url: "/access/role-templates", method: "POST", data: template,
      }, api),
      invalidatesTags: tags,
    }),
    createRole: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/roles", method: "POST", data }, api),
      invalidatesTags: tags,
    }),
    updateRole: builder.mutation({
      queryFn: ({ roleId, ...data }, api) => domainRequest({ url: `/roles/${roleId}`, method: "PATCH", data }, api),
      invalidatesTags: tags,
    }),
    duplicateRole: builder.mutation({
      queryFn: ({ roleId, ...data }, api) => domainRequest({ url: `/roles/${roleId}/duplicate`, method: "POST", data }, api),
      invalidatesTags: tags,
    }),
    deleteRole: builder.mutation({
      queryFn: (roleId, api) => domainRequest({ url: `/roles/${roleId}`, method: "DELETE" }, api),
      invalidatesTags: tags,
    }),
    getAccessAudit: builder.query({
      queryFn: ({ cursor, limit = 50 } = {}, api) => domainRequest({ url: "/access/audit/page", method: "GET", params: { cursor: cursor || undefined, limit } }, api),
      providesTags: tags,
      keepUnusedDataFor: 60,
    }),
  }),
});

export const {
  useGetAccessWorkspaceQuery,
  useGetAccessUsersPageQuery,
  useGetAccessCatalogQuery,
  useGetAccessPeoplePageQuery,
  useGetAccessStudentsPageQuery,
  useGetAccessClientsPageQuery,
  useLazyGetAccessConfigurationQuery,
  usePreviewAccessMutation,
  useSaveAccessMutation,
  useLazyGetEnterprisePolicyQuery,
  useGetEffectivePolicyQuery,
  usePreviewEnterprisePolicyMutation,
  useSaveEnterprisePolicyMutation,
  useGetAccessDelegationQuery,
  useSaveAccessDelegationMutation,
  useCreateGuidedRoleTemplateMutation,
  useCreateRoleMutation,
  useUpdateRoleMutation,
  useDuplicateRoleMutation,
  useDeleteRoleMutation,
  useGetAccessAuditQuery,
} = accessApi;
