import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const invalidations = [...resourceTags("appointments"), ...resourceTags("dashboard"), ...resourceTags("clients")];

export const schedulingApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    createAppointment: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/appointments", method: "POST", data }, api),
      invalidatesTags: invalidations,
    }),
    updateAppointmentStatus: builder.mutation({
      queryFn: ({ appointmentId, status, version }, api) => domainRequest({ url: `/appointments/${appointmentId}/status`, method: "PATCH", data: { status, version } }, api),
      invalidatesTags: invalidations,
    }),
    rescheduleAppointment: builder.mutation({
      queryFn: ({ appointmentId, ...data }, api) => domainRequest({ url: `/appointments/${appointmentId}`, method: "PATCH", data }, api),
      invalidatesTags: invalidations,
    }),
  }),
});

export const { useCreateAppointmentMutation, useUpdateAppointmentStatusMutation, useRescheduleAppointmentMutation } = schedulingApi;
