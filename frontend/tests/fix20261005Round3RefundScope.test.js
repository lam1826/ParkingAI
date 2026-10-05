// Round 3 (Claude minors) of review 05/10/2026, final whole-diff review, Site Finance direct refunds (#24):
//  - an unconfirmed refund attempt (key, amount, reason) belongs to the account that started it: it is
//    not offered to another manager who signs in on the same tab after logout / session expiry, and that
//    account switch removes the earlier draft from the tab. The #24 guarantee stays: the SAME account
//    keeps the key across a remount, a reload and signing back in, until the server answers definitively.
//  - a 5xx/408/429 answer keeps the "not confirmed" guidance but shows the server's detail and its
//    'Mã truy vết'; only a failure without any response blames the connection.
// Integration tests run the REAL AuthProvider + SiteFinancePage + SiteFinance under the shared harness.
import test from "node:test";
import assert from "node:assert/strict";
import {
  blockedStorage, buttonsNamed, fakeApi, findAll, fire, h, loadReal, MemoryStorage, R, setGlobal, settle, stub, textOf,
} from "./fix20261005IntegrationHarness.js";
import * as refunds from "../src/pages/Expansion/siteFinanceRefund.js";
import { withServerErrorTrace } from "../src/services/serverErrorTrace.js";

// Every compiled graph below uses THIS module instance (the one the test reads), like the single
// instance a real page load shares between AuthProvider and the lazily loaded finance page.
const SHARED_REFUNDS = { "pages/Expansion/siteFinanceRefund.js": new URL("../src/pages/Expansion/siteFinanceRefund.js", import.meta.url).href };
const AUTH_OVERRIDES = {
  ...SHARED_REFUNDS,
  "react-router-dom": stub("round3-refund-router", `
export const useNavigate = () => () => {};
export const useLocation = () => ({ pathname: "/site-finance", search: "", state: null });
export function Link({ to, children, ...props }) { return createElement("a", { ...props, href: to }, children); }
export function useSearchParams() { return [new URLSearchParams(""), () => {}]; }
`),
};
const SITE = { id: 4, name: "Bãi 4", role: "manager" };
const ACCOUNTS = { manager_a: { id: 71, username: "manager_a", role: "manager" }, manager_b: { id: 72, username: "manager_b", role: "manager" }, manager_c: { id: 73, username: "manager_c", role: "manager" } };
const timeout = () => Object.assign(new Error("timeout of 10000ms exceeded"), { code: "ECONNABORTED", isAxiosError: true, request: {} });
const REASON_A = "Khach A tra lai ve, SDT 0901xxxxxx";

/** One receipt; auth endpoints answer for the account that logged in last; `refund` answers each POST. */
function serve(receiptId, refund) {
  let signedIn = null;
  const receipt = { id: receiptId, kind: "receipt", method: "cash", amount: 75000, refundable_amount: 75000, created_at: "2026-10-05T02:00:00+00:00", shift_id: null };
  fakeApi.setHandler(async (method, url, params, body) => {
    if (method === "post" && url === "/api/auth/login") { signedIn = ACCOUNTS[body.username]; return { access_token: `token-${body.username}`, token_type: "bearer" }; }
    if (method === "get" && url === "/api/auth/me") return signedIn;
    if (method === "get" && url === "/api/v2/sites") return [SITE];
    if (method === "get" && url === "/api/v2/sites/4/cash-shifts") return { items: [] };
    if (method === "get" && url === "/api/v2/sites/4/payments") return { items: [receipt] };
    if (method === "get" && url === "/api/v2/sites/4/revenue") return { total_revenue: 75000, unassigned_revenue: 0, note: "", date_from: null, date_to: null };
    if (method === "post" && url === `/api/v2/sites/4/payments/${receiptId}/refund`) return refund(body);
    throw new Error(`unexpected ${method} ${url}`);
  });
}

