export const AUTH_SESSION_CHANGED = "parking-auth-session-changed";

export function notifyAuthSessionChanged(eventTarget = globalThis.window) {
  eventTarget?.dispatchEvent(new Event(AUTH_SESSION_CHANGED));
}

export function isCurrentAuthFailure(authorization, currentToken) {
  return Boolean(currentToken && authorization === `Bearer ${currentToken}`);
}

// Own the account boundary outside React so local login, expiry and other tabs
// all invalidate old requests before a new profile is allowed into the UI.
export function createAuthSessionBoundary({ storage, eventTarget, fetchProfile, onReset, onUser, onLoading }) {
  let token = undefined;
  let profile = null;
  let version = 0;
  let loginVersion = 0;
  let stopped = true;

  async function refresh() {
    if (stopped) throw new Error("Phiên đăng nhập đã thay đổi.");
    loginVersion++;
    const requestToken = storage.getItem("token");
    const requestVersion = ++version;
    const changed = requestToken !== token;
    if (changed) {
      token = requestToken;
      profile = null;
      storage.removeItem("user");
      onReset();
      onLoading(Boolean(requestToken));
    }
    if (!requestToken) {
      storage.removeItem("user");
      onUser(null);
      onLoading(false);
      return null;
    }

    const isCurrent = () => !stopped && requestVersion === version && requestToken === storage.getItem("token");
    try {
      const nextProfile = await fetchProfile();
      if (!isCurrent()) throw new Error("Phiên đăng nhập đã thay đổi.");
      if (profile && profile.id !== nextProfile.id) onReset();
      profile = nextProfile;
      storage.setItem("user", JSON.stringify(nextProfile));
      onUser(nextProfile);
      onLoading(false);
      return nextProfile;
    } catch (error) {
      // A late old-token error must not remove a newer tab's session.
      if (isCurrent()) {
        if (!profile) {
          storage.removeItem("token");
          storage.removeItem("user");
          token = null;
          onReset();
        }
        onLoading(false);
      }
      throw error;
    }
  }

  function handleSessionChange(event) {
    if (event.type === "storage" && (
      (event.storageArea && event.storageArea !== storage) ||
      (event.key !== null && event.key !== "token")
    )) return;
    // Read the actual token: queued storage events may describe an older write.
    if (storage.getItem("token") !== token) void refresh().catch(() => {});
  }

  return {
    refresh,
    beginLogin() {
      const attempt = ++loginVersion;
      const previousToken = storage.getItem("token");
      return () => !stopped && attempt === loginVersion && previousToken === storage.getItem("token");
    },
    start() {
      stopped = false;
      eventTarget.addEventListener("storage", handleSessionChange);
      eventTarget.addEventListener(AUTH_SESSION_CHANGED, handleSessionChange);
      return refresh().catch(() => null);
    },
    stop() {
      stopped = true;
      version++;
      loginVersion++;
      eventTarget.removeEventListener("storage", handleSessionChange);
      eventTarget.removeEventListener(AUTH_SESSION_CHANGED, handleSessionChange);
    },
  };
}
