import { baseApi, domainRequest, resourceTags } from "@/store/api/baseApi";

const clinicTags = (...resources) => [
  ...resourceTags("clinic"),
  ...resourceTags("dashboard"),
  ...resources.flatMap((resource) => resourceTags(resource)),
];

const get = (url, params, api) => domainRequest({ url, method: "GET", params }, api);

export const clinicApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getClinicSummary: builder.query({
      queryFn: ({ locationId }, api) => get("/clinic/summary", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("clinic"),
      keepUnusedDataFor: 60,
    }),
    getClinicQueue: builder.query({
      queryFn: ({ locationId }, api) => get("/clinic/queue", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("clinic"),
      keepUnusedDataFor: 30,
    }),
    getClinicPatients: builder.query({
      queryFn: ({ locationId }, api) => get("/clinic/patients", { location_id: locationId || undefined }, api),
      providesTags: (result) => [...resourceTags("clinic"), ...(result || []).map((row) => ({ type: "Resource", id: `clients:${row.client_id}` }))],
      keepUnusedDataFor: 180,
    }),
    getClinicEncounters: builder.query({
      queryFn: ({ locationId, status }, api) => get("/clinic/encounters", { location_id: locationId || undefined, status_filter: status || undefined }, api),
      providesTags: resourceTags("clinic"),
      keepUnusedDataFor: 90,
    }),
    getClinicPrescriptions: builder.query({
      queryFn: ({ locationId }, api) => get("/clinic/prescriptions", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("clinic"),
      keepUnusedDataFor: 90,
    }),
    getClinicLabTests: builder.query({
      queryFn: (_arg, api) => get("/clinic/lab/tests", undefined, api),
      providesTags: resourceTags("clinic"),
      keepUnusedDataFor: 600,
    }),
    getClinicLabOrders: builder.query({
      queryFn: ({ locationId }, api) => get("/clinic/lab/orders", { location_id: locationId || undefined }, api),
      providesTags: resourceTags("clinic"),
      keepUnusedDataFor: 90,
    }),
    createPatientProfile: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/clinic/patients", method: "POST", data }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    createEncounter: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/clinic/encounters", method: "POST", data }, api),
      invalidatesTags: clinicTags("appointments", "clients"),
    }),
    updateEncounter: builder.mutation({
      queryFn: ({ encounterId, ...data }, api) => domainRequest({ url: `/clinic/encounters/${encounterId}`, method: "PATCH", data }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    addDiagnosis: builder.mutation({
      queryFn: ({ encounterId, ...data }, api) => domainRequest({ url: `/clinic/encounters/${encounterId}/diagnoses`, method: "POST", data }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    signEncounter: builder.mutation({
      queryFn: (encounterId, api) => domainRequest({ url: `/clinic/encounters/${encounterId}/sign`, method: "POST" }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    createPrescription: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/clinic/prescriptions", method: "POST", data }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    signPrescription: builder.mutation({
      queryFn: (prescriptionId, api) => domainRequest({ url: `/clinic/prescriptions/${prescriptionId}/sign`, method: "POST" }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    createLabTest: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/clinic/lab/tests", method: "POST", data }, api),
      invalidatesTags: clinicTags(),
    }),
    createLabOrder: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/clinic/lab/orders", method: "POST", data }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    signLabOrder: builder.mutation({
      queryFn: (orderId, api) => domainRequest({ url: `/clinic/lab/orders/${orderId}/sign`, method: "POST" }, api),
      invalidatesTags: clinicTags("clients"),
    }),
    dispensePrescription: builder.mutation({
      queryFn: (data, api) => domainRequest({ url: "/clinic/dispenses", method: "POST", data }, api),
      invalidatesTags: clinicTags("inventory", "clients"),
    }),
  }),
});

export const {
  useGetClinicSummaryQuery,
  useGetClinicQueueQuery,
  useGetClinicPatientsQuery,
  useGetClinicEncountersQuery,
  useGetClinicPrescriptionsQuery,
  useGetClinicLabTestsQuery,
  useGetClinicLabOrdersQuery,
  useCreatePatientProfileMutation,
  useCreateEncounterMutation,
  useUpdateEncounterMutation,
  useAddDiagnosisMutation,
  useSignEncounterMutation,
  useCreatePrescriptionMutation,
  useSignPrescriptionMutation,
  useCreateLabTestMutation,
  useCreateLabOrderMutation,
  useSignLabOrderMutation,
  useDispensePrescriptionMutation,
} = clinicApi;
