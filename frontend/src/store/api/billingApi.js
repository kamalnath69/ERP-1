import { baseApi, domainRequest, resourceTags } from "./baseApi";

const request = (api, args) => domainRequest(args, api);

export const billingApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getBillingOverview: builder.query({
      queryFn: (_arg, api) => request(api, { url: "/billing/overview", method: "GET" }),
      providesTags: resourceTags("billing"),
      keepUnusedDataFor: 180,
    }),
    getBillingInvoices: builder.query({
      queryFn: ({ status, purchaseType, cursor, limit = 25 } = {}, api) => request(api, {
        url: "/billing/invoices/page",
        method: "GET",
        params: {
          status: status && status !== "all" ? status : undefined,
          purchase_type: purchaseType && purchaseType !== "all" ? purchaseType : undefined,
          cursor: cursor || undefined,
          limit,
        },
      }),
      providesTags: (result) => [
        ...resourceTags("billing"),
        ...(result?.items || []).map((row) => ({ type: "Resource", id: `billing:${row.id}` })),
      ],
      keepUnusedDataFor: 180,
    }),
    previewPlanCheckout: builder.mutation({
      queryFn: (data, api) => request(api, { url: "/billing/checkout/preview", method: "POST", data }),
    }),
    createPlanCheckout: builder.mutation({
      queryFn: (data, api) => request(api, { url: "/billing/checkout", method: "POST", data }),
      invalidatesTags: resourceTags("billing"),
    }),
    createPackCheckout: builder.mutation({
      queryFn: ({ packId, ...data }, api) => request(api, { url: `/billing/wallet/packs/${packId}/checkout`, method: "POST", data }),
      invalidatesTags: resourceTags("billing"),
    }),
    verifyBillingPayment: builder.mutation({
      queryFn: (data, api) => request(api, { url: "/billing/payments/verify", method: "POST", data }),
      invalidatesTags: resourceTags("billing"),
    }),
    mockPayInvoice: builder.mutation({
      queryFn: (invoiceId, api) => request(api, { url: `/billing/orders/${invoiceId}/mock-pay`, method: "POST" }),
      invalidatesTags: resourceTags("billing"),
    }),
    schedulePlanChange: builder.mutation({
      queryFn: (data, api) => request(api, { url: "/billing/subscription/schedule", method: "POST", data }),
      invalidatesTags: resourceTags("billing"),
    }),
    cancelPlan: builder.mutation({
      queryFn: (data, api) => request(api, { url: "/billing/subscription/cancel", method: "POST", data }),
      invalidatesTags: resourceTags("billing"),
    }),
    removeScheduledPlanChange: builder.mutation({
      queryFn: (_arg, api) => request(api, { url: "/billing/subscription/scheduled-change", method: "DELETE" }),
      invalidatesTags: resourceTags("billing"),
    }),
  }),
});

export const {
  useGetBillingOverviewQuery,
  useGetBillingInvoicesQuery,
  usePreviewPlanCheckoutMutation,
  useCreatePlanCheckoutMutation,
  useCreatePackCheckoutMutation,
  useVerifyBillingPaymentMutation,
  useMockPayInvoiceMutation,
  useSchedulePlanChangeMutation,
  useCancelPlanMutation,
  useRemoveScheduledPlanChangeMutation,
} = billingApi;
