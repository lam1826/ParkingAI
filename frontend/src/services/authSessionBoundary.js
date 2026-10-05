export const AUTH_SESSION_CHANGED = "parking-auth-session-changed";

export function notifyAuthSessionChanged(eventTarget = globalThis.window) {
  eventTarget?.dispatchEvent(new Event(AUTH_SESSION_CHANGED));
}

export function isCurrentAuthFailure(authorization, currentToken) {
  return Boolean(currentToken && authorization === `Bearer ${currentToken}`);
}

// A 401 for the CURRENT token ends the session locally. It deliberately does
// not navigate: the session event makes AuthProvider reset, after which public
// pages keep rendering and PrivateRoute redirects with a ?next= continuation.
export function expireCurrentSession({ authorization, storage, clearChat, notify }) {
  if (!isCurrentAuthFailure(authorization, storage.getItem("token"))) return false;
  storage.removeItem("token");
  storage.removeItem("user");
  clearChat();
  notify();
  return true;
}

// Own the account boundary outside React so local login, expiry and other tabs
// all invalidate old requests before a new profile is allowed into the UI.
// Backoff for a kept token whose profile could not be loaded (timeout, network
// drop, 5xx). A 401 is not retried: it ends the session.
export const PROFILE_RETRY_DELAYS_MS = [1000, 2000, 5000, 10000, 30000];

export function createAuthSessionBoundary({
  storage, eventTarget, fetchProfile, onReset, onUser, onLoading,
  onProfileError = () => {},
  retryDelays = PROFILE_RETRY_DELAYS_MS,
  setTimer = (callback, delay) => setTimeout(callback, delay),
  clearTimer = (timer) => clearTimeout(timer),
}) {
  let token = undefined;
  let profile = null;
  let version = 0;
  let loginVersion = 0;
  let stopped = true;
  let retryTimer = null;
  let retryAttempt = 0;

  function cancelRetry() {
    if (retryTimer !== null) clearTimer(retryTimer);
    retryTimer = null;
  }

  function scheduleRetry() {
    if (stopped || retryTimer !== null) return;
    const delay = retryDelays[Math.min(retryAttempt, retryDelays.length - 1)];
    retryAttempt++;
    const retryToken = token;
    retryTimer = setTimer(() => {
      retryTimer = null;
      // Same token, so this is not a session change: it must not invalidate a
      // login submitted meanwhile (refresh() would bump loginVersion).
      if (!stopped && !profile && retryToken && storage.getItem("token") === retryToken) {
        void loadProfile().catch(() => {});
      }
    }, delay);
  }

  // An explicit refresh (start, session event, logout, login, profile edit)
  // supersedes any login still waiting for its token.
  async function refresh() {
    if (stopped) throw new Error("Phiên đăng nhập đã thay đổi.");
    loginVersion++;
    return loadProfile();
  }

  async function loadProfile() {
    if (stopped) throw new Error("Phiên đăng nhập đã thay đổi.");
    const requestToken = storage.getItem("token");
    const requestVersion = ++version;
    const changed = requestToken !== token;
    if (changed) {
      token = requestToken;
      profile = null;
      cancelRetry();
      retryAttempt = 0;
      onProfileError(null);
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
      cancelRetry();
      retryAttempt = 0;
      onProfileError(null);
      storage.setItem("user", JSON.stringify(nextProfile));
      onUser(nextProfile);
      onLoading(false);
      return nextProfile;
    } catch (error) {
      // A late old-token error must not remove a newer tab's session.
      if (isCurrent()) {
        if (!profile && error?.response?.status === 401) {
          storage.removeItem("token");
          storage.removeItem("user");
          token = null;
          onReset();
        } else if (!profile) {
          // Token kept but no account yet: report it and retry instead of
          // rendering role-gated pages for a user that never loaded.
          onProfileError(error);
          scheduleRetry();
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
    end(expectedToken) {
      // A delayed password-change response belongs to the session that sent it.
      // It must not log out an account signed in meanwhile in another tab.
      if (stopped || (expectedToken !== undefined && storage.getItem("token") !== expectedToken)) return false;
      storage.removeItem("token");
      storage.removeItem("user");
      void refresh().catch(() => {});
      return true;
    },
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
      cancelRetry();
      version++;
      loginVersion++;
      eventTarget.removeEventListener("storage", handleSessionChange);
      eventTarget.removeEventListener(AUTH_SESSION_CHANGED, handleSessionChange);
    },
  };
}

// What a failed login may write to the console: never the error itself. An
// AxiosError carries its request config, i.e. the typed password (config.data of
// POST /api/auth/login) and, when the profile load failed after the token was
// issued, `Authorization: Bearer <token>` of /api/auth/me (review 05/10 round 3).
export function loginFailureLogDetails(error) {
  const status = Number(error?.response?.status);
  const code = typeof error?.code === "string" && /^[A-Z][A-Z0-9_]{0,39}$/.test(error.code) ? error.code : null;
  return { status: Number.isInteger(status) && status > 0 ? status : null, code };
}

// AuthProvider.login without React: the profile refresh resets (remounts) the
// login page, so a failure after the token was issued is handed to onFailure
// (provider state) BEFORE the final reset; the new page can then show it.
export async function loginWithSession({ session, storage, authenticate, credentials, describeError, onFailure }) {
  const isCurrentAttempt = session.beginLogin();
  let issuedToken = null;
  try {
    const data = await authenticate(credentials);
    if (!isCurrentAttempt()) throw new Error("Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.");
    issuedToken = data.access_token;
    // Store the token first so the request interceptor attaches it to /api/auth/me.
    storage.setItem("token", issuedToken);
    const profile = await session.refresh();
    return { success: true, profile };
  } catch (error) {
    const message = describeError(error, { afterToken: Boolean(issuedToken) });
    if (issuedToken && storage.getItem("token") === issuedToken) {
      onFailure({ message, username: String(credentials?.username ?? "").trim() });
      storage.removeItem("token");
      storage.removeItem("user");
      await session.refresh().catch(() => null);
    }
    return { success: false, message, error };
  }
}