/** The provider's value as last rendered (login/logout are driven through it, like the app does). */
const authProbe = { current: null };
function Shell({ AuthContext, Page }) {
  const value = R.useContext(AuthContext);
  R.useEffect(() => { authProbe.current = value; });
  return value.user ? h(Page) : h("main", null, "Đăng nhập");
}
async function mountApp() {
  const { AuthProvider, AuthContext } = await loadReal("context/AuthContext.jsx", AUTH_OVERRIDES);
  const Page = (await loadReal("pages/Expansion/SiteFinancePage.jsx", SHARED_REFUNDS)).default;
  const root = R.createRoot();
  root.render(h(AuthProvider, null, h(Shell, { AuthContext, Page })));
  await settle(root);
  return root;
}
async function signIn(root, username) {
  const result = await authProbe.current.login({ username, password: "test-only" });
  assert.equal(result.success, true, `${username} signs in`);
  await settle(root);
  assert.ok(buttonsNamed(root, "Hoàn tiền").length, "the finance page is shown");
}
async function signOut(root) {
  authProbe.current.logout();
  await settle(root);
  assert.equal(buttonsNamed(root, "Hoàn tiền").length, 0, "signed out");
}

const field = (root, label) => findAll(root, (node) => node.type === "mui-textfield" && node.props.label === label)[0];
const dialogOpen = (root) => findAll(root, (node) => node.type === "dialog").length > 0;
const refundPosts = () => fakeApi.calls.filter((call) => call.method === "post" && call.url.endsWith("/refund"));
const PENDING = new RegExp(refunds.PENDING_REFUND_NOTICE.slice(0, 40));
async function openRefund(root) {
  fire(buttonsNamed(root, "Hoàn tiền")[0], "onClick");
  await settle(root);
  assert.ok(dialogOpen(root), "the refund dialog is open");
}
async function fillAndSubmit(root, amount, reason) {
  if (amount !== null) fire(field(root, "Số tiền hoàn (₫)"), "onChange", { target: { value: amount } });
  if (reason !== null) fire(field(root, "Lý do hoàn"), "onChange", { target: { value: reason } });
  await settle(root);
  fire(buttonsNamed(root, "Xác nhận đã hoàn tiền")[0], "onSubmit");
  await settle(root);
}
async function closeDialog(root) {
  fire(buttonsNamed(root, "Quay lại")[0], "onClick");
  await settle(root);
}
const storedText = () => JSON.stringify([...globalThis.sessionStorage.map]);

test.beforeEach(() => {
  setGlobal("localStorage", new MemoryStorage());
  setGlobal("sessionStorage", new MemoryStorage());
});

test("round 3: manager A's unconfirmed refund is not offered to manager B who signs in on the same tab", async () => {
  let attempts = 0;
  serve("rcpt-r3-switch", () => { attempts += 1; if (attempts === 1) throw timeout(); return { id: "refund-r3-b", kind: "refund" }; });
  const root = await mountApp();
  await signIn(root, "manager_a");
  await openRefund(root);
  await fillAndSubmit(root, "50000", REASON_A);
  const keyA = refundPosts()[0].body.idempotency_key;
  assert.match(textOf(root.tree), /Chưa xác nhận được kết quả hoàn tiền/);
  await closeDialog(root);
  await signOut(root);

  await signIn(root, "manager_b");
  await openRefund(root);
  assert.doesNotMatch(textOf(root.tree), PENDING, "B is not told that the attempt is B's own unconfirmed one");
  assert.equal(field(root, "Số tiền hoàn (₫)").props.value, "", "A's amount is not prefilled for B");
  assert.equal(field(root, "Lý do hoàn").props.value, "", "A's free-text reason is not prefilled for B");
  assert.doesNotMatch(storedText(), /Khach A/, "A's draft text no longer sits in the tab's storage");
  await fillAndSubmit(root, "10000", "Khách B hoàn");
  const sent = refundPosts()[1];
  assert.ok(sent, "B's refund is sent");
  assert.notEqual(sent.body.idempotency_key, keyA, "B never sends A's idempotency key");
  assert.equal(dialogOpen(root), false, "B's confirmed refund closes the dialog");
  root.unmount();
});

