import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

export const teamApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getTeamDirectory: builder.query({
      queryFn: ({ locationId, q = "", status, limit = 50, cursor }, api) => domainRequest({
        url: "/employees/directory",
        method: "GET",
        params: { location_id: locationId || undefined, q: q || undefined, status: status || undefined, limit, cursor: cursor || undefined },
      }, api),
      providesTags: (result) => [
        ...resourceTags("team"),
        ...(result?.items || []).map((row) => ({ type: "Resource", id: `team:${row.id}` })),
      ],
      keepUnusedDataFor: 180,
    }),
    createEmployee: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/employees", method: "POST", data }, api),
      invalidatesTags: [...resourceTags("team"), ...resourceTags("access"), ...resourceTags("dashboard")],
    }),
    updateEmployee: builder.mutation({
      queryFn: ({ employeeId, ...data }, api) => domainRequest({ url: `/employees/${employeeId}`, method: "PATCH", data }, api),
      invalidatesTags: (_result, _error, { employeeId }) => [...resourceTags("team", employeeId), ...resourceTags("dashboard")],
    }),
  }),
});

export const { useGetTeamDirectoryQuery, useCreateEmployeeMutation, useUpdateEmployeeMutation } = teamApi;
