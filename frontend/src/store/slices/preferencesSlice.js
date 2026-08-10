import { createSlice } from "@reduxjs/toolkit";

function stored(key, fallback = null) {
  if (typeof window === "undefined") return fallback;
  return localStorage.getItem(key) ?? fallback;
}

function storedJSON(key, fallback) {
  try { return JSON.parse(stored(key, JSON.stringify(fallback))); } catch { return fallback; }
}

const initialState = {
  locationId: stored("edvatiq.location"),
  sidebarCompact: stored("edvatiq.sidebar") === "compact",
  aiSidebarCollapsed: stored("edvatiq.ai.sidebar") === "collapsed",
  appearance: stored("edvatiq.appearance", "system"),
  dashboardLayouts: storedJSON("edvatiq.dashboard.layouts", {}),
};

const preferencesSlice = createSlice({
  name: "preferences",
  initialState,
  reducers: {
    setLocationId: (state, action) => { state.locationId = action.payload || null; },
    setSidebarCompact: (state, action) => { state.sidebarCompact = Boolean(action.payload); },
    setAISidebarCollapsed: (state, action) => { state.aiSidebarCollapsed = Boolean(action.payload); },
    setAppearance: (state, action) => {
      state.appearance = ["light", "dark", "system"].includes(action.payload) ? action.payload : "system";
    },
    setDashboardLayout: (state, action) => {
      const { key = "default", layout = [] } = action.payload || {};
      state.dashboardLayouts[key] = layout;
    },
    resetDashboardLayout: (state, action) => { delete state.dashboardLayouts[action.payload || "default"]; },
    clearTenantPreferences: (state) => { state.locationId = null; },
  },
});

export const { setLocationId, setSidebarCompact, setAISidebarCollapsed, setAppearance, setDashboardLayout, resetDashboardLayout, clearTenantPreferences } = preferencesSlice.actions;
export const selectLocationId = (state) => state.preferences.locationId;
export const selectSidebarCompact = (state) => state.preferences.sidebarCompact;
export const selectAISidebarCollapsed = (state) => state.preferences.aiSidebarCollapsed;
export const selectAppearance = (state) => state.preferences.appearance;
export const selectDashboardLayout = (key = "default") => (state) => state.preferences.dashboardLayouts[key] || null;
export const selectDashboardLayouts = (state) => state.preferences.dashboardLayouts;
export default preferencesSlice.reducer;
