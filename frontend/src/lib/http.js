import axios from "axios";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL || import.meta.env.REACT_APP_BACKEND_URL || "";
export const API_BASE = `${BACKEND_URL}/api`;
const http = axios.create({ baseURL: API_BASE, withCredentials: true });

// HttpOnly cookies are the only browser session store.
localStorage.removeItem("edvatiq.access_token");
localStorage.removeItem("edvatiq.refresh_token");

function cookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const match = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : "";
}

http.interceptors.request.use((config) => {
  if (["post", "put", "patch", "delete"].includes(config.method?.toLowerCase())) {
    const csrf = cookie("edvatiq_csrf");
    if (csrf) config.headers["X-CSRF-Token"] = csrf;
  }
  return config;
});

let refreshing = null;

function readableDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => {
    const path = (item?.loc || []).filter((part) => part !== "body").join(" ").replaceAll("_", " ");
    return path ? `${path}: ${item?.msg || "Invalid value"}` : item?.msg || "Invalid value";
  }).join(". ");
  if (detail && typeof detail === "object") return detail.message || "The request could not be completed";
  return "The request could not be completed";
}

export function apiErrorMessage(error, fallback = "The request could not be completed") {
  const detail = error?.response?.data?.detail;
  return detail == null ? fallback : readableDetail(detail);
}

http.interceptors.response.use((response) => response, async (error) => {
  const original = error.config || {};
  const path = String(original.url || "");
  const refreshExcluded = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout", "/auth/email/", "/auth/password/"].some((item) => path.includes(item));
  if (error.response?.status === 401 && !original._retry && !refreshExcluded) {
    original._retry = true;
    try {
      refreshing = refreshing || axios.post(`${API_BASE}/auth/refresh`, {}, {
        withCredentials: true,
        headers: { "X-CSRF-Token": cookie("edvatiq_csrf") },
      }).finally(() => { refreshing = null; });
      await refreshing;
      return http(original);
    } catch {
      if (!original.suppressAuthRedirect && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login?expired=1";
      }
    }
  }
  if (error.response?.data?.detail && typeof error.response.data.detail !== "string") {
    error.response.data.validation_errors = error.response.data.detail;
    error.response.data.detail = readableDetail(error.response.data.detail);
  }
  return Promise.reject(error);
});

export default http;
