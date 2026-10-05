import { defaultLanding, sanitizeNextPath } from "../../utils/safeNext.js";

// Customer-only screens: an internal account sent there sees a customer page
// whose actions the server rejects (customer_only), so it lands on its own home.
const CUSTOMER_ONLY_PATHS = new Set(["/portal", "/reservations"]);

/** Where login navigates: a safe continuation the role can use, else the role landing. */
export function postLoginDestination(next, role) {
  const safe = sanitizeNextPath(next);
  if (!safe) return defaultLanding(role);
  if (role !== "customer") {
    const pathname = new URL(safe, "http://parkingai.invalid").pathname.replace(/\/+$/, "") || "/";
    if (CUSTOMER_ONLY_PATHS.has(pathname)) return defaultLanding(role);
  }
  return safe;
}
