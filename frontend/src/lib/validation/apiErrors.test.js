import { describe, expect, it } from "vitest";
import { normalizeApiError } from "@/lib/validation/apiErrors";

describe("normalizeApiError transport failures", () => {
  it("turns network failures into a retryable message", () => {
    const result = normalizeApiError({
      code: "ERR_NETWORK",
      response: { status: 0, data: { detail: "Network Error" } },
    });

    expect(result.message).toBe("Could not reach Edvatiq. Check your connection and try again.");
  });

  it("turns request deadlines into a retryable message", () => {
    const result = normalizeApiError({
      code: "ECONNABORTED",
      response: { status: 0, data: { detail: "timeout of 15000ms exceeded" } },
    });

    expect(result.message).toBe("Edvatiq took too long to respond. Please try again.");
  });

  it("keeps an API credential error", () => {
    const result = normalizeApiError({
      response: { status: 401, data: { detail: "Invalid credentials" } },
    });

    expect(result.message).toBe("Invalid credentials");
  });
});
