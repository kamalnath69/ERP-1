import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { API_BASE } from "@/lib/http";
import { baseApi, tagsForUrl } from "@/store/api/baseApi";

export const REALTIME_FALLBACK_MS = 60_000;
const CONNECTION_GRACE_MS = 10_000;
const FALLBACK_RESOURCES = ["notifications", "appointments", "gym", "clinic", "dashboard"];
const RECONNECT_RESOURCES = [
  "auth", "business", "dashboard", "notifications", "appointments", "clients",
  "team", "catalog", "sales", "gym", "clinic", "documents", "ai", "reports",
  "billing", "access",
];

const resourceTags = (resources) => resources.map((id) => ({ type: "Resource", id }));

export default function RealtimeSync() {
  const dispatch = useDispatch();

  useEffect(() => {
    if (typeof EventSource === "undefined") return undefined;
    const source = new EventSource(`${API_BASE}/events`, { withCredentials: true });
    let fallbackTimer;
    let hasConnected = false;
    let wasDisconnected = false;

    const refresh = (resources) => {
      dispatch(baseApi.util.invalidateTags(resourceTags(resources)));
    };
    const canRefresh = () =>
      document.visibilityState === "visible" && navigator.onLine !== false;
    const stopFallback = () => {
      if (fallbackTimer) clearInterval(fallbackTimer);
      fallbackTimer = undefined;
    };
    const startFallback = () => {
      if (fallbackTimer) return;
      fallbackTimer = setInterval(() => {
        if (canRefresh()) refresh(FALLBACK_RESOURCES);
      }, REALTIME_FALLBACK_MS);
    };
    const invalidate = (event) => {
      try {
        const payload = JSON.parse(event.data);
        dispatch(baseApi.util.invalidateTags(tagsForUrl(payload.path, true)));
      } catch {}
    };
    const opened = () => {
      stopFallback();
      if (hasConnected && wasDisconnected) refresh(RECONNECT_RESOURCES);
      hasConnected = true;
      wasDisconnected = false;
    };
    const failed = () => {
      wasDisconnected = true;
      startFallback();
    };
    const connectionTimer = setTimeout(() => {
      if (!hasConnected) startFallback();
    }, CONNECTION_GRACE_MS);

    source.addEventListener("open", opened);
    source.addEventListener("error", failed);
    source.addEventListener("invalidate", invalidate);
    return () => {
      clearTimeout(connectionTimer);
      stopFallback();
      source.removeEventListener("open", opened);
      source.removeEventListener("error", failed);
      source.removeEventListener("invalidate", invalidate);
      source.close();
    };
  }, [dispatch]);

  return null;
}
