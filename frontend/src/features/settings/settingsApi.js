import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

export const settingsApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getSettingsWorkspace: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/settings/workspace", method: "GET" }, api),
      providesTags: [...resourceTags("settings"), ...resourceTags("business")],
      keepUnusedDataFor: 300,
    }),
    updateSettingsSection: builder.mutation({
      queryFn: ({ section, data }, api) => domainRequest({ url: `/settings/${section}`, method: "PUT", data }, api),
      invalidatesTags: [...resourceTags("settings"), ...resourceTags("business"), ...resourceTags("dashboard")],
    }),
    createLocation: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/locations", method: "POST", data }, api),
      invalidatesTags: [...resourceTags("settings"), ...resourceTags("business"), ...resourceTags("dashboard")],
    }),
    updateLocation: builder.mutation({
      queryFn: ({ locationId, data }, api) => domainRequest({ url: `/locations/${locationId}`, method: "PATCH", data }, api),
      invalidatesTags: [...resourceTags("settings"), ...resourceTags("business"), ...resourceTags("dashboard")],
    }),
    requestIndustryMigration: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/settings/industry-migration-request", method: "POST", data }, api),
      invalidatesTags: resourceTags("settings"),
    }),
  }),
});

export const {
  useGetSettingsWorkspaceQuery,
  useUpdateSettingsSectionMutation,
  useCreateLocationMutation,
  useUpdateLocationMutation,
  useRequestIndustryMigrationMutation,
} = settingsApi;
