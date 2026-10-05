// The page ErrorBoundary in MainLayout is remounted per pathname, but customer
// destinations share one pathname (/portal?tab=fees, ?tab=support, ...). A shown
// error is therefore also cleared when the location changes AFTER the error was
// shown (a menu click leaves the broken view). An error raised by that same
// navigation stays shown, so a view that keeps failing cannot loop.

/** Location identity for the page boundary: path and query, not the #hash. */
export function pageBoundaryResetKey(location) {
  return `${location?.pathname ?? ""}${location?.search ?? ""}`;
}

export function shouldResetErrorBoundary({ prevResetKey, resetKey, hadError, hasError }) {
  return Boolean(hadError && hasError && prevResetKey !== resetKey);
}
