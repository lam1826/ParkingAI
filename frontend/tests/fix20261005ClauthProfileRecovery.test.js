// CL-AUTH #39: a transient /api/auth/me failure at startup is reported and
// retried with backoff instead of leaving a signed-in shell with no user.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createAuthSessionBoundary, loginWithSession } from "../src/services/authSessionBoundary.js";

function memoryStorage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)), removeItem: (key) => values.delete(key) };
}

const http = (status) => Object.assign(new Error(`status ${status}`), { response: { status } });
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function fixture(responses) {
  const storage = memoryStorage();
  const events = new EventTarget();
  const timers = [];
  const state = { user: null, loading: true, profileError: undefined, fetches: 0 };
  const boundary = createAuthSessionBoundary({
    storage, eventTarget: events,
    fetchProfile: async () => {
      const next = responses[Math.min(state.fetches++, responses.length - 1)];
      if (next instanceof Error) throw next;
      return next;
    },
    onReset: () => { state.user = null; },
    onUser: (user) => { state.user = user; },
    onLoading: (loading) => { state.loading = loading; },
    onProfileError: (error) => { state.profileError = error; },
    setTimer: (callback, delay) => { const timer = { callback, delay, cleared: false }; timers.push(timer); return timer; },
    clearTimer: (timer) => { if (timer) timer.cleared = true; },
  });
  const fire = async () => {
    const timer = timers.find((item) => !item.cleared && !item.fired);
    assert.ok(timer, "a retry is scheduled");
    timer.fired = true;
    timer.callback();
    await settle();
    return timer.delay;
  };
  return { storage, events, timers, state, boundary, fire };
}

for (const failure of [http(503), http(500), Object.assign(new Error("timeout of 10000ms exceeded"), { code: "ECONNABORTED", request: {} }), Object.assign(new Error("Network Error"), { request: {} })]) {
  test(`startup profile failure (${failure.message}) is surfaced and retried until it succeeds`, async () => {
    const f = fixture([failure, failure, { id: 7, username: "staff1", role: "staff" }]);
    f.storage.setItem("token", "valid-token");
    await f.boundary.start();
    assert.equal(f.state.user, null);
    assert.equal(f.state.loading, false);
    assert.equal(f.state.profileError, failure, "the UI can show an explicit error with a retry");
    assert.equal(f.storage.getItem("token"), "valid-token");
    assert.equal(await f.fire(), 1000);
    assert.equal(f.state.user, null);
    assert.equal(await f.fire(), 2000, "backoff grows");
    assert.equal(f.state.user.id, 7);
    assert.equal(f.state.profileError, null);
    assert.equal(f.state.fetches, 3);
    assert.equal(f.timers.filter((timer) => !timer.cleared && !timer.fired).length, 0);
    f.boundary.stop();
  });
}

test("a 401 clears the session and schedules no retry", async () => {
  const f = fixture([http(401)]);
  f.storage.setItem("token", "expired");
  await f.boundary.start();
  assert.equal(f.storage.getItem("token"), null);
  assert.equal(f.timers.length, 0);
  f.boundary.stop();
});

test("manual retry, token change and stop cancel or reuse the pending retry", async () => {
  const f = fixture([http(503), { id: 1, role: "customer" }]);
  f.storage.setItem("token", "one");
  await f.boundary.start();
  assert.equal(f.timers.length, 1);
  await f.boundary.refresh();
  assert.equal(f.state.user.id, 1);
  assert.equal(f.timers[0].cleared, true, "a successful manual retry cancels the scheduled one");

  const g = fixture([http(503)]);
  g.storage.setItem("token", "one");
  await g.boundary.start();
  g.storage.setItem("token", "two");
  g.events.dispatchEvent(new Event("parking-auth-session-changed"));
  await settle();
  assert.equal(g.timers[0].cleared, true, "another account's token cancels the old retry");
  g.boundary.stop();
  assert.ok(g.timers.every((timer) => timer.cleared), "stop cancels every pending retry");
});

// Rework: the background retry must not invalidate a login submitted while it
// was pending (it used to call refresh(), which bumps the login version).
for (const keptAccountRecovers of [false, true]) {
  test(`a profile retry firing during login (${keptAccountRecovers ? "kept account recovers" : "still failing"}) does not cancel the login`, async () => {
    const storage = memoryStorage();
    const timers = [];
    const state = { user: null, profileError: undefined };
    const accounts = { old: { id: 1, username: "old", role: "customer" }, new: { id: 2, username: "staff1", role: "staff" } };
    let oldCalls = 0;
    const session = createAuthSessionBoundary({
      storage, eventTarget: new EventTarget(),
      fetchProfile: async () => {
        const token = storage.getItem("token");
        if (token === "old" && (oldCalls++ === 0 || !keptAccountRecovers)) throw http(503);
        return accounts[token];
      },
      onReset: () => { state.user = null; },
      onUser: (user) => { state.user = user; },
      onLoading: () => {},
      onProfileError: (error) => { state.profileError = error; },
      setTimer: (callback, delay) => { const timer = { callback, delay, cleared: false }; timers.push(timer); return timer; },
      clearTimer: (timer) => { if (timer) timer.cleared = true; },
    });
    storage.setItem("token", "old");
    await session.start();
    assert.equal(timers.length, 1, "the kept token's profile retry is pending");

    let issue;
    const failures = [];
    const login = loginWithSession({
      session, storage, credentials: { username: " staff1 ", password: "secret" },
      authenticate: () => new Promise((resolve) => { issue = () => resolve({ access_token: "new" }); }),
      describeError: (error) => error.message,
      onFailure: (failure) => failures.push(failure),
    });
    // POST /api/auth/login is in flight when the retry timer fires.
    timers[0].callback();
    await settle();
    assert.equal(state.user?.id, keptAccountRecovers ? 1 : undefined);
    issue();
    const result = await login;

    assert.equal(result.success, true, result.message);
    assert.equal(result.profile.id, 2);
    assert.equal(storage.getItem("token"), "new");
    assert.equal(state.user.id, 2);
    assert.equal(state.profileError, null);
    assert.deepEqual(failures, []);
    assert.ok(timers.slice(1).every((timer) => timer.cleared), "no retry left for the old token");
    session.stop();
  });
}

test("a token change or stop still cancels a login waiting for its token", async () => {
  const storage = memoryStorage();
  const session = createAuthSessionBoundary({
    storage, eventTarget: new EventTarget(),
    fetchProfile: async () => { throw http(503); },
    onReset: () => {}, onUser: () => {}, onLoading: () => {},
    setTimer: () => ({}), clearTimer: () => {},
  });
  storage.setItem("token", "old");
  await session.start();
  const isCurrent = session.beginLogin();
  await session.refresh().catch(() => null);
  assert.equal(isCurrent(), false, "an explicit refresh (logout/session event) still supersedes the login");
  const next = session.beginLogin();
  session.stop();
  assert.equal(next(), false);
});

test("the private shell shows an account-recovery state instead of role-gated routes", async () => {
  const layout = await readFile(new URL("../src/layouts/MainLayout.jsx", import.meta.url), "utf8");
  assert.match(layout, /if \(!user\)/);
  assert.match(layout, /Không tải được thông tin tài khoản/);
  assert.match(layout, /refreshUser/);
  const context = await readFile(new URL("../src/context/AuthContext.jsx", import.meta.url), "utf8");
  assert.match(context, /onProfileError: setProfileError/);
  assert.match(context, /profileError/);
});
