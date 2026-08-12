import { useCallback, useRef, useState } from "react";

export function usePendingAction() {
  const active = useRef(new Set());
  const [, render] = useState(0);

  const run = useCallback(async (key, action) => {
    if (active.current.has(key)) return undefined;
    active.current.add(key);
    render((value) => value + 1);
    try {
      return await action();
    } finally {
      active.current.delete(key);
      render((value) => value + 1);
    }
  }, []);

  const isPending = useCallback((key) => active.current.has(key), []);
  return { run, isPending, anyPending: active.current.size > 0 };
}

export function useStableIdempotencyKey() {
  const key = useRef(crypto.randomUUID());
  const reset = useCallback(() => { key.current = crypto.randomUUID(); }, []);
  return { current: () => key.current, reset };
}
