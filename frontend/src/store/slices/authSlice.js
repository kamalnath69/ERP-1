import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api, { tokenStore } from "@/lib/api";
import { invalidateTerminology, resetTerminology } from "@/hooks/useTerminology";

export const fetchMe = createAsyncThunk("auth/fetchMe", async (_, { rejectWithValue }) => {
  try {
    const { data } = await api.get("/auth/me");
    return data;
  } catch (e) {
    return rejectWithValue(e?.response?.data || { detail: "Not authenticated" });
  }
});

export const loginThunk = createAsyncThunk("auth/login", async ({ email, password }, { dispatch, rejectWithValue }) => {
  try {
    const { data } = await api.post("/auth/login", { email, password });
    tokenStore.set(data.access_token);
    tokenStore.setRefresh(data.refresh_token);
    await dispatch(fetchMe());
    // Refresh tenant-specific caches so the new user never sees the previous tenant's data.
    try { await invalidateTerminology(); } catch {}
    return data.user;
  } catch (e) {
    return rejectWithValue(e?.response?.data || { detail: "Login failed" });
  }
});

export const registerOrgThunk = createAsyncThunk("auth/registerOrg", async (payload, { dispatch, rejectWithValue }) => {
  try {
    const { data } = await api.post("/auth/register", payload);
    tokenStore.set(data.access_token);
    tokenStore.setRefresh(data.refresh_token);
    await dispatch(fetchMe());
    try { await invalidateTerminology(); } catch {}
    return data.user;
  } catch (e) {
    return rejectWithValue(e?.response?.data || { detail: "Registration failed" });
  }
});

export const logoutThunk = createAsyncThunk("auth/logout", async () => {
  try {
    await api.post("/auth/logout", { refresh_token: tokenStore.getRefresh() });
  } catch {}
  tokenStore.clear();
  // Reset (no fetch — user is unauthenticated) so the login page & subsequent
  // login from a different tenant doesn't briefly show the old terminology.
  try { resetTerminology(); } catch {}
});

const initialState = {
  user: null,
  organization: null,
  permissions: [],
  roles: [],
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
      })
      .addCase(fetchMe.rejected, (s, a) => {
        s.loading = false;
        s.user = null;
        s.organization = null;
        s.permissions = [];
        s.roles = [];
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
