import { configureStore } from "@reduxjs/toolkit";
import http from "../../lib/http";
import { baseApi } from "./baseApi";
import { workspaceApi } from "./workspaceApi";

vi.mock("../../lib/http", () => ({
  __esModule: true,
  default: { request: vi.fn() },
}));

function testStore() {
  return configureStore({
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefault) => getDefault().concat(baseApi.middleware),
  });
}

const response = (data) => ({ data, status: 200, statusText: "OK", headers: {} });
const failure = (message) => Object.assign(new Error(message), {
  response: { status: 503, data: { detail: message } },
});

describe("resilient workspace queries", () => {
  beforeEach(() => {
    http.request.mockReset();
  });

  test("returns usable data and identifies a failed dependency", async () => {
    http.request.mockImplementation(({ url }) => url === "/appointments"
      ? Promise.reject(failure("Appointments unavailable"))
      : Promise.resolve(response(
        url === "/clients" ? { items: [{ id: "client-1" }] }
          : url === "/employees" ? { items: [{ id: "employee-1" }] }
            : [{ id: "service-1" }],
      )));
    const store = testStore();

    const result = await store.dispatch(workspaceApi.endpoints.getCalendarWorkspace.initiate({ locationId: "loc-1", day: "2026-08-04" })).unwrap();

    expect(result.clientsResponse.items[0].id).toBe("client-1");
    expect(result._sync.partial).toBe(true);
    expect(result._sync.failures.appointments.status).toBe(503);
  });

  test("keeps last-known-good fields when a background refresh is partial", async () => {
    let refresh = false;
    http.request.mockImplementation(({ url }) => {
      if (!refresh) {
        if (url === "/appointments") return Promise.resolve(response([{ id: "appt-1" }]));
        if (url === "/clients") return Promise.resolve(response({ items: [{ id: "client-1" }] }));
        if (url === "/employees") return Promise.resolve(response({ items: [{ id: "employee-1" }] }));
        return Promise.resolve(response([{ id: "service-1" }]));
      }
      if (url === "/appointments") return Promise.reject(failure("Appointments unavailable"));
      if (url === "/clients") return Promise.resolve(response({ items: [{ id: "client-2" }] }));
      if (url === "/employees") return Promise.resolve(response({ items: [{ id: "employee-2" }] }));
      return Promise.resolve(response([{ id: "service-2" }]));
    });
    const store = testStore();
    const args = { locationId: "loc-1", day: "2026-08-04" };
    const subscription = store.dispatch(workspaceApi.endpoints.getCalendarWorkspace.initiate(args));
    await subscription.unwrap();
    refresh = true;
    await store.dispatch(workspaceApi.endpoints.getCalendarWorkspace.initiate(args, { forceRefetch: true })).unwrap();

    const cached = workspaceApi.endpoints.getCalendarWorkspace.select(args)(store.getState()).data;
    expect(cached.appointments[0].id).toBe("appt-1");
    expect(cached.clientsResponse.items[0].id).toBe("client-2");
    expect(cached.services[0].id).toBe("service-2");
    expect(cached._sync.partial).toBe(true);
    subscription.unsubscribe();
  });

  test("reuses shared client reference data across module navigation", async () => {
    http.request.mockResolvedValue(response({ items: [{ id: "client-1" }] }));
    const store = testStore();
    const args = { locationId: "loc-1", q: "", limit: 100 };
    const clientsPage = store.dispatch(workspaceApi.endpoints.getClients.initiate(args));
    await clientsPage.unwrap();
    clientsPage.unsubscribe();

    const salesPage = store.dispatch(workspaceApi.endpoints.getClients.initiate(args));
    await salesPage.unwrap();
    salesPage.unsubscribe();

    expect(http.request).toHaveBeenCalledTimes(1);
  });
});
