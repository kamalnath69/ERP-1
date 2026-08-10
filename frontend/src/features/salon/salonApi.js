import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const get = (url, { locationId, range }, api) => domainRequest({
  url,
  method: "GET",
  params: { location_id: locationId || undefined, range },
}, api);

const tags = [...resourceTags("salon"), ...resourceTags("appointments"), ...resourceTags("clients")];

export const salonApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getSalonOverview: builder.query({
      queryFn: (args, api) => get("/salon/workspace", args, api),
      providesTags: tags,
      keepUnusedDataFor: 90,
    }),
    getSalonBookings: builder.query({
      queryFn: (args, api) => get("/salon/bookings", args, api),
      providesTags: tags,
      keepUnusedDataFor: 60,
    }),
    getSalonRebooking: builder.query({
      queryFn: (args, api) => get("/salon/rebooking", args, api),
      providesTags: tags,
      keepUnusedDataFor: 120,
    }),
    getSalonFollowUps: builder.query({
      queryFn: (args, api) => get("/salon/follow-ups", args, api),
      providesTags: tags,
      keepUnusedDataFor: 90,
    }),
    getSalonSummary: builder.query({
      queryFn: (args, api) => get("/salon/summary", args, api),
      providesTags: tags,
      keepUnusedDataFor: 90,
    }),
  }),
});

export const {
  useGetSalonOverviewQuery,
  useGetSalonBookingsQuery,
  useGetSalonRebookingQuery,
  useGetSalonFollowUpsQuery,
  useGetSalonSummaryQuery,
} = salonApi;
