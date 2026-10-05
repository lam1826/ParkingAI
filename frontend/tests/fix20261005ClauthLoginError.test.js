// CL-AUTH #75 (+ #40 client side): when /api/auth/login succeeds but the profile
// fetch fails, the login page that is remounted by the session reset still gets
// the error message and the username.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createAuthSessionBoundary, loginWithSession } from "../src/services/authSessionBoundary.js";

function memoryStorage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)), removeItem: (key) => values.delete(key) };
}

function provider(fetchProfile) {
  const storage = memoryStorage();
  const log = [];
  const session = createAuthSessionBoundary({
    storage, eventTarget: new EventTarget(), fetchProfile,
    onReset: () => log.push("reset"), onUser: () => {}, onLoading: (value) => log.push(`loading:${value}`),
    setTimer: () => null, clearTimer: () => {},
  });
  return { storage, log, session };
}

const describeError = (error) => error?.response?.data?.detail || "Đăng nhập thất bại.";

for (const failure of [
  Object.assign(new Error("Request failed with status code 503"), { response: { status: 503, data: { detail: "Hệ thống đang khởi động" } } }),
  Object.assign(new Error("timeout of 10000ms exceeded"), { code: "ECONNABORTED", request: {} }),
]) {
  test(`profile failure after the token is issued keeps the error for the remounted page (${failure.message})`, async () => {
    const p = provider(async () => { throw failure; });
    await p.session.start();
    const failures = [];
    const result = await loginWithSession({
      session: p.session, storage: p.storage, credentials: { username: "lan_khach", password: "secret" },
      authenticate: async () => ({ access_token: "issued" }), describeError,
      onFailure: (value) => { failures.push(value); p.log.push("failure"); },
    });
    assert.equal(result.success, false);
    assert.ok(result.message);
    assert.equal(failures.length, 1);
    assert.equal(failures[0].message, result.message);
    assert.equal(failures[0].username, "lan_khach");
    // Provider state is written before the final remount, so the new page reads it.
    assert.ok(p.log.lastIndexOf("reset") > p.log.indexOf("failure"));
    assert.equal(p.storage.getItem("token"), null);
    p.session.stop();
  });
}

test("a wrong password does not remount the page and needs no provider message", async () => {
  const p = provider(async () => ({ id: 1 }));
  await p.session.start();
  const failures = [];
  const wrong = Object.assign(new Error("401"), { response: { status: 401, data: { detail: "Sai tên đăng nhập hoặc mật khẩu" } } });
  const resetsBefore = p.log.filter((entry) => entry === "reset").length;
  const result = await loginWithSession({
    session: p.session, storage: p.storage, credentials: { username: "x", password: "y" },
    authenticate: async () => { throw wrong; }, describeError, onFailure: (value) => failures.push(value),
  });
  assert.deepEqual([result.success, result.message], [false, "Sai tên đăng nhập hoặc mật khẩu"]);
  assert.equal(failures.length, 0);
  assert.equal(p.log.filter((entry) => entry === "reset").length, resetsBefore);
  p.session.stop();
});

test("successful login returns the profile for the landing decision", async () => {
  const p = provider(async () => ({ id: 3, role: "staff" }));
  await p.session.start();
  const result = await loginWithSession({
    session: p.session, storage: p.storage, credentials: { username: "a", password: "b" },
    authenticate: async () => ({ access_token: "issued" }), describeError, onFailure: () => assert.fail("no failure"),
  });
  assert.equal(result.success, true);
  assert.equal(result.profile.role, "staff");
  assert.equal(p.storage.getItem("token"), "issued");
  p.session.stop();
});

test("login page shows the provider-held failure, keeps the username and trims what it sends", async () => {
  const page = await readFile(new URL("../src/pages/Login/LoginPage.jsx", import.meta.url), "utf8");
  assert.match(page, /loginFailure/);
  assert.match(page, /clearLoginFailure/);
  assert.match(page, /username: formData\.username\.trim\(\)/);
  assert.match(page, /autoCapitalize="none"/);
  assert.match(page, /autoCorrect="off"/);
  const context = await readFile(new URL("../src/context/AuthContext.jsx", import.meta.url), "utf8");
  assert.match(context, /loginWithSession\(/);
  assert.match(context, /onFailure: setLoginFailure/);
});
