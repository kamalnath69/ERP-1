import { configureStore } from "@reduxjs/toolkit";
import http from "../../lib/http";
import { baseApi, resourceForUrl, tagsForUrl } from "./baseApi";

jest.mock("../../lib/http", () => ({
  __esModule: true,
  default: { request: jest.fn() },
}));

function testStore() {
  return configureStore({
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefault) => getDefault().concat(baseApi.middleware),
  });
}

describe("shared RTK Query API", () => {
  beforeEach(() => {
    http.request.mockReset();
    http.request.mockResolvedValue({ data: { items: [] }, status: 200, statusText: "OK", headers: {} });
  });

  test("maps every API area to a stable module cache", () => {
    expect(resourceForUrl("/inventory?location_id=1")).toBe("inventory");
    expect(resourceForUrl("/client-signals/123")).toBe("clients");
    expect(resourceForUrl("/super-admin/organizations")).toBe("super-admin");
  });

  test("invalidates dependent dashboards after a sale", () => {
    expect(tagsForUrl("/sales/123/payments", true).map((tag) => tag.id)).toEqual([
      "sales", "catalog", "clients", "dashboard", "reports",
    ]);
  });

  test("deduplicates concurrent reads with identical arguments", async () => {
    const store = testStore();
    const args = { url: "/clients", params: { location_id: "loc-1" } };
    const first = store.dispatch(baseApi.endpoints.get.initiate(args, { subscribe: false }));
    const second = store.dispatch(baseApi.endpoints.get.initiate(args, { subscribe: false }));

    await Promise.all([first.unwrap(), second.unwrap()]);

    expect(http.request).toHaveBeenCalledTimes(1);
  });

  test("reuses a fulfilled query after a screen unsubscribes and remounts", async () => {
    const store = testStore();
    const args = { url: "/reports/summary", params: { location_id: "loc-1", start: "2026-08-01" } };
    const first = store.dispatch(baseApi.endpoints.get.initiate(args));
    await first.unwrap();
    first.unsubscribe();

    const second = store.dispatch(baseApi.endpoints.get.initiate(args));
    await second.unwrap();
    second.unsubscribe();

    expect(http.request).toHaveBeenCalledTimes(1);
  });
});
