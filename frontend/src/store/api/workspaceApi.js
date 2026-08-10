import { baseApi, domainRequest, resourceTags } from "./baseApi";

const request = (api, url, params) => domainRequest({ url, method: "GET", params }, api);

export async function combine(api, definitions) {
  const results = await Promise.all(definitions.map(({ url, params }) => request(api, url, params)));
  const data = {};
  const failures = {};
  definitions.forEach((definition, index) => {
    const result = results[index];
    if (result.error) failures[definition.key] = {
      status: result.error.status,
      message: result.error.data?.detail || "Could not refresh",
    };
    else data[definition.key] = result.data;
  });
  if (Object.keys(data).length === 0) return results.find((result) => result.error);
  data._sync = {
    partial: Object.keys(failures).length > 0,
    failures,
    refreshedAt: new Date().toISOString(),
  };
  return { data };
}

function mergeWorkspaceCache(current, incoming) {
  Object.entries(incoming).forEach(([key, value]) => {
    if (key !== "_sync") current[key] = value;
  });
  current._sync = incoming._sync;
}

const tags = (...resources) => resources.flatMap((resource) => resourceTags(resource));
const itemTags = (resource, result, select = (value) => value?.items || value || []) => [
  ...resourceTags(resource),
  ...(select(result) || []).filter((item) => item?.id).map((item) => ({ type: "Resource", id: `${resource}:${item.id}` })),
];

