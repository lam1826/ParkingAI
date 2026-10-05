// Round 3 (Claude minors) of review 05/10/2026, final whole-diff review:
//  - security (AuthContext.jsx): a failed login must not write the AxiosError to the browser console.
//    Its request config carries the typed password (config.data of POST /api/auth/login) and, when the
//    profile load fails after the token was issued, `Authorization: Bearer <token>` of /api/auth/me.
//  - frontend (LoginPage.jsx): the provider-held failure of #75 (message + username) is shown by the
//    login page that follows the failed attempt only, not again when the user leaves /login and returns.
// Runs the REAL AuthProvider + LoginPage under the shared harness (fake HTTP client, no network).
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import path from "node:path";
import { inspect } from "node:util";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  fakeApi, findAll, fire, h, loadReal, MemoryStorage, R, setGlobal, settle, stub, STUBS, textOf,
} from "./fix20261005IntegrationHarness.js";

const PASSWORD = "S3cret-Pass-r3";
const ISSUED = "issued-jwt-r3";

const OVERRIDES = {
  "react-router-dom": stub("round3-login-router", `
export const navigations = [];
export const useNavigate = () => (to, options) => { navigations.push({ to, options }); };
export const useLocation = () => ({ pathname: "/login", search: "", state: null });
export function Link({ to, children, ...props }) { return createElement("a", { ...props, href: to }, children); }
`),
  "components/common/PrototypeUI.jsx": stub("round3-login-prototype", "export function PrototypeBrand() { return null; }"),
  "styles/prototype-reference.css": STUBS.empty,
  "styles/prototype-app.css": STUBS.empty,
};
// The harness compiles every loadReal() into its own scenario directory next to its stubs.
const OUT = path.dirname(fileURLToPath(stub("round3-login-probe", "")));

/** LoginPage and the AuthContext module it imports, from ONE compile (the same context object). */
async function loadLogin() {
  const LoginPage = (await loadReal("pages/Login/LoginPage.jsx", OVERRIDES)).default;
  const scenario = readdirSync(OUT).filter((name) => /^scenario-\d+$/.test(name))
    .sort((a, b) => Number(b.slice("scenario-".length)) - Number(a.slice("scenario-".length)))[0];
  const auth = await import(pathToFileURL(path.join(OUT, scenario, "context__AuthContext.mjs")).href);
  return { LoginPage, AuthProvider: auth.AuthProvider };
}

function Routes({ route, LoginPage }) {
  return route === "/login" ? h(LoginPage) : h("main", null, "Thông tin bãi xe");
}
const app = (graph, route) => h(graph.AuthProvider, null, h(Routes, { route, LoginPage: graph.LoginPage }));
const later = (value, ms = 5) => new Promise((resolve) => setTimeout(() => resolve(value), ms));

/** An AxiosError as axios 1.x builds it: the request config travels with the error. */
function axiosFailure({ url, status, detail, data, headers }) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    name: "AxiosError", isAxiosError: true, code: status >= 500 ? "ERR_BAD_RESPONSE" : "ERR_BAD_REQUEST",
    config: { url, method: url.endsWith("/login") ? "post" : "get", data, headers: { Accept: "application/json", ...headers } },
    request: {}, response: { status, data: { detail }, headers: {} },
  });
}

function captureConsole() {
  const levels = ["error", "warn", "log", "info", "debug"];
  const originals = Object.fromEntries(levels.map((level) => [level, console[level]]));
  const entries = [];
  for (const level of levels) console[level] = (...args) => entries.push({ level, args });
  return {
    entries,
    text: () => inspect(entries, { depth: Infinity, showHidden: true, maxStringLength: Infinity, maxArrayLength: Infinity }),
    restore: () => Object.assign(console, originals),
  };
}

const input = (root, name) => findAll(root, (node) => node.type === "input" && node.props.name === name)[0];
const alertText = (root) => findAll(root, (node) => node.props?.role === "alert").map((node) => textOf(node)).join(" ");

async function submitLogin(root, username = "staff1", password = PASSWORD) {
  fire(input(root, "username"), "onChange", { target: { name: "username", value: username } });
  fire(input(root, "password"), "onChange", { target: { name: "password", value: password } });
  await settle(root);
  fire(findAll(root, (node) => node.type === "form")[0], "onSubmit");
  await settle(root);
}

test.beforeEach(() => {
  setGlobal("localStorage", new MemoryStorage());
  setGlobal("sessionStorage", new MemoryStorage());
});

