import React, { createContext, useCallback, useContext, useEffect, useMemo } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useAuth } from "@/contexts/AuthContext";
import { useGetQuery } from "@/store/api/baseApi";
import { selectLocationId, setAppearance, setDashboardLayout, setLocationId as storeLocationId } from "@/store/slices/preferencesSlice";

const BusinessContext = createContext(null);

function errorMessage(error) {
  return error?.data?.detail || error?.message || null;
}

export function BusinessProvider({ children }) {
  const dispatch = useDispatch();
  const { user } = useAuth();
  const selectedLocationId = useSelector(selectLocationId);
  const skip = !user || user.is_super_admin;
  const query = useGetQuery(
    { url: "/organization/context" },
    { skip, refetchOnMountOrArgChange: 300 },
  );
  const context = skip ? null : query.data?.data || null;
  const locations = useMemo(() => context?.locations || [], [context?.locations]);

  const setLocationId = useCallback((value) => {
    dispatch(storeLocationId(value));
  }, [dispatch]);

  useEffect(() => {
    if (!context) return;
    const valid = locations.some((item) => item.id === selectedLocationId);
    if (!valid) setLocationId(locations[0]?.id || null);
  }, [context, locations, selectedLocationId, setLocationId]);

  useEffect(() => {
    const appearance = context?.preferences?.appearance?.value?.mode;
    if (["light", "dark", "system"].includes(appearance)) dispatch(setAppearance(appearance));
    const layouts = context?.preferences?.dashboard?.value?.layouts;
    if (layouts && typeof layouts === "object") {
      Object.entries(layouts).forEach(([key, layout]) => dispatch(setDashboardLayout({ key, layout })));
    }
  }, [context?.preferences, dispatch]);

  const location = locations.find((item) => item.id === selectedLocationId) || locations[0] || null;
  const hasModule = useCallback((module) => {
    const value = context?.entitlements?.values?.[`module.${module}`];
    return value == null ? context?.organization?.enabled_modules?.includes(module) : Boolean(value);
  }, [context]);

  const value = useMemo(() => ({
    context,
    organization: context?.organization,
    industry: context?.organization?.industry,
    locations,
    location,
    locationId: location?.id || null,
    setLocationId,
    loading: query.isLoading || (query.isFetching && !context),
    refreshing: query.isFetching && Boolean(context),
    error: errorMessage(query.error),
    refresh: query.refetch,
    entitlements: context?.entitlements,
    usage: context?.usage,
    wallet: context?.ai_wallet,
    hasModule,
  }), [context, hasModule, location, locations, query.error, query.isFetching, query.isLoading, query.refetch, setLocationId]);

  return <BusinessContext.Provider value={value}>{children}</BusinessContext.Provider>;
}

export function useBusiness() { return useContext(BusinessContext); }