export const workspaceApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getDashboardWorkspace: builder.query({
      queryFn: ({ locationId, range = 30 }, api) => request(api, "/dashboard/workspace", { location_id: locationId || undefined, range }),
      providesTags: tags("dashboard"),
      keepUnusedDataFor: 90,
    }),
    saveMyPreference: builder.mutation({
      queryFn: ({ namespace, value, version }, api) => domainRequest({ url: `/users/me/preferences/${namespace}`, method: "PUT", data: { value, version } }, api),
      invalidatesTags: tags("business"),
    }),
    getClients: builder.query({
      queryFn: ({ locationId, q = "", limit = 100 }, api) => request(api, "/clients", { location_id: locationId || undefined, q: q || undefined, limit }),
      providesTags: (result) => itemTags("clients", result),
      keepUnusedDataFor: 300,
    }),
    getClientDirectory: builder.query({
      queryFn: ({ locationId, q = "", segment = "all", limit = 50, cursor }, api) => request(api, "/clients/directory", {
        location_id: locationId || undefined,
        q: q || undefined,
        segment,
        limit,
        cursor: cursor || undefined,
      }),
      providesTags: (result) => itemTags("clients", result),
      keepUnusedDataFor: 180,
    }),
    createClient: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/clients", method: "POST", data }, api),
      invalidatesTags: tags("clients", "dashboard", "salon", "gym", "clinic"),
    }),
    getEmployees: builder.query({
      queryFn: ({ limit = 100 } = {}, api) => request(api, "/employees", { limit }),
      providesTags: (result) => itemTags("team", result),
      keepUnusedDataFor: 600,
    }),
    getRoles: builder.query({
      queryFn: (_arg, api) => request(api, "/roles"),
      providesTags: (result) => itemTags("access", result),
      keepUnusedDataFor: 600,
    }),
    getCalendarWorkspace: builder.query({
      async queryFn({ locationId, day }, api) {
        const start = new Date(`${day}T00:00:00`);
        const end = new Date(start);
        start.setDate(start.getDate() - 1);
        end.setDate(end.getDate() + 14);
        return combine(api, [
          { key: "appointments", url: "/appointments", params: { location_id: locationId, start: start.toISOString(), end: end.toISOString() } },
          { key: "clientsResponse", url: "/clients", params: { location_id: locationId, limit: 100 } },
          { key: "employeesResponse", url: "/employees", params: { limit: 100 } },
          { key: "services", url: "/catalog", params: { item_type: "service" } },
        ]);
      },
      providesTags: tags("appointments", "clients", "team", "catalog"),
      keepUnusedDataFor: 120,
      merge: mergeWorkspaceCache,
    }),
    getAppointmentsWindow: builder.query({
      queryFn: ({ locationId, day }, api) => {
        const start = new Date(`${day}T00:00:00`);
        const end = new Date(start);
        start.setDate(start.getDate() - 1);
        end.setDate(end.getDate() + 14);
        return request(api, "/appointments", { location_id: locationId, start: start.toISOString(), end: end.toISOString() });
      },
      providesTags: (result) => itemTags("appointments", result),
      keepUnusedDataFor: 60,
    }),
    getCalendarReference: builder.query({
      queryFn: ({ locationId }, api) => combine(api, [
        { key: "clientsResponse", url: "/clients", params: { location_id: locationId, limit: 100 } },
        { key: "employeesResponse", url: "/employees", params: { limit: 100 } },
        { key: "services", url: "/catalog", params: { item_type: "service" } },
      ]),
      providesTags: tags("clients", "team", "catalog"),
      keepUnusedDataFor: 600,
      merge: mergeWorkspaceCache,
    }),
    getTeamWorkspace: builder.query({
      async queryFn({ includeRoles }, api) {
        const definitions = [{ key: "employeesResponse", url: "/employees", params: { limit: 100 } }];
        if (includeRoles) definitions.push({ key: "roles", url: "/roles" });
        return combine(api, definitions);
      },
      providesTags: tags("team", "access"),
      keepUnusedDataFor: 600,
      merge: mergeWorkspaceCache,
    }),
    getCatalogWorkspace: builder.query({
      queryFn: ({ locationId }, api) => combine(api, [
        { key: "items", url: "/catalog" },
        { key: "stock", url: "/inventory", params: { location_id: locationId } },
      ]),
      providesTags: tags("catalog"),
      keepUnusedDataFor: 180,
      merge: mergeWorkspaceCache,
    }),
    getCatalogItems: builder.query({
      queryFn: (_arg, api) => request(api, "/catalog"),
      providesTags: (result) => itemTags("catalog", result),
      keepUnusedDataFor: 600,
    }),
    getInventoryLevels: builder.query({
      queryFn: ({ locationId }, api) => request(api, "/inventory", { location_id: locationId }),
      providesTags: tags("catalog"),
      keepUnusedDataFor: 120,
    }),
    getInventoryWorkspace: builder.query({
      queryFn: ({ locationId, q = "", state }, api) => request(api, "/inventory/workspace", { location_id: locationId || undefined, q: q || undefined, state: state || undefined }),
      providesTags: tags("inventory", "catalog"),
      keepUnusedDataFor: 90,
    }),
    getInventoryLevelsPage: builder.query({
      queryFn: ({ locationId, q = "", state, batchesOnly = false, cursor, limit = 25 }, api) => request(api, "/inventory/levels/page", {
        location_id: locationId || undefined,
        q: q || undefined,
        state: state || undefined,
        batches_only: batchesOnly || undefined,
        cursor: cursor || undefined,
        limit,
      }),
      providesTags: (result) => itemTags("inventory", result),
      keepUnusedDataFor: 90,
    }),
    getInventoryMovementsPage: builder.query({
      queryFn: ({ locationId, q = "", movementType, cursor, limit = 50 }, api) => request(api, "/inventory/movements/page", {
        location_id: locationId || undefined,
        q: q || undefined,
        movement_type: movementType || undefined,
        cursor: cursor || undefined,
        limit,
      }),
      providesTags: (result) => itemTags("inventory", result),
      keepUnusedDataFor: 90,
    }),
    adjustStock: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/inventory/adjust", method: "POST", data }, api),
      invalidatesTags: tags("inventory", "catalog", "dashboard"),
    }),
    transferStock: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/inventory/transfer", method: "POST", data }, api),
      invalidatesTags: tags("inventory", "catalog", "dashboard"),
    }),
    getReports: builder.query({
      queryFn: ({ locationId, start, end }, api) => request(api, "/reports/summary", { location_id: locationId, start, end }),
      providesTags: tags("reports"),
      keepUnusedDataFor: 300,
    }),
    getNotifications: builder.query({
      queryFn: ({ status }, api) => request(api, "/notifications", { unread_only: status === "unread" || undefined }),
      providesTags: (result) => itemTags("notifications", result),
      keepUnusedDataFor: 120,
    }),
    getDocuments: builder.query({
      queryFn: ({ entityType, entityId, q, status, cursor, limit = 25 } = {}, api) => request(api, "/documents/page", {
        entity_type: entityType || undefined,
        entity_id: entityId || undefined,
        q: q || undefined,
        status: status && status !== "all" ? status : undefined,
        cursor: cursor || undefined,
        limit,
      }),
      providesTags: (result) => itemTags("documents", result),
      keepUnusedDataFor: 120,
    }),
    uploadDocument: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/documents/upload", method: "POST", data }, api),
      invalidatesTags: tags("documents"),
    }),
    reindexDocument: builder.mutation({
      queryFn: (documentId, api) => domainRequest({ url: `/documents/${documentId}/reindex`, method: "POST" }, api),
      invalidatesTags: tags("documents"),
    }),
    deleteDocument: builder.mutation({
      queryFn: (documentId, api) => domainRequest({ url: `/documents/${documentId}`, method: "DELETE" }, api),
      invalidatesTags: tags("documents"),
    }),
    getEmployeeProfile: builder.query({
      queryFn: (employeeId, api) => request(api, `/employees/${employeeId}/profile`),
      providesTags: (_result, _error, employeeId) => resourceTags("team", employeeId),
      keepUnusedDataFor: 600,
    }),
    getCatalogProfile: builder.query({
      queryFn: ({ itemId, locationId }, api) => request(api, `/catalog/${itemId}/profile`, { location_id: locationId }),
      providesTags: (_result, _error, { itemId }) => resourceTags("catalog", itemId),
      keepUnusedDataFor: 600,
    }),
  }),
});

export const {
  useGetDashboardWorkspaceQuery, useSaveMyPreferenceMutation, useGetClientsQuery, useGetClientDirectoryQuery, useCreateClientMutation, useGetEmployeesQuery, useGetRolesQuery, useGetCalendarWorkspaceQuery,
  useGetAppointmentsWindowQuery, useGetCalendarReferenceQuery,
  useGetTeamWorkspaceQuery, useGetCatalogWorkspaceQuery,
  useGetCatalogItemsQuery, useGetInventoryLevelsQuery, useGetInventoryWorkspaceQuery, useGetInventoryLevelsPageQuery, useGetInventoryMovementsPageQuery, useAdjustStockMutation, useTransferStockMutation,
  useGetReportsQuery, useGetNotificationsQuery,
  useGetDocumentsQuery, useUploadDocumentMutation, useReindexDocumentMutation, useDeleteDocumentMutation, useGetEmployeeProfileQuery,
  useGetCatalogProfileQuery,
} = workspaceApi;
