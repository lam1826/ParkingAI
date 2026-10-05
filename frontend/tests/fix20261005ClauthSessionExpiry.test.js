// CL-AUTH #31: an expired stored token is cleared quietly; React routing (not a
// hard jump to bare /login) decides where to go, so public pages stay public and
// private deep links keep ?next=.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createAuthSessionBoundary, expireCurrentSession } from "../src/services/authSessionBoundary.js";
import { withNext } from "../src/utils/safeNext.js";

function memoryStorage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)), removeItem: (key) => values.delete(key) };
}

test("only the current token's 401 ends the session, without navigating", () => {
  const storage = memoryStorage();
  const calls = [];
  storage.setItem("token", "stale");
  storage.setItem("user", "{}");
  const hooks = { clearChat: () => calls.push("chat"), notify: () => calls.push("notify") };
  assert.equal(expireCurrentSession({ authorization: "Bearer other", storage, ...hooks }), false);
  assert.equal(storage.getItem("token"), "stale");
  assert.equal(expireCurrentSession({ authorization: undefined, storage, ...hooks }), false);
  assert.equal(expireCurrentSession({ authorization: "Bearer stale", storage, ...hooks }), true);
  assert.equal(storage.getItem("token"), null);
  assert.equal(storage.getItem("user"), null);
  assert.deepEqual(calls, ["chat", "notify"]);
});

test("a stale token at startup resets the session and stops loading so routes can render", async () => {
  const storage = memoryStorage();
  const events = new EventTarget();
  const state = { user: "unset", loading: true, resets: 0 };
  const boundary = createAuthSessionBoundary({
    storage, eventTarget: events,
    // Same order as the real app: the axios interceptor runs before refresh() sees the error.
    fetchProfile: async () => {
      expireCurrentSession({ authorization: "Bearer stale", storage, clearChat: () => {}, notify: () => events.dispatchEvent(new Event("parking-auth-session-changed")) });
      throw Object.assign(new Error("401"), { response: { status: 401 } });
    },
    onReset: () => { state.resets++; },
    onUser: (user) => { state.user = user; },
    onLoading: (loading) => { state.loading = loading; },
  });
  storage.setItem("token", "stale");
  await boundary.start();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(storage.getItem("token"), null);
  assert.equal(state.loading, false);
  assert.equal(state.user, null);
  assert.ok(state.resets >= 2, "the provider remounts so PrivateRoute re-evaluates");
  // PrivateRoute's continuation for a private deep link (unchanged contract).
  assert.equal(withNext("/login", "/portal?tab=tickets"), "/login?next=%2Fportal%3Ftab%3Dtickets");
  boundary.stop();
});

test("the axios 401 handler no longer hard-navigates to bare /login", async () => {
  const api = await readFile(new URL("../src/services/api.js", import.meta.url), "utf8");
  assert.doesNotMatch(api, /window\.location\.href\s*=\s*["'`]\/login/);
  assert.match(api, /expireCurrentSession\(/);
});
