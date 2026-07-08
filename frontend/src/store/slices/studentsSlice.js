import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "@/lib/api";

export const fetchStudents = createAsyncThunk(
  "students/fetch",
  async (q, { rejectWithValue }) => {
    try {
      const { data } = await api.get("/students", { params: q ? { q } : {} });
      return data;
    } catch (e) {
      return rejectWithValue(e?.response?.data || { detail: "Failed" });
    }
  }
);

const initialState = {
  items: [],
  loading: false,
  query: "",
  error: null,
  selectedId: null,
};

const slice = createSlice({
  name: "students",
  initialState,
  reducers: {
    setQuery: (s, a) => {
      s.query = a.payload;
    },
    setSelected: (s, a) => {
      s.selectedId = a.payload;
    },
    upsert: (s, a) => {
      const idx = s.items.findIndex((x) => x.id === a.payload.id);
      if (idx >= 0) s.items[idx] = a.payload;
      else s.items.unshift(a.payload);
    },
  },
  extraReducers: (b) => {
    b.addCase(fetchStudents.pending, (s) => {
      s.loading = true;
      s.error = null;
    })
      .addCase(fetchStudents.fulfilled, (s, a) => {
        s.loading = false;
        s.items = a.payload || [];
      })
      .addCase(fetchStudents.rejected, (s, a) => {
        s.loading = false;
        s.error = a.payload?.detail || "Failed";
      });
  },
});

export const { setQuery, setSelected, upsert } = slice.actions;
export const selectStudents = (s) => s.students.items;
export default slice.reducer;
