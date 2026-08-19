import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "@/lib/api";
import { baseApi } from "@/store/api/baseApi";
import { clearTenantPreferences } from "@/store/slices/preferencesSlice";

function authErrorPayload(error, fallback) {
  const source = error?.response?.data
    || (error && typeof error === "object" && (error.detail || error.error) ? error : null)
    || {};
  return {
    ...source,
    detail: source.detail || fallback,
    status: error?.response?.status ?? error?.status ?? source.status ?? null,
    code: error?.code || source.code || null,
  };
}

export const fetchMe = createAsyncThunk("auth/fetchMe", async (_, { rejectWithValue }) => {
  try {
    // A missing session during app startup is normal on public pages. The route
    // guard decides whether sign-in is required after this silent check.
    const { data } = await api.get("/auth/me", { suppressAuthRedirect: true });
    return data;
  } catch (e) {
    return rejectWithValue(authErrorPayload(e, "Not authenticated"));
  }
});

export const loginThunk = createAsyncThunk("auth/login", async ({ email, password, org_slug, mfa_code }, { dispatch, rejectWithValue }) => {
  try {
    const { data } = await api.post("/auth/login", { email, password, org_slug: org_slug || null, mfa_code: mfa_code || null });
    dispatch(baseApi.util.resetApiState());
    dispatch(clearTenantPreferences());
    const session = await dispatch(fetchMe());
    if (fetchMe.rejected.match(session)) {
      return rejectWithValue({
        ...session.payload,
        display_detail: "You are signed in, but your workspace could not be loaded. Please try again.",
      });
    }
    return session.payload?.user || data.user;
  } catch (e) {
    return rejectWithValue(authErrorPayload(e, "Login failed"));
  }
});

export const registerOrgThunk = createAsyncThunk("auth/registerOrg", async (payload, { rejectWithValue }) => {
  try {
    const { data } = await api.post("/auth/register", payload);
    return data;
  } catch (e) {
    return rejectWithValue(authErrorPayload(e, "Registration failed"));
  }
});

export const logoutThunk = createAsyncThunk("auth/logout", async (_, { dispatch }) => {
  try {
    await api.post("/auth/logout");
  } catch {}
  dispatch(baseApi.util.resetApiState());
  dispatch(clearTenantPreferences());
  // Reset (no fetch — user is unauthenticated) so the login page & subsequent
  // login from a different tenant doesn't briefly show the old terminology.
});

const initialState = {
  user: null,
  organization: null,
  permissions: [],
  roles: [],
  accessContext: null,
  loading: true,
  error: null,
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    setProfile: (state, action) => {
      state.user = action.payload.user ?? state.user;
      state.organization = action.payload.organization ?? state.organization;
      state.permissions = action.payload.permissions ?? state.permissions;
      state.roles = action.payload.roles ?? state.roles;
      state.accessContext = action.payload.access_context ?? state.accessContext;
    },
    patchUser: (state, action) => {
      if (state.user) state.user = { ...state.user, ...action.payload };
    },
    reset: () => ({ ...initialState, loading: false }),
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchMe.pending, (s) => {
        s.loading = true;
        s.error = null;
      })
      .addCase(fetchMe.fulfilled, (s, a) => {
        s.loading = false;
        s.user = a.payload.user;
        s.organization = a.payload.organization;
        s.permissions = a.payload.permissions || [];
        s.roles = a.payload.roles || [];
        s.accessContext = a.payload.access_context || null;
      })
      .addCase(fetchMe.rejected, (s, a) => {
        s.loading = false;
        s.user = null;
        s.organization = null;
        s.permissions = [];
        s.roles = [];
        s.accessContext = null;
        s.error = a.payload?.detail || "Not authenticated";
      })
      .addCase(logoutThunk.fulfilled, () => ({ ...initialState, loading: false }));
  },
});

export const { setProfile, patchUser, reset } = authSlice.actions;
export const selectAuth = (s) => s.auth;
export const selectUser = (s) => s.auth.user;
export const selectPermissions = (s) => s.auth.permissions;
export const selectCan = (code) => (s) =>
  s.auth.user?.is_super_admin || s.auth.permissions.includes(code);
export default authSlice.reducer;
