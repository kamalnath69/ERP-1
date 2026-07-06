import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API_BASE });

const TOKEN_KEY = "athena.access_token";
const REFRESH_KEY = "athena.refresh_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  setRefresh: (t) => localStorage.setItem(REFRESH_KEY, t),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

api.interceptors.request.use((config) => {
  const t = tokenStore.get();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

let refreshing = null;

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config || {};
    if (err.response?.status === 401 && !original._retry && tokenStore.getRefresh()) {
      original._retry = true;
      try {
        refreshing =
          refreshing ||
          axios
            .post(`${API_BASE}/auth/refresh`, { refresh_token: tokenStore.getRefresh() })
            .then((res) => {
              tokenStore.set(res.data.access_token);
              tokenStore.setRefresh(res.data.refresh_token);
              return res.data.access_token;
            })
            .finally(() => {
              refreshing = null;
            });
        const newToken = await refreshing;
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch (e) {
        tokenStore.clear();
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
