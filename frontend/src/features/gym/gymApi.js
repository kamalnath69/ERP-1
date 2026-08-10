import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const get = (url, params, api) => domainRequest({ url, method: "GET", params }, api);
const invalidations = (...resources) => [
  ...resourceTags("gym"),
  ...resourceTags("dashboard"),
  ...resourceTags("clients"),
  ...resources.flatMap((resource) => resourceTags(resource)),
];

export const gymApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getGymSummary: builder.query({
      queryFn: ({ locationId }, api) => get("/gym/summary", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 60,
    }),
    getMembershipPlans: builder.query({
      queryFn: (_arg, api) => get("/gym/plans", undefined, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 600,
    }),
    getMembershipQuote: builder.query({
      queryFn: ({ planId, clientId, kind = "activation", interstate = false }, api) => get("/gym/membership-quote", {
        plan_id: planId,
        client_id: clientId || undefined,
        kind,
        interstate,
      }, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 30,
    }),
    getMemberships: builder.query({
      queryFn: ({ locationId, status }, api) => get("/gym/memberships", { location_id: locationId || undefined, status_filter: status || undefined }, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 90,
    }),
    getGymAttendance: builder.query({
      queryFn: ({ locationId }, api) => get("/gym/check-ins", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 30,
    }),
    getGymClasses: builder.query({
      queryFn: ({ locationId }, api) => get("/gym/classes", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 60,
    }),
    getGymCoaching: builder.query({
      queryFn: ({ section, clientId }, api) => get("/gym/coaching", { section, client_id: clientId || undefined }, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 120,
    }),
    getGymEquipment: builder.query({
      queryFn: ({ locationId }, api) => get("/gym/equipment", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("gym"),
      keepUnusedDataFor: 180,
    }),
    createMembershipPlan: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/plans", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
    createMembership: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/memberships", method: "POST", data }, api),
      invalidatesTags: invalidations("notifications"),
    }),
    freezeMembership: builder.mutation({
      queryFn: ({ membershipId, ...data }, api) => domainRequest({ url: `/gym/memberships/${membershipId}/freeze`, method: "POST", data }, api),
      invalidatesTags: invalidations("notifications"),
    }),
    resumeMembership: builder.mutation({
      queryFn: (membershipId, api) => domainRequest({ url: `/gym/memberships/${membershipId}/resume`, method: "POST" }, api),
      invalidatesTags: invalidations("notifications"),
    }),
    renewMembership: builder.mutation({
      queryFn: (input, api) => {
        const { membershipId, ...data } = typeof input === "string" ? { membershipId: input } : input;
        return domainRequest({ url: `/gym/memberships/${membershipId}/renew`, method: "POST", data }, api);
      },
      invalidatesTags: invalidations("notifications"),
    }),
    cancelMembership: builder.mutation({
      queryFn: ({ membershipId, ...data }, api) => domainRequest({ url: `/gym/memberships/${membershipId}/cancel`, method: "POST", data }, api),
      invalidatesTags: invalidations("notifications"),
    }),
    revokeMembershipCancellation: builder.mutation({
      queryFn: ({ membershipId, ...data }, api) => domainRequest({ url: `/gym/memberships/${membershipId}/cancellation/revoke`, method: "POST", data }, api),
      invalidatesTags: invalidations("notifications"),
    }),
    checkInMember: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/check-ins", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
    checkOutMember: builder.mutation({
      queryFn: (checkinId, api) => domainRequest({ url: `/gym/check-ins/${checkinId}/checkout`, method: "POST" }, api),
      invalidatesTags: invalidations(),
    }),
    assignTrainer: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/trainers", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
    addMeasurement: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/measurements", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
    addWorkoutPlan: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/workouts", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
    addDietPlan: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/diets", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
    createGymClass: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/classes", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
    bookGymClass: builder.mutation({
      queryFn: ({ classId, client_id }, api) => domainRequest({ url: `/gym/classes/${classId}/book`, method: "POST", data: { client_id } }, api),
      invalidatesTags: invalidations(),
    }),
    createGymEquipment: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/gym/equipment", method: "POST", data }, api),
      invalidatesTags: invalidations(),
    }),
  }),
});

export const {
  useGetGymSummaryQuery,
  useGetMembershipPlansQuery,
  useGetMembershipQuoteQuery,
  useGetMembershipsQuery,
  useGetGymAttendanceQuery,
  useGetGymClassesQuery,
  useGetGymCoachingQuery,
  useGetGymEquipmentQuery,
  useCreateMembershipPlanMutation,
  useCreateMembershipMutation,
  useFreezeMembershipMutation,
  useResumeMembershipMutation,
  useRenewMembershipMutation,
  useCancelMembershipMutation,
  useRevokeMembershipCancellationMutation,
  useCheckInMemberMutation,
  useCheckOutMemberMutation,
  useAssignTrainerMutation,
  useAddMeasurementMutation,
  useAddWorkoutPlanMutation,
  useAddDietPlanMutation,
  useCreateGymClassMutation,
  useBookGymClassMutation,
  useCreateGymEquipmentMutation,
} = gymApi;
