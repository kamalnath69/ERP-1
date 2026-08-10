import reducer, {
  clearTenantPreferences,
  setAISidebarCollapsed,
  setLocationId,
  setSidebarCompact,
} from "./preferencesSlice";

describe("preferences slice", () => {
  const initial = { locationId: null, sidebarCompact: false };

  test("stores the active business location", () => {
    expect(reducer(initial, setLocationId("location-1")).locationId).toBe("location-1");
  });

  test("keeps shell layout separate from tenant reset", () => {
    const state = { locationId: "location-1", sidebarCompact: true };
    expect(reducer(state, clearTenantPreferences())).toEqual({ locationId: null, sidebarCompact: true });
    expect(reducer(initial, setSidebarCompact(true)).sidebarCompact).toBe(true);
  });

  test("stores the AI history layout independently", () => {
    const state = { ...initial, aiSidebarCollapsed: false };
    expect(reducer(state, setAISidebarCollapsed(true)).aiSidebarCollapsed).toBe(true);
  });
});
