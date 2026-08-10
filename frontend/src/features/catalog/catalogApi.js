import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

export const catalogApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getCatalogDirectory: builder.query({
      queryFn: ({ q, itemType, state = "active", trackStock, cursor, limit = 25 } = {}, api) => domainRequest({
        url: "/catalog/page",
        method: "GET",
        params: {
          q: q || undefined,
          item_type: itemType && itemType !== "all" ? itemType : undefined,
          state,
          track_stock: trackStock,
          cursor: cursor || undefined,
          limit,
        },
      }, api),
      providesTags: (result) => [
        ...resourceTags("catalog"),
        ...(result?.items || []).map((row) => ({ type: "Resource", id: `catalog:${row.id}` })),
      ],
      keepUnusedDataFor: 600,
    }),
    createCatalogItem: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/catalog", method: "POST", data }, api),
      invalidatesTags: [...resourceTags("catalog"), ...resourceTags("inventory"), ...resourceTags("search")],
    }),
    updateCatalogItem: builder.mutation({
      queryFn: ({ itemId, ...data }, api) => domainRequest({ url: `/catalog/${itemId}`, method: "PATCH", data }, api),
      invalidatesTags: (_result, _error, { itemId }) => [...resourceTags("catalog", itemId), ...resourceTags("inventory"), ...resourceTags("search")],
    }),
  }),
});

export const { useGetCatalogDirectoryQuery, useCreateCatalogItemMutation, useUpdateCatalogItemMutation } = catalogApi;
