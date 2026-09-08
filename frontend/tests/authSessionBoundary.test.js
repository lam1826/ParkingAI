import assert from "node:assert/strict";
import test from "node:test";
import { createAuthSessionBoundary, AUTH_SESSION_CHANGED, isCurrentAuthFailure } from "../src/services/authSessionBoundary.js";
import { clearAIChat, readAIChat, saveAIChat } from "../src/utils/aiChatStorage.js";

function memoryStorage() {
  const values = new Map();
  return { get length() { return values.size; }, key: (index) => [...values.keys()][index],
    getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key) };
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function fixture() {
  const storage = memoryStorage(), chats = memoryStorage(), events = new EventTarget();
  const pending = [];
  const state = { user: null, loading: true, resets: 0 };
  const boundary = createAuthSessionBoundary({
    storage, eventTarget: events,
    fetchProfile: () => { const request = deferred(); pending.push(request); return request.promise; },
    onReset: () => { state.user = null; state.resets++; clearAIChat(chats, events); },
    onUser: (user) => { state.user = user; },
    onLoading: (loading) => { state.loading = loading; },
  });
  function externalToken(token, key = "token", storageArea = storage) {
    if (token) storage.setItem("token", token); else storage.removeItem("token");
    const event = new Event("storage");
    Object.assign(event, { key, storageArea });
    events.dispatchEvent(event);
  }
  return { storage, chats, events, pending, state, boundary, externalToken };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("unauthenticated and old-account 401 responses never expire the current session", () => {
  assert.equal(isCurrentAuthFailure(undefined, "current"), false);
  assert.equal(isCurrentAuthFailure("Bearer old", "current"), false);
  assert.equal(isCurrentAuthFailure("Bearer current", null), false);
  assert.equal(isCurrentAuthFailure("Bearer current", "current"), true);
});

test("late login cannot overwrite another tab, a newer login attempt, or a local logout", async () => {
  const f = fixture();
  await f.boundary.start();
  const first = f.boundary.beginLogin();
  const second = f.boundary.beginLogin();
  assert.equal(first(), false);
  assert.equal(second(), true);
  await f.boundary.refresh();
  assert.equal(second(), false);
  const third = f.boundary.beginLogin();
  f.storage.setItem("token", "other-tab-token");
  assert.equal(third(), false);
  f.boundary.stop();
});

test("another tab changing accounts clears displayed user and chat before its new profile arrives", async () => {
  const f = fixture();
  f.storage.setItem("token", "account-a-token");
  const started = f.boundary.start();
  f.pending[0].resolve({ id: 1, username: "account-a" });
  await started;
  saveAIChat(f.chats, 1, [{ id: "private", role: "user", content: "account-a-only" }]);
  f.externalToken("account-b-token");
  assert.equal(f.state.user, null);
  assert.equal(f.state.loading, true);
  assert.deepEqual(readAIChat(f.chats, 1), []);
  assert.equal(f.storage.getItem("user"), null);
  f.pending[1].resolve({ id: 2, username: "account-b" });
  await settle();
  assert.equal(f.state.user.id, 2);
  assert.equal(f.state.loading, false);
  f.boundary.stop();
});

test("late old-account profile and failure cannot replace or sign out the new account", async () => {
  for (const oldFails of [false, true]) {
    const f = fixture();
    f.storage.setItem("token", "old");
    const started = f.boundary.start();
    f.externalToken("new");
    f.pending[1].resolve({ id: 2 });
    await settle();
    if (oldFails) f.pending[0].reject(new Error("expired old session"));
    else f.pending[0].resolve({ id: 1 });
    await started;
    assert.equal(f.storage.getItem("token"), "new");
    assert.equal(f.state.user.id, 2);
    assert.equal(JSON.parse(f.storage.getItem("user")).id, 2);
    f.boundary.stop();
  }
});

test("external logout and local expiry discard a profile already in flight", async () => {
  for (const localExpiry of [false, true]) {
    const f = fixture();
    f.storage.setItem("token", "old");
    const started = f.boundary.start();
    if (localExpiry) {
      f.storage.removeItem("token");
      f.events.dispatchEvent(new Event(AUTH_SESSION_CHANGED));
    } else f.externalToken(null, null);
    assert.equal(f.state.user, null);
    assert.equal(f.state.loading, false);
    f.pending[0].resolve({ id: 1 });
    await started;
    assert.equal(f.state.user, null);
    assert.equal(f.storage.getItem("user"), null);
    f.boundary.stop();
  }
});

test("unrelated storage events and duplicate token events do not fetch or clear chat", async () => {
  const f = fixture();
  f.storage.setItem("token", "one");
  const started = f.boundary.start();
  f.pending[0].resolve({ id: 1 });
  await started;
  const resets = f.state.resets;
  f.externalToken("one");
  f.externalToken("one", "user");
  f.externalToken("one", "token", f.chats);
  assert.equal(f.pending.length, 1);
  assert.equal(f.state.resets, resets);
  f.boundary.stop();
});

test("same-account refresh preserves mounted UI and only the latest profile can commit", async () => {
  const f = fixture();
  f.storage.setItem("token", "one");
  const started = f.boundary.start();
  f.pending[0].resolve({ id: 1, name: "original" });
  await started;
  const oldRefresh = f.boundary.refresh();
  const rejectedOld = assert.rejects(oldRefresh, /thay đổi/);
  const newRefresh = f.boundary.refresh();
  assert.equal(f.state.loading, false);
  assert.equal(f.state.user.name, "original");
  f.pending[2].resolve({ id: 1, name: "latest" });
  await newRefresh;
  f.pending[1].resolve({ id: 1, name: "stale" });
  await rejectedOld;
  assert.equal(f.state.user.name, "latest");
  f.boundary.stop();
});

test("only a 401 bootstrap clears session; transient profile failures preserve the token", async () => {
  const transient = fixture();
  transient.storage.setItem("token", "still-valid");
  const transientStart = transient.boundary.start();
  transient.pending[0].reject({ response: { status: 503 }, message: "temporary outage" });
  await transientStart;
  assert.equal(transient.storage.getItem("token"), "still-valid");
  assert.equal(transient.state.loading, false);
  transient.boundary.stop();

  const f = fixture();
  f.storage.setItem("token", "one");
  const started = f.boundary.start();
  f.pending[0].reject({ response: { status: 401 }, message: "invalid token" });
  await started;
  assert.equal(f.state.user, null);
  assert.equal(f.state.loading, false);
  assert.equal(f.storage.getItem("token"), null);
  f.externalToken("two");
  f.pending[1].resolve({ id: 2 });
  await settle();
  const refresh = f.boundary.refresh();
  f.pending[2].reject(new Error("temporary network failure"));
  await assert.rejects(refresh, /network/);
  assert.equal(f.state.user.id, 2);
  assert.equal(f.storage.getItem("token"), "two");
  f.boundary.stop();
});

test("stopped boundary ignores events and responses; restarting creates one listener", async () => {
  const f = fixture();
  f.storage.setItem("token", "one");
  const started = f.boundary.start();
  f.boundary.stop();
  f.externalToken("two");
  f.pending[0].resolve({ id: 1 });
  await started;
  assert.equal(f.pending.length, 1);
  assert.equal(f.state.user, null);
  const restarted = f.boundary.start();
  f.pending[1].resolve({ id: 2 });
  await restarted;
  f.externalToken("three");
  assert.equal(f.pending.length, 3);
  f.pending[2].resolve({ id: 3 });
  await settle();
  assert.equal(f.state.user.id, 3);
  f.boundary.stop();
});
