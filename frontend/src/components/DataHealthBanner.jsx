import React from "react";
import { useDispatch, useSelector } from "react-redux";
import { Button } from "@/components/ui/button";
import { WarningCircle } from "@phosphor-icons/react";
import { baseApi } from "@/store/api/baseApi";
import { cn } from "@/lib/utils";

export function isCancelledQuery(query) {
  return query?.error?.status === "CANCELLED"
    || query?.error?.code === "ERR_CANCELED"
    || query?.error?.name === "AbortError";
}

export function selectDegradedQueries(state) {
  const apiState = state[baseApi.reducerPath];
  if (!apiState) return [];
  const subscriptions = apiState.subscriptions || {};
  return Object.entries(apiState.queries || {})
    .filter(([cacheKey, query]) => {
      const active = Object.keys(subscriptions[cacheKey] || {}).length > 0;
      return active
        && !isCancelledQuery(query)
        && (query?.status === "rejected" || query?.data?._sync?.partial);
    })
    .map(([, query]) => ({ endpointName: query.endpointName, originalArgs: query.originalArgs, hasData: query.data !== undefined }));
}

export default function DataHealthBanner({ className }) {
  const dispatch = useDispatch();
  const degraded = useSelector(selectDegradedQueries);
  if (!degraded.length) return null;
  const hasUnavailableData = degraded.some((query) => !query.hasData);

  const retry = () => {
    degraded.forEach(({ endpointName, originalArgs }) => {
      const endpoint = baseApi.endpoints[endpointName];
      if (!endpoint) return;
      const request = dispatch(endpoint.initiate(originalArgs, { subscribe: false, forceRefetch: true }));
      request.finally(() => request.unsubscribe?.());
    });
  };

  return <div role="status" className={cn("mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-300/60 bg-amber-50 px-4 py-3 text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-100", className)}>
    <div className="flex items-center gap-2 text-sm"><WarningCircle weight="fill" />{hasUnavailableData ? "Some information could not be loaded. Please try again." : "Some information could not be refreshed. The latest available information is still shown."}</div>
    <Button type="button" size="sm" variant="outline" className="rounded-lg" onClick={retry}>Try again</Button>
  </div>;
}