test("round 3 keeps #24: the same manager signing back in on the tab still gets the unconfirmed key and content", async () => {
  let attempts = 0;
  serve("rcpt-r3-same", () => { attempts += 1; if (attempts === 1) throw timeout(); return { id: "refund-r3-a", kind: "refund" }; });
  const root = await mountApp();
  await signIn(root, "manager_c");
  await openRefund(root);
  await fillAndSubmit(root, "37500", "Khách trả lại");
  const key = refundPosts()[0].body.idempotency_key;
  await closeDialog(root);
  await signOut(root); // logout, password change and a 401 expiry all end the session this way

  await signIn(root, "manager_c");
  await openRefund(root);
  assert.match(textOf(root.tree), PENDING, "the dialog still warns that the earlier attempt is unconfirmed");
  assert.equal(field(root, "Số tiền hoàn (₫)").props.value, "37500");
  assert.equal(field(root, "Lý do hoàn").props.value, "Khách trả lại");
  await fillAndSubmit(root, null, null);
  assert.equal(refundPosts()[1].body.idempotency_key, key, "the retry reuses the unconfirmed key, so no second refund is recorded");
  assert.equal(refunds.loadPendingRefunds()["rcpt-r3-same"], undefined, "the confirmed retry forgets the key");
  root.unmount();
});

test("round 3 helpers: attempts are stored per account; a reload keeps them for that account only", async () => {
  const page = await loadReal("pages/Expansion/siteFinanceRefund.js"); // a fresh module = one page load
  const storage = new MemoryStorage();
  const attempt = { key: "k-r3-a", amount: 50000, method: "cash", reason: REASON_A };
  page.bindPendingRefundsAccount(71, storage);
  page.beginRefundAttempt(page.loadPendingRefunds(storage), "r1", attempt, storage);
  page.settleRefundAttempt(page.loadPendingRefunds(storage), "r1", attempt, timeout(), storage);
  assert.equal(page.loadPendingRefunds(storage).r1.key, "k-r3-a");
  page.bindPendingRefundsAccount(null, storage); // signed out (logout / 401): nobody's drafts are offered
  assert.deepEqual(page.loadPendingRefunds(storage), {});

  // Tab reload, the same account signs in again: the key is still there (#24).
  const reloaded = await loadReal("pages/Expansion/siteFinanceRefund.js");
  reloaded.bindPendingRefundsAccount("71", storage);
  assert.deepEqual(reloaded.loadPendingRefunds(storage).r1, attempt);
  // Another account signs in on that tab: nothing of the first account is offered or kept.
  reloaded.bindPendingRefundsAccount(72, storage);
  assert.deepEqual(reloaded.loadPendingRefunds(storage), {});
  assert.doesNotMatch(JSON.stringify([...storage.map]), /Khach A|k-r3-a/);
  reloaded.bindPendingRefundsAccount(71, storage);
  assert.deepEqual(reloaded.loadPendingRefunds(storage), {}, "the switch dropped the first account's draft");

  // Blocked storage: the in-memory copy is scoped the same way.
  const blocked = await loadReal("pages/Expansion/siteFinanceRefund.js");
  blocked.bindPendingRefundsAccount(71, blockedStorage);
  blocked.beginRefundAttempt(blocked.loadPendingRefunds(blockedStorage), "r2", { ...attempt, key: "k-r3-mem" }, blockedStorage);
  blocked.bindPendingRefundsAccount(null, blockedStorage);
  blocked.bindPendingRefundsAccount(71, blockedStorage);
  assert.equal(blocked.loadPendingRefunds(blockedStorage).r2.key, "k-r3-mem", "same account: kept in memory");
  blocked.bindPendingRefundsAccount(72, blockedStorage);
  assert.deepEqual(blocked.loadPendingRefunds(blockedStorage), {}, "other account: not offered from memory");
});

