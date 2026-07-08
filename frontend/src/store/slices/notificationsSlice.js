import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "@/lib/api";

export const fetchNotifications = createAsyncThunk(
  "notifications/fetch",
  async (_, { rejectWithValue }) => {
    try {
      const { data } = await api.get("/notifications");
      return data;
    } catch (e) {
      return rejectWithValue(e?.response?.data || { detail: "Failed" });
    }
  }
);

export const markNotificationRead = createAsyncThunk(
  "notifications/markRead",
  async (id) => {
    await api.post(`/notifications/${id}/read`);
    return id;
  }
);

const initialState = {
  items: [],
  loading: false,
  error: null,
};

const slice = createSlice({
  name: "notifications",
  initialState,
  reducers: {
    prepend: (s, a) => {
      s.items = [a.payload, ...s.items];
    },
    clear: () => initialState,
  },
  extraReducers: (b) => {
    b.addCase(fetchNotifications.pending, (s) => {
      s.loading = true;
      s.error = null;
    })
      .addCase(fetchNotifications.fulfilled, (s, a) => {
        s.loading = false;
        s.items = a.payload || [];
      })
      .addCase(fetchNotifications.rejected, (s, a) => {
        s.loading = false;
        s.error = a.payload?.detail || "Failed";
      })
      .addCase(markNotificationRead.fulfilled, (s, a) => {
        const n = s.items.find((x) => x.id === a.payload);
        if (n) n.is_read = true;
      });
  },
});

export const { prepend, clear } = slice.actions;
export const selectUnreadCount = (s) => s.notifications.items.filter((n) => !n.is_read).length;
export const selectNotifications = (s) => s.notifications.items;
export default slice.reducer;
