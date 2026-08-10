import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const salesTags = (...extra) => [
  ...resourceTags("sales"),
  ...resourceTags("dashboard"),
  ...resourceTags("reports"),
  ...extra,
];

export const salesApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getSalesDirectory: builder.query({
      queryFn: ({ locationId, q, status, startsAt, endsAt, limit = 50, cursor }, api) => domainRequest({
        url: "/sales/workspace",
        method: "GET",
        params: {
          location_id: locationId || undefined,
          q: q || undefined,
          status: status && status !== "all" ? status : undefined,
          starts_at: startsAt || undefined,
          ends_at: endsAt || undefined,
          limit,
          cursor: cursor || undefined,
        },
      }, api),
      providesTags: (result) => [
        ...resourceTags("sales"),
        ...(result?.items || []).map((row) => ({ type: "Resource", id: `sales:${row.id}` })),
      ],
      keepUnusedDataFor: 120,
    }),
    getSaleDetail: builder.query({
      queryFn: (invoiceId, api) => domainRequest({ url: `/sales/${invoiceId}`, method: "GET" }, api),
      providesTags: (_result, _error, invoiceId) => resourceTags("sales", invoiceId),
      keepUnusedDataFor: 300,
    }),
    createSale: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/sales", method: "POST", data }, api),
      invalidatesTags: salesTags(...resourceTags("inventory"), ...resourceTags("clients")),
    }),
    recordSalePayment: builder.mutation({
      queryFn: ({ invoiceId, ...data }, api) => domainRequest({ url: `/sales/${invoiceId}/payments`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { invoiceId }) => salesTags(...resourceTags("sales", invoiceId), ...resourceTags("clients")),
    }),
    voidSaleInvoice: builder.mutation({
      queryFn: ({ invoiceId, ...data }, api) => domainRequest({ url: `/sales/${invoiceId}/void`, method: "POST", data }, api),
      invalidatesTags: (_result, _error, { invoiceId }) => salesTags(...resourceTags("sales", invoiceId), ...resourceTags("clients")),
    }),
  }),
});

export const {
  useGetSalesDirectoryQuery,
  useGetSaleDetailQuery,
  useCreateSaleMutation,
  useRecordSalePaymentMutation,
  useVoidSaleInvoiceMutation,
} = salesApi;
