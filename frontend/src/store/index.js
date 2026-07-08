import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./slices/authSlice";
import notificationsReducer from "./slices/notificationsSlice";
import studentsReducer from "./slices/studentsSlice";
import dashboardReducer from "./slices/dashboardSlice";
import aiReducer from "./slices/aiSlice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    notifications: notificationsReducer,
    students: studentsReducer,
    dashboard: dashboardReducer,
    ai: aiReducer,
  },
  middleware: (getDefault) =>
    getDefault({
      // Allow non-serializable payloads (e.g., File objects) in select actions if we add them later.
      serializableCheck: {
        ignoredActions: ["ai/streamChunkReceived"],
      },
    }),
});

export default store;
