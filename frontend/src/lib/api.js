import { baseApi } from "@/store/api/baseApi";
import http, { API_BASE, apiErrorMessage } from "@/lib/http";

let dispatchApi = null;

export function bindApiDispatch(dispatch) {
  dispatchApi = dispatch;
}

function axiosCompatibleError(error) {
  const message = error?.data?.detail || error?.message || "The request could not be completed";
  const converted = new Error(message);
  converted.code = error?.code || (error?.status === "CANCELLED" ? "ERR_CANCELED" : undefined);
  converted.response = {
    status: typeof error?.status === "number" ? error.status : 0,
    data: error?.data || { detail: message },
  };
  return converted;
}

async function reduxRequest(method, url, data, config = {}) {
  // Binary data is deliberately not placed in Redux's serializable cache.
  if (!dispatchApi || (config.responseType && config.responseType !== "json")) {
    return http.request({ ...config, method, url, data });
  }

  const { signal, forceRefetch, ...requestConfig } = config;
  const args = { ...requestConfig, method, url, data };
  const isQuery = method === "GET";
  const endpoint = isQuery ? baseApi.endpoints.get : baseApi.endpoints.mutate;
  const pending = dispatchApi(endpoint.initiate(args, isQuery ? { subscribe: false, forceRefetch: Boolean(forceRefetch) } : undefined));

  const abort = () => pending.abort();
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });

  try {
    const result = await pending.unwrap();
    return { ...result, config: { ...config, method, url } };
  } catch (error) {
    throw axiosCompatibleError(error);
  } finally {
    signal?.removeEventListener("abort", abort);
    if (isQuery) pending.unsubscribe();
    else pending.reset();
  }
}

const api = {
  get: (url, config) => reduxRequest("GET", url, undefined, config),
  delete: (url, config = {}) => reduxRequest("DELETE", url, config.data, config),
  post: (url, data, config) => reduxRequest("POST", url, data, config),
  put: (url, data, config) => reduxRequest("PUT", url, data, config),
  patch: (url, data, config) => reduxRequest("PATCH", url, data, config),
  invalidate: (...resources) => dispatchApi?.(baseApi.util.invalidateTags(resources.map((id) => ({ type: "Resource", id })))),
};

export { API_BASE, apiErrorMessage };
export default api;
