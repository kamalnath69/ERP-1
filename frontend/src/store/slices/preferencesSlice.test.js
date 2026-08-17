import reducer, {
  clearTenantPreferences,
  setAISidebarCollapsed,
  setAppearance,
  setLocationId,
  setSidebarPinned,
} from "./preferencesSlice";

describe("preferences slice", () => {
  const initial = { locationId: null, sidebarPinned: false };

  test("defaults first-time appearance to light", () => {
    expect(reducer(undefined, { type: "preferences/init" }).appearance).toBe("light");
  });

  test("stores the active business location", () => {
    expect(reducer(initial, setLocationId("location-1")).locationId).toBe("location-1");
  });

  test("keeps shell layout separate from tenant reset", () => {
    const state = { locationId: "location-1", sidebarPinned: true };
    expect(reducer(state, clearTenantPreferences())).toEqual({ locationId: null, sidebarPinned: true });
    expect(reducer(initial, setSidebarPinned(true)).sidebarPinned).toBe(true);
  });

  test("stores the AI history layout independently", () => {
    const state = { ...initial, aiSidebarCollapsed: false };
    expect(reducer(state, setAISidebarCollapsed(true)).aiSidebarCollapsed).toBe(true);
  });

  test("uses light mode when an unsupported appearance is supplied", () => {
    const state = { ...initial, appearance: "dark" };
    expect(reducer(state, setAppearance("unsupported")).appearance).toBe("light");
  });
});
