import { configureStore } from "@reduxjs/toolkit";
import { beforeEach, describe, expect, test, vi } from "vitest";

import api from "@/lib/api";
import authReducer, { loginThunk } from "@/store/slices/authSlice";

vi.mock("@/lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

function authStore() {
  return configureStore({ reducer: { auth: authReducer } });
}

const credentials = {
  email: "owner@example.com",
  password: "Secret123!",
  org_slug: "example",
  mfa_code: "",
};

describe("login session lifecycle", () => {
  beforeEach(() => {
    api.get.mockReset();
    api.post.mockReset();
  });

  test("hydrates the complete authorized session before completing login", async () => {
    const user = { id: "user-1", email: credentials.email };
    api.post.mockResolvedValue({ data: { user } });
    api.get.mockResolvedValue({
      data: { user, organization: { id: "org-1" }, permissions: ["ai.use"], roles: [], access_context: null },
    });

    const store = authStore();
    const result = await store.dispatch(loginThunk(credentials));

    expect(loginThunk.fulfilled.match(result)).toBe(true);
    expect(store.getState().auth.user).toEqual(user);
    expect(store.getState().auth.permissions).toEqual(["ai.use"]);
  });

  test("preserves a credential error for an immediate retry", async () => {
    const error = Object.assign(new Error("Invalid credentials"), {
      response: { status: 401, data: { detail: "Invalid credentials" } },
    });
    api.post.mockRejectedValue(error);

    const result = await authStore().dispatch(loginThunk(credentials));

    expect(loginThunk.rejected.match(result)).toBe(true);
    expect(result.payload).toMatchObject({ detail: "Invalid credentials", status: 401 });
  });

  test("does not complete navigation state when workspace hydration fails", async () => {
    api.post.mockResolvedValue({ data: { user: { id: "user-1" } } });
    const error = Object.assign(new Error("Network Error"), {
      code: "ERR_NETWORK",
      response: { status: 0, data: { detail: "Network Error" } },
    });
    api.get.mockRejectedValue(error);

    const store = authStore();
    const result = await store.dispatch(loginThunk(credentials));

    expect(loginThunk.rejected.match(result)).toBe(true);
    expect(result.payload).toMatchObject({ code: "ERR_NETWORK", status: 0 });
    expect(result.payload.display_detail).toContain("workspace could not be loaded");
    expect(store.getState().auth.user).toBeNull();
  });
});
