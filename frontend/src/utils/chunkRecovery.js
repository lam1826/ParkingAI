import { lazy } from "react";

const RELOAD_MARKER = "parkingai:chunk-reload";

export function isChunkLoadError(error) {
  const message = String(error?.message || error || "").toLowerCase();
  return message.includes("dynamically imported module")
    || message.includes("failed to fetch module")
    || message.includes("importing a module script failed")
    || message.includes("chunkloaderror")
    || message.includes("vite:preloaderror");
}

export function recoverChunkError(error, {
  storage = globalThis.sessionStorage,
  location = globalThis.location,
} = {}) {
  if (!isChunkLoadError(error) || !storage || !location?.reload) return false;
  const current = String(location.href || "");
  if (storage.getItem(RELOAD_MARKER) === current) return false;
  storage.setItem(RELOAD_MARKER, current);
  location.reload();
  return true;
}

export function lazyWithRecovery(importer) {
  return lazy(async () => {
    try {
      const loaded = await importer();
      globalThis.sessionStorage?.removeItem(RELOAD_MARKER);
      return loaded;
    } catch (error) {
      if (recoverChunkError(error)) return new Promise(() => {});
      throw error;
    }
  });
}
