import { configureStore, createListenerMiddleware, isAnyOf } from "@reduxjs/toolkit";
import { setupListeners } from "@reduxjs/toolkit/query";
import { bindApiDispatch } from "@/lib/api";
import { baseApi } from "./api/baseApi";
import { setupCacheSync } from "./api/cacheSync";
import authReducer from "./slices/authSlice";
import preferencesReducer, { clearTenantPreferences, resetDashboardLayout, setAISidebarCollapsed, setAppearance, setDashboardLayout, setLocationId, setSidebarCompact } from "./slices/preferencesSlice";
import aiReducer from "./slices/aiSlice";

const persistence = createListenerMiddleware();

persistence.startListening({
  matcher: isAnyOf(setLocationId, clearTenantPreferences),
  effect: (_action, listenerApi) => {
    const locationId = listenerApi.getState().preferences.locationId;
    if (locationId) localStorage.setItem("edvatiq.location", locationId);
    else localStorage.removeItem("edvatiq.location");
  },
});

persistence.startListening({
  matcher: isAnyOf(setDashboardLayout, resetDashboardLayout),
  effect: (_action, listenerApi) => {
    localStorage.setItem("edvatiq.dashboard.layouts", JSON.stringify(listenerApi.getState().preferences.dashboardLayouts));
  },
});

persistence.startListening({
  actionCreator: setAppearance,
  effect: (_action, listenerApi) => {
    localStorage.setItem("edvatiq.appearance", listenerApi.getState().preferences.appearance);
  },
});

persistence.startListening({
  actionCreator: setAISidebarCollapsed,
  effect: (_action, listenerApi) => {
    localStorage.setItem("edvatiq.ai.sidebar", listenerApi.getState().preferences.aiSidebarCollapsed ? "collapsed" : "expanded");
  },
});

persistence.startListening({
  actionCreator: setSidebarCompact,
  effect: (_action, listenerApi) => {
    localStorage.setItem("edvatiq.sidebar", listenerApi.getState().preferences.sidebarCompact ? "compact" : "full");
  },
});

export const store = configureStore({
  reducer: {
    auth: authReducer,
    preferences: preferencesReducer,
    aiWorkspace: aiReducer,
    [baseApi.reducerPath]: baseApi.reducer,
  },
  middleware: (getDefault) =>
    getDefault({
      serializableCheck: true,
    }).prepend(persistence.middleware).concat(baseApi.middleware),
});

bindApiDispatch(store.dispatch);
setupListeners(store.dispatch);
setupCacheSync(store.dispatch, baseApi);

export default store;
