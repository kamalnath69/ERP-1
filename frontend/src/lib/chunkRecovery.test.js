import { installChunkLoadRecovery } from "./chunkRecovery";

function preloadError() {
  return new Event("vite:preloadError", { cancelable: true });
}

test("reloads once when a deployed build references a missing chunk", () => {
  const target = new EventTarget();
  const storage = new Map();
  const reload = vi.fn();
  const storageAdapter = {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
  };

  const uninstall = installChunkLoadRecovery({
    target,
    storage: storageAdapter,
    reload,
    getBuildId: () => "entry-build-a.js",
  });

  const firstError = preloadError();
  target.dispatchEvent(firstError);
  target.dispatchEvent(preloadError());

  expect(firstError.defaultPrevented).toBe(true);
  expect(reload).toHaveBeenCalledTimes(1);
  uninstall();
});

test("does not enter a reload loop for the same deployed build", () => {
  const target = new EventTarget();
  const storage = new Map([["edvatiq.chunk-recovery-build.v1", "entry-build-a.js"]]);
  const reload = vi.fn();

  installChunkLoadRecovery({
    target,
    storage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
    },
    reload,
    getBuildId: () => "entry-build-a.js",
  });

  const repeatedError = preloadError();
  target.dispatchEvent(repeatedError);

  expect(repeatedError.defaultPrevented).toBe(false);
  expect(reload).not.toHaveBeenCalled();
});