test("round 3 security: a failed login POST never logs the typed password", async () => {
  const graph = await loadLogin();
  fakeApi.setHandler(async (method, url, params, body) => {
    if (method === "post" && url === "/api/auth/login") {
      await later();
      throw axiosFailure({ url, status: 503, detail: "Hệ thống đang khởi động", data: JSON.stringify(body) });
    }
    throw new Error(`unexpected ${method} ${url}`);
  });
  const root = R.createRoot();
  root.render(app(graph, "/login"));
  await settle(root);
  const consoleSpy = captureConsole();
  try {
    await submitLogin(root);
  } finally {
    consoleSpy.restore();
  }
  assert.match(alertText(root), /Hệ thống đang khởi động/, "the failure is still shown on the page");
  assert.equal(fakeApi.calls.filter((call) => call.url === "/api/auth/login")[0].body.password, PASSWORD, "the probe really sent the password");
  const logged = consoleSpy.text();
  assert.doesNotMatch(logged, new RegExp(PASSWORD), "the console never receives the typed password");
  assert.doesNotMatch(logged, /config/, "the axios request config is never logged");
  assert.match(logged, /Login failed/, "a non-sensitive diagnostic line is still logged");
  assert.match(logged, /503/, "the diagnostic keeps the HTTP status");
  root.unmount();
});

function profileFailsAfterToken() {
  fakeApi.setHandler(async (method, url) => {
    if (method === "post" && url === "/api/auth/login") return later({ access_token: ISSUED, token_type: "bearer" });
    if (method === "get" && url === "/api/auth/me") {
      await later();
      throw axiosFailure({ url, status: 503, detail: "Hệ thống đang khởi động", headers: { Authorization: `Bearer ${ISSUED}` } });
    }
    throw new Error(`unexpected ${method} ${url}`);
  });
}

test("round 3 security: a profile failure after the token was issued never logs the bearer token", async () => {
  const graph = await loadLogin();
  profileFailsAfterToken();
  const root = R.createRoot();
  root.render(app(graph, "/login"));
  await settle(root);
  const consoleSpy = captureConsole();
  try {
    await submitLogin(root);
  } finally {
    consoleSpy.restore();
  }
  assert.match(alertText(root), /Đăng nhập chưa hoàn tất/);
  assert.equal(localStorage.getItem("token"), null, "the issued token was dropped");
  const logged = consoleSpy.text();
  assert.doesNotMatch(logged, new RegExp(ISSUED), "the console never receives the issued bearer token");
  assert.doesNotMatch(logged, new RegExp(PASSWORD));
  assert.doesNotMatch(logged, /Authorization|config/);
  assert.match(logged, /Login failed/);
  root.unmount();
});

test("round 3: the post-token failure (#75) is shown once and is gone when the user comes back to /login", async () => {
  const graph = await loadLogin();
  profileFailsAfterToken();
  const root = R.createRoot();
  root.render(app(graph, "/login"));
  await settle(root);
  const consoleSpy = captureConsole(); // keep the test output quiet
  try {
    await submitLogin(root);
  } finally {
    consoleSpy.restore();
  }
  // #75 still holds: the page that follows the failed attempt shows what happened and keeps the username.
  assert.match(alertText(root), /Đăng nhập chưa hoàn tất vì chưa tải được thông tin tài khoản: Hệ thống đang khởi động/);
  assert.equal(input(root, "username").props.value, "staff1");
  assert.equal(input(root, "password").props.value, "");
  // Re-renders of that page (provider updates) keep showing it.
  await settle(root);
  assert.match(alertText(root), /Đăng nhập chưa hoàn tất/);

  // The user leaves /login ("Thông tin bãi xe" / "Đăng ký") and comes back later without a new attempt.
  root.render(app(graph, "/gioi-thieu"));
  await settle(root);
  assert.equal(input(root, "username"), undefined, "the login page is gone");
  root.render(app(graph, "/login"));
  await settle(root);
  assert.equal(alertText(root), "", "the old failure is not shown again");
  assert.equal(input(root, "username").props.value, "", "the old username is not prefilled again");
  root.unmount();
});

test("round 3: a failure shown on the login page is still replaced by the next attempt's outcome", async () => {
  const graph = await loadLogin();
  let logins = 0;
  fakeApi.setHandler(async (method, url) => {
    if (method === "post" && url === "/api/auth/login") {
      logins += 1;
      if (logins === 1) return later({ access_token: ISSUED, token_type: "bearer" });
      await later();
      throw axiosFailure({ url, status: 401, detail: "Sai tên đăng nhập hoặc mật khẩu" });
    }
    if (method === "get" && url === "/api/auth/me") {
      await later();
      throw axiosFailure({ url, status: 503, detail: "Hệ thống đang khởi động", headers: { Authorization: `Bearer ${ISSUED}` } });
    }
    throw new Error(`unexpected ${method} ${url}`);
  });
  const root = R.createRoot();
  root.render(app(graph, "/login"));
  await settle(root);
  const consoleSpy = captureConsole();
  try {
    await submitLogin(root);
    assert.match(alertText(root), /Đăng nhập chưa hoàn tất/);
    await submitLogin(root, "staff1", "wrong");
  } finally {
    consoleSpy.restore();
  }
  assert.match(alertText(root), /Sai tên đăng nhập hoặc mật khẩu/);
  assert.doesNotMatch(alertText(root), /Đăng nhập chưa hoàn tất/, "the earlier failure does not linger next to the new one");
  root.unmount();
});
