import { useCallback, useEffect, useRef, useState } from "react";

function mergeById(current, incoming) {
  const seen = new Set();
  return [...current, ...incoming].filter((item) => {
    const key = item?.id || item?.student_profile_id || item?.client_id;
    if (!key) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export default function useCursorPagination(filterKey) {
  const [pageState, setPageState] = useState({ key: filterKey, cursor: null, items: [] });
  const accepted = useRef(null);
  const current = pageState.key === filterKey ? pageState : { key: filterKey, cursor: null, items: [] };

  useEffect(() => {
    if (pageState.key === filterKey) return;
    accepted.current = null;
    setPageState({ key: filterKey, cursor: null, items: [] });
  }, [filterKey, pageState.key]);

  const accept = useCallback((page) => {
    if (!page || accepted.current === page) return;
    accepted.current = page;
    setPageState((state) => {
      if (state.key !== filterKey) return { key: filterKey, cursor: null, items: page.items || [] };
      return {
        ...state,
        items: state.cursor ? mergeById(state.items, page.items || []) : (page.items || []),
      };
    });
  }, [filterKey]);

  return {
    cursor: current.cursor,
    items: current.items,
    accept,
    reset: useCallback(() => {
      accepted.current = null;
      setPageState({ key: filterKey, cursor: null, items: [] });
    }, [filterKey]),
    loadMore: useCallback((nextCursor) => {
      if (!nextCursor) return;
      accepted.current = null;
      setPageState((state) => state.key === filterKey ? { ...state, cursor: nextCursor } : { key: filterKey, cursor: nextCursor, items: [] });
    }, [filterKey]),
  };
}
