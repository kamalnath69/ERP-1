import { createApi, fakeBaseQuery } from "@reduxjs/toolkit/query/react";
import http from "../../lib/http";
import { broadcastInvalidation } from "./cacheSync";

const RESOURCE_ALIASES = {
  "client-signals": "clients",
  communication: "notifications",
  employees: "team",
  locations: "business",
  organization: "business",
  roles: "access",
  salon: "clients",
  search: "search",
  tasks: "dashboard",
  users: "team",
};

const RELATED_RESOURCES = {
  access: ["auth", "business", "team"],
  ai: ["business", "dashboard"],
  appointments: ["clients", "dashboard"],
  billing: ["auth", "business", "dashboard"],
  business: ["auth", "dashboard", "search"],
  catalog: ["dashboard", "inventory", "reports", "search"],
  clinic: ["clients", "dashboard", "reports"],
  clients: ["dashboard", "reports", "search"],
  documents: ["clients", "ai"],
  gym: ["clients", "dashboard", "reports"],
  inventory: ["catalog", "dashboard", "reports"],
  sales: ["catalog", "clients", "dashboard", "reports"],
  team: ["auth", "business", "search"],
};

export function resourceForUrl(url = "") {
  const segment = String(url).replace(/^https?:\/\/[^/]+/i, "").split("?")[0].split("/").filter(Boolean)[0] || "root";
  if (segment === "super-admin") return "super-admin";
  if (segment === "auth") return "auth";
  return RESOURCE_ALIASES[segment] || segment;
}

export function tagsForUrl(url, includeRelated = false) {
  const resource = resourceForUrl(url);
  const values = includeRelated ? [resource, ...(RELATED_RESOURCES[resource] || [])] : [resource];
  return [...new Set(values)].map((id) => ({ type: "Resource", id }));
}

export function resourceTags(resource, id) {
  return [
    { type: "Resource", id: resource },
    { type: "Resource", id: `${resource}:LIST` },
    ...(id ? [{ type: "Resource", id: `${resource}:${id}` }] : []),
  ];
}

function plainHeaders(headers) {
  if (!headers) return {};
  return Object.fromEntries(Object.entries(headers).map(([key, value]) => [key, String(value)]));
}

function normalizedError(error) {
  return {
    status: error.response?.status || (error.code === "ERR_CANCELED" ? "CANCELLED" : "NETWORK_ERROR"),
    data: error.response?.data || { detail: error.message || "The request could not be completed" },
    message: error.message,
    code: error.code,
  };
}

export async function executeRequest(args, api) {
  const { url, method = "GET", data, params, headers, responseType, suppressAuthRedirect } = args;
  try {
    const response = await http.request({
      url,
      method,
      data,
      params,
      headers,
      responseType,
      suppressAuthRedirect,
      signal: api.signal,
    });
    return {
      data: {
        data: response.data,
        status: response.status,
        statusText: response.statusText,
        headers: plainHeaders(response.headers),
      },
    };
  } catch (error) {
    return { error: normalizedError(error) };
  }
}

export async function domainRequest(args, api) {
  const result = await executeRequest(args, api);
  if (result.error) return result;
  return { data: result.data.data };
}

export const baseApi = createApi({
  reducerPath: "api",
  baseQuery: fakeBaseQuery(),
  tagTypes: ["Resource"],
  keepUnusedDataFor: 300,
  refetchOnFocus: true,
  refetchOnReconnect: true,
  refetchOnMountOrArgChange: 300,
  endpoints: (builder) => ({
    get: builder.query({
      queryFn: (args, api) => executeRequest({ ...args, method: "GET" }, api),
      providesTags: (_result, _error, args) => tagsForUrl(args.url),
    }),
    mutate: builder.mutation({
      queryFn: (args, api) => executeRequest(args, api),
      invalidatesTags: (_result, _error, args) => tagsForUrl(args.url, true),
      async onQueryStarted(args, { queryFulfilled }) {
        try {
          await queryFulfilled;
          broadcastInvalidation(tagsForUrl(args.url, true).map((tag) => tag.id));
        } catch {}
      },
    }),
  }),
});

export const { useGetQuery, useLazyGetQuery, useMutateMutation } = baseApi;
