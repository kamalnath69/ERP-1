import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "@/lib/api";

export const fetchWidgets = createAsyncThunk(
  "dashboard/widgets",
  async (_, { rejectWithValue }) => {
    try {
      const { data } = await api.get("/analytics/widgets");
      return data;
    } catch (e) {
      return rejectWithValue(e?.response?.data || { detail: "Failed" });
    }
  }
);

const initialState = {
  widgets: null,
  loading: false,
  lastLoadedAt: null,
  error: null,
};

const slice = createSlice({
  name: "dashboard",
  initialState,
  reducers: { clear: () => initialState },
  extraReducers: (b) => {
    b.addCase(fetchWidgets.pending, (s) => {
      s.loading = true;
      s.error = null;
    })
      .addCase(fetchWidgets.fulfilled, (s, a) => {
        s.loading = false;
        s.widgets = a.payload;
        s.lastLoadedAt = Date.now();
      })
      .addCase(fetchWidgets.rejected, (s, a) => {
        s.loading = false;
        s.error = a.payload?.detail || "Failed";
      });
  },
});

export const { clear } = slice.actions;
export const selectWidgets = (s) => s.dashboard.widgets;
export const selectDashboardLoading = (s) => s.dashboard.loading;
export default slice.reducer;
