import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const tags = () => resourceTags("notifications");

export const notificationsApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getNotificationInbox: builder.query({
      queryFn: ({ status = "all", q, cursor, limit = 25 }, api) => domainRequest({ url: "/notifications/page", method: "GET", params: { status, q: q || undefined, cursor: cursor || undefined, limit } }, api),
      providesTags: (result) => [...tags(), ...(result?.items || []).map((row) => ({ type: "Resource", id: `notifications:${row.id}` }))],
      keepUnusedDataFor: 120,
    }),
    getNotificationSummary: builder.query({
      queryFn: (_arg, api) => domainRequest({ url: "/notifications/summary", method: "GET" }, api),
      providesTags: tags,
      keepUnusedDataFor: 60,
    }),
    markNotificationRead: builder.mutation({
      queryFn: ({ id }, api) => domainRequest({ url: `/notifications/${id}/read`, method: "POST" }, api),
      invalidatesTags: tags,
    }),
    markAllNotificationsRead: builder.mutation({
      queryFn: (_arg, api) => domainRequest({ url: "/notifications/read-all", method: "POST" }, api),
      invalidatesTags: tags,
    }),
  }),
});

export const { useGetNotificationInboxQuery, useGetNotificationSummaryQuery, useMarkNotificationReadMutation, useMarkAllNotificationsReadMutation } = notificationsApi;
