import { useCallback, useEffect, useRef, useState } from "react";

const idleState = Object.freeze({
  conversationId: null,
  status: "idle",
  error: null,
});
const MAX_CANCELLATION_RETRIES = 1;

export function isCancelledHistoryRequest(error) {
  return error?.name === "AbortError"
    || error?.code === "ERR_CANCELED"
    || error?.status === "CANCELLED"
    || error?.error === "Aborted";
}

export default function useLatestConversationHistory({
  conversationId,
  hasCachedMessages = false,
  loadPage,
  onPage,
  limit = 50,
}) {
  const [state, setState] = useState(idleState);
  const requestRef = useRef(null);
  const sequenceRef = useRef(0);
  const conversationRef = useRef(conversationId);
  const cachedMessagesRef = useRef(hasCachedMessages);
  const onPageRef = useRef(onPage);

  conversationRef.current = conversationId;
  cachedMessagesRef.current = hasCachedMessages;
  onPageRef.current = onPage;

  const abortCurrent = useCallback(() => {
    sequenceRef.current += 1;
    const request = requestRef.current;
    requestRef.current = null;
    request?.abort?.();
  }, []);

  const run = useCallback((id, { preferCache = true, background = false } = {}) => {
    if (!id) return null;

    const startRequest = (useCachedValue, cancellationRetries = 0) => {
      abortCurrent();
      const sequence = sequenceRef.current;
      setState({
        conversationId: id,
        status: background ? "refreshing" : "loading",
        error: null,
      });

      let request;
      try {
        request = loadPage({ conversationId: id, limit }, useCachedValue);
        requestRef.current = request;
      } catch (error) {
        if (conversationRef.current === id && sequenceRef.current === sequence) {
          setState({ conversationId: id, status: "error", error });
        }
        return null;
      }

      const result = typeof request?.unwrap === "function"
        ? request.unwrap()
        : Promise.resolve(request);

      Promise.resolve(result)
        .then((page) => {
          if (sequenceRef.current !== sequence || conversationRef.current !== id) return;
          onPageRef.current?.(id, page || { items: [] });
          setState({ conversationId: id, status: "ready", error: null });
        })
        .catch((error) => {
          if (
            sequenceRef.current !== sequence
            || conversationRef.current !== id
          ) return;
          if (
            isCancelledHistoryRequest(error)
            && cancellationRetries < MAX_CANCELLATION_RETRIES
          ) {
            queueMicrotask(() => {
              if (
                sequenceRef.current === sequence
                && conversationRef.current === id
              ) {
                startRequest(false, cancellationRetries + 1);
              }
            });
            return;
          }
          setState({ conversationId: id, status: "error", error });
        })
        .finally(() => {
          if (sequenceRef.current === sequence && requestRef.current === request) {
            requestRef.current = null;
          }
        });

      return request;
    };

    return startRequest(preferCache);
  }, [abortCurrent, limit, loadPage]);

  useEffect(() => {
    if (!conversationId) {
      abortCurrent();
      setState(idleState);
      return undefined;
    }

    run(conversationId, {
      preferCache: true,
      background: cachedMessagesRef.current,
    });

    return () => {
      abortCurrent();
    };
  }, [abortCurrent, conversationId, run]);

  const refresh = useCallback(() => {
    if (!conversationId) return null;
    return run(conversationId, {
      preferCache: false,
      background: cachedMessagesRef.current,
    });
  }, [conversationId, run]);

  return {
    ...state,
    isLoading: state.status === "loading",
    isFetching: state.status === "loading" || state.status === "refreshing",
    refresh,
    abort: abortCurrent,
  };
}
