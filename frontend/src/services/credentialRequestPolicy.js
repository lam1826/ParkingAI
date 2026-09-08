const PUBLIC_CREDENTIAL_PATHS = new Set(["/api/auth/login", "/api/auth/register"]);

export function shouldAttachAuthorization(url) {
  if (!url) return true;
  try {
    const path = new URL(String(url), "https://parkingai.local").pathname.replace(/\/$/, "");
    return !PUBLIC_CREDENTIAL_PATHS.has(path);
  } catch {
    return true;
  }
}
