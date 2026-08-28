function normalizedUrl(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return text ? text.replace(/\/+$/, "") : "";
}


export function resolveApiBaseUrl({
  runtimeUrl,
  buildUrl,
  isDevelopment = false,
  locationOrigin = "",
} = {}) {
  const runtime = normalizedUrl(runtimeUrl);
  if (runtime) return runtime;

  const build = normalizedUrl(buildUrl);
  if (build) return build;

  if (isDevelopment) return "http://localhost:8000";

  // Same-origin is a safe production fallback: it never sends a user's
  // credentials to localhost or an arbitrary third-party host. A separate
  // API domain must be supplied through the CDN-generated config.js.
  return normalizedUrl(locationOrigin) || "/";
}