test("round 3 helpers: a late answer to the previous account's attempt never lands in the next account's drafts", async () => {
  const page = await loadReal("pages/Expansion/siteFinanceRefund.js");
  const storage = new MemoryStorage();
  const a = { key: "k-r3-late-a", amount: 50000, method: "cash", reason: REASON_A };
  page.bindPendingRefundsAccount(71, storage);
  page.beginRefundAttempt(page.loadPendingRefunds(storage), "r1", a, storage); // still in flight
  page.bindPendingRefundsAccount(null, storage);
  page.bindPendingRefundsAccount(72, storage); // manager B signed in on the tab
  page.settleRefundAttempt(page.loadPendingRefunds(storage), "r1", a, timeout(), storage); // A's request times out late
  assert.deepEqual(page.loadPendingRefunds(storage), {}, "B is not handed A's attempt");
  assert.doesNotMatch(JSON.stringify([...storage.map]), /Khach A/);
  // B's own attempt on the same receipt is not touched by a late answer to A's.
  const b = { key: "k-r3-late-b", amount: 1000, method: "cash", reason: "B" };
  page.beginRefundAttempt(page.loadPendingRefunds(storage), "r1", b, storage);
  page.settleRefundAttempt(page.loadPendingRefunds(storage), "r1", a, undefined, storage);
  page.settleRefundAttempt(page.loadPendingRefunds(storage), "r1", a, { response: { status: 409 } }, storage);
  assert.equal(page.loadPendingRefunds(storage).r1?.key, "k-r3-late-b");

  // While nobody is signed in, a late uncertain answer keeps A's key for A.
  const page2 = await loadReal("pages/Expansion/siteFinanceRefund.js");
  const storage2 = new MemoryStorage();
  const a2 = { key: "k-r3-late-a2", amount: 2000, method: "cash", reason: "A2" };
  page2.bindPendingRefundsAccount(71, storage2);
  page2.beginRefundAttempt(page2.loadPendingRefunds(storage2), "r2", a2, storage2);
  page2.bindPendingRefundsAccount(null, storage2);
  page2.settleRefundAttempt(page2.loadPendingRefunds(storage2), "r2", a2, timeout(), storage2);
  page2.bindPendingRefundsAccount(71, storage2);
  assert.equal(page2.loadPendingRefunds(storage2).r2?.key, "k-r3-late-a2");
  // ...and a late success while signed out still forgets it for A.
  page2.bindPendingRefundsAccount(null, storage2);
  page2.settleRefundAttempt(page2.loadPendingRefunds(storage2), "r2", a2, undefined, storage2);
  page2.bindPendingRefundsAccount(71, storage2);
  assert.equal(page2.loadPendingRefunds(storage2).r2, undefined);
});

/** A 5xx exactly as the axios interceptor leaves it (withServerErrorTrace adds the trace code). */
const serverError = (status, data, headers = {}) => withServerErrorTrace(Object.assign(new Error(`Request failed with status code ${status}`), {
  name: "AxiosError", isAxiosError: true, code: "ERR_BAD_RESPONSE", request: {}, response: { status, data, headers },
}));

