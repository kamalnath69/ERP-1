const CHUNK_RECOVERY_KEY = "edvatiq.chunk-recovery-build.v1";

function currentBuildId(documentRef, locationRef) {
  const entryScript = Array.from(
    documentRef?.querySelectorAll?.('script[type="module"][src]') || [],
  ).find((script) => script.src.includes("/assets/"));

  return entryScript?.src || locationRef?.href || "unknown-build";
}

export function installChunkLoadRecovery({
  target = globalThis.window,
  storage = globalThis.window?.sessionStorage,
  documentRef = globalThis.document,
  locationRef = globalThis.location,
  reload = () => locationRef?.reload(),
  getBuildId = () => currentBuildId(documentRef, locationRef),
} = {}) {
  if (!target?.addEventListener || !storage) return () => {};

  let reloadStarted = false;

  const handlePreloadError = (event) => {
    if (reloadStarted) {
      event.preventDefault();
      return;
    }

    const buildId = getBuildId();

    try {
      if (storage.getItem(CHUNK_RECOVERY_KEY) === buildId) return;
      storage.setItem(CHUNK_RECOVERY_KEY, buildId);
    } catch {
      // Without session storage there is no reliable way to prevent a reload loop.
      return;
    }

    event.preventDefault();
    reloadStarted = true;
    reload();
  };

  target.addEventListener("vite:preloadError", handlePreloadError);
  return () => target.removeEventListener("vite:preloadError", handlePreloadError);
}

