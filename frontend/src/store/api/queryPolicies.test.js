import { QUERY_POLICIES } from "./queryPolicies";

describe("event-driven query policies", () => {
  test("do not poll while realtime synchronization is available", () => {
    Object.values(QUERY_POLICIES).forEach((policy) => {
      expect(policy.pollingInterval).toBeUndefined();
      expect(policy.refetchOnFocus).toBe(true);
      expect(policy.refetchOnReconnect).toBe(true);
    });
  });

  test("keeps reference data cached longer than operational data", () => {
    expect(QUERY_POLICIES.reference.refetchOnMountOrArgChange)
      .toBeGreaterThan(QUERY_POLICIES.operational.refetchOnMountOrArgChange);
  });
});