test("round 3 #24: a 5xx keeps the 'not confirmed' guidance and shows the server detail and its trace code", () => {
  const failure = serverError(500, { detail: "Hệ thống chưa xử lý được yêu cầu. Vui lòng thử lại hoặc cung cấp mã truy vết để được hỗ trợ.", request_id: "req-abc123" });
  const shown = refunds.refundFailure(failure).message;
  assert.match(shown, /^Chưa xác nhận được kết quả hoàn tiền/);
  assert.match(shown, /Hệ thống chưa xử lý được yêu cầu/, "the server's own text is kept");
  assert.match(shown, /Mã truy vết: req-abc123/, "the trace code the user quotes to support is kept");
  assert.match(shown, /cùng mã yêu cầu nên không ghi hoàn trùng/, "the retry guidance is kept");
  assert.match(shown, /500/);
  assert.doesNotMatch(shown, /mất kết nối|quá thời gian chờ/, "a server answer is not a lost connection");
  // Only a trace header and an empty body: the interceptor builds the detail, it still reaches the page.
  assert.match(refunds.refundFailure(serverError(503, "", { "x-request-id": "req-hdr-503" })).message, /Mã truy vết: req-hdr-503/);
  // A trace code that never made it into the detail is still shown once.
  const traced = Object.assign(new Error("x"), { response: { status: 502, data: "<html>Bad gateway</html>" }, traceId: "req-502" });
  const tracedText = refunds.refundFailure(traced).message;
  assert.equal(tracedText.split("Mã truy vết: req-502").length, 2);
  assert.doesNotMatch(tracedText, /<html>/, "a proxy page is never shown as the server detail");
});

test("round 3 #24: 408/429 keep the uncertain guidance without blaming the connection; no response still does", () => {
  for (const status of [408, 429]) {
    const shown = refunds.refundFailure({ response: { status, data: { detail: `Máy chủ trả ${status}` } } }).message;
    assert.match(shown, /^Chưa xác nhận được kết quả hoàn tiền/);
    assert.match(shown, new RegExp(`Máy chủ trả ${status}`));
    assert.doesNotMatch(shown, /mất kết nối/);
  }
  const bare = refunds.refundFailure({ response: { status: 429, data: "" } }).message;
  assert.match(bare, /429/);
  assert.match(bare, /cùng mã yêu cầu/);
  assert.doesNotMatch(bare, /mất kết nối/);
  for (const transport of [timeout(), new Error("Network Error"), Object.assign(new Error("Network Error"), { code: "ERR_NETWORK", request: {} })]) {
    assert.equal(refunds.refundFailure(transport).message, refunds.UNCERTAIN_REFUND_MESSAGE);
  }
  assert.match(refunds.UNCERTAIN_REFUND_MESSAGE, /mất kết nối hoặc quá thời gian chờ/);
  const conflict = { response: { status: 409, data: { detail: "Số tiền hoàn vượt quá" } } };
  assert.equal(refunds.refundFailure(conflict), conflict, "a definitive refusal is shown as the server sent it");
});

test("round 3 #24: the finance page shows the 500 trace code and the reopened dialog keeps the key", async () => {
  refunds.bindPendingRefundsAccount?.(null);
  let attempts = 0;
  serve("rcpt-r3-500", () => {
    attempts += 1;
    if (attempts === 1) throw serverError(500, { detail: "Hệ thống chưa xử lý được yêu cầu. Vui lòng thử lại hoặc cung cấp mã truy vết để được hỗ trợ.", request_id: "req-page-500" });
    return { id: "refund-r3-500", kind: "refund" };
  });
  const Page = (await loadReal("pages/Expansion/SiteFinancePage.jsx", SHARED_REFUNDS)).default;
  const root = R.createRoot();
  root.render(h(Page));
  await settle(root);
  await openRefund(root);
  await fillAndSubmit(root, "37500", "Khách trả lại");
  const key = refundPosts()[0].body.idempotency_key;
  const text = textOf(root.tree);
  assert.match(text, /Chưa xác nhận được kết quả hoàn tiền/);
  assert.match(text, /Mã truy vết: req-page-500/);
  assert.doesNotMatch(text, /mất kết nối/);
  await closeDialog(root);
  await openRefund(root);
  assert.match(textOf(root.tree), PENDING);
  await fillAndSubmit(root, null, null);
  assert.equal(refundPosts()[1].body.idempotency_key, key, "a 5xx is still uncertain: the retry reuses the key");
  root.unmount();
});
