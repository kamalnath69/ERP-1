const EVENT_DRIVEN_REFRESH = Object.freeze({
  refetchOnFocus: true,
  refetchOnReconnect: true,
});

// Realtime invalidation keeps mounted data current. These thresholds only
// verify stale cache entries when a screen is mounted again.
export const QUERY_POLICIES = Object.freeze({
  live: Object.freeze({
    ...EVENT_DRIVEN_REFRESH,
    refetchOnMountOrArgChange: 30,
  }),
  operational: Object.freeze({
    ...EVENT_DRIVEN_REFRESH,
    refetchOnMountOrArgChange: 60,
  }),
  collaborative: Object.freeze({
    ...EVENT_DRIVEN_REFRESH,
    refetchOnMountOrArgChange: 300,
  }),
  reference: Object.freeze({
    ...EVENT_DRIVEN_REFRESH,
    refetchOnMountOrArgChange: 600,
  }),
  analytical: Object.freeze({
    ...EVENT_DRIVEN_REFRESH,
    refetchOnMountOrArgChange: 300,
  }),
});

export function withSkip(policy, skip) {
  return { ...policy, skip };
}
