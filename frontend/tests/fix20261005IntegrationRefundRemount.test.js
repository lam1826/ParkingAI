// Integration round 2 (review 05/10/2026, agent MONEY): #24 (stable refund idempotency key, CL-LEDGER)
// meets #73 (header 'Làm mới' remounts SiteFinance, CL-REPORTS).
//
// The header refresh must keep reloading the finance data (#73), and a refund whose outcome is unknown
// must keep its idempotency key across that remount, a navigation away and back, and a page reload,
// also while the request is still in flight and when sessionStorage is blocked. Otherwise a reopened
// dialog mints a new key and the backend records a second refund.
// Runs the REAL SiteFinancePage + SiteFinance under the shared harness (fake HTTP client).
import test from "node:test";
import assert from "node:assert/strict";
import {
  blockedStorage, buttonsNamed, countCalls, fakeApi, findAll, fire, h, loadReal, MemoryStorage, R, setGlobal, settle, textOf,
} from "./fix20261005IntegrationHarness.js";
import { loadPendingRefunds, PENDING_REFUND_NOTICE } from "../src/pages/Expansion/siteFinanceRefund.js";

const SITE = { id: 4, name: "Bãi 4", role: "manager" };
const timeout = () => Object.assign(new Error("timeout of 10000ms exceeded"), { code: "ECONNABORTED" });

function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

/** Fake API for one receipt; `refund` answers each POST (it may throw or return a pending promise). */
function financeApi(receiptId, refund) {
  const receipt = { id: receiptId, kind: "receipt", method: "cash", amount: 75000, refundable_amount: 75000, created_at: "2026-10-05T02:00:00+00:00", shift_id: null };
  fakeApi.setHandler(async (method, url, params, body) => {
    if (method === "get" && url === "/api/v2/sites") return [SITE];
    if (method === "get" && url === "/api/v2/sites/4/cash-shifts") return { items: [] };
    if (method === "get" && url === "/api/v2/sites/4/payments") return { items: [receipt] };
    if (method === "get" && url === "/api/v2/sites/4/revenue") return { total_revenue: 75000, unassigned_revenue: 0, note: "", date_from: null, date_to: null };
    if (method === "post" && url === `/api/v2/sites/4/payments/${receiptId}/refund`) return refund(body);
    throw new Error(`unexpected ${method} ${url}`);
  });
  return receipt; // tests change refundable_amount when the server records a refund
}

const loadPage = async () => (await loadReal("pages/Expansion/SiteFinancePage.jsx")).default;
async function mount(Page, root = R.createRoot()) {
  root.render(h(Page));
  await settle(root);
  return root;
}
const field = (root, label) => findAll(root, (node) => node.type === "mui-textfield" && node.props.label === label)[0];
const dialogOpen = (root) => findAll(root, (node) => node.type === "dialog").length > 0;
const refundPosts = () => fakeApi.calls.filter((call) => call.method === "post" && call.url.endsWith("/refund"));
const headerRefresh = (root) => findAll(root, (node) => node.type === "button" && node.props["aria-label"] === "Làm mới")[0];

async function openRefund(root) {
  fire(buttonsNamed(root, "Hoàn tiền")[0], "onClick");
  await settle(root);
  assert.ok(dialogOpen(root), "the refund dialog is open");
}
async function fillAndSubmit(root, amount = "37500", reason = "Khách trả lại") {
  if (amount !== null) fire(field(root, "Số tiền hoàn (₫)"), "onChange", { target: { value: amount } });
  if (reason !== null) fire(field(root, "Lý do hoàn"), "onChange", { target: { value: reason } });
  await settle(root);
  fire(buttonsNamed(root, "Xác nhận đã hoàn tiền")[0], "onSubmit");
  await settle(root);
}
async function closeDialog(root) {
  fire(buttonsNamed(root, "Quay lại")[0], "onClick");
  await settle(root);
  assert.equal(dialogOpen(root), false);
}
/** Reopen the dialog: it must warn, keep the old content and send the old key. */
async function assertSameKeyOnRetry(root, key) {
  await openRefund(root);
  assert.match(textOf(root.tree), new RegExp(PENDING_REFUND_NOTICE.slice(0, 40)), "the dialog warns that the previous attempt is unconfirmed");
  assert.equal(field(root, "Số tiền hoàn (₫)").props.value, "37500");
  assert.equal(field(root, "Lý do hoàn").props.value, "Khách trả lại");
  const before = refundPosts().length;
  await fillAndSubmit(root, null, null);
  const retry = refundPosts()[before];
  assert.ok(retry, "the retry is sent");
  assert.equal(retry.body.idempotency_key, key, "the retry reuses the idempotency key of the unconfirmed attempt");
  assert.deepEqual({ amount: retry.body.amount, reason: retry.body.reason, method: retry.body.method }, { amount: 37500, reason: "Khách trả lại", method: "cash" });
}

test.beforeEach(() => setGlobal("sessionStorage", new MemoryStorage()));

test("#24 + #73 header 'Làm mới' reloads the finance data and an uncertain refund keeps its key across the remount", async () => {
  let attempts = 0;
  financeApi("rcpt-header", () => { attempts += 1; if (attempts === 1) throw timeout(); return { id: "refund-1", kind: "refund" }; });
  const root = await mount(await loadPage());
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;
  assert.ok(key);
  assert.match(textOf(root.tree), /Chưa xác nhận được kết quả hoàn tiền/);
  await closeDialog(root);

  const count = (suffix) => countCalls((call) => call.method === "get" && call.url === `/api/v2/sites/4/${suffix}`);
  const before = { shifts: count("cash-shifts"), payments: count("payments"), revenue: count("revenue") };
  fire(headerRefresh(root), "onClick");
  await settle(root);
  // #73 (CL-REPORTS): the header refresh reloads every finance section, by remounting SiteFinance.
  assert.deepEqual({ shifts: count("cash-shifts"), payments: count("payments"), revenue: count("revenue") },
    { shifts: before.shifts + 1, payments: before.payments + 1, revenue: before.revenue + 1 });
  assert.ok([...root.instances.keys()].some((id) => id.includes("<SiteFinance#4-1>")), "SiteFinance was remounted");

  await assertSameKeyOnRetry(root, key);
  assert.equal(dialogOpen(root), false, "the confirmed retry closes the dialog");
  assert.equal(loadPendingRefunds(globalThis.sessionStorage)["rcpt-header"], undefined, "a confirmed refund forgets the key");
  root.unmount();
});

test("#24 a refund still in flight when the page is reloaded keeps its key", async () => {
  const lost = deferred(); // the reload kills the request: its outcome never reaches this page
  let attempts = 0;
  financeApi("rcpt-reload", () => { attempts += 1; return attempts === 1 ? lost.promise : { id: "refund-2", kind: "refund" }; });
  const first = await mount(await loadPage());
  await openRefund(first);
  await fillAndSubmit(first);
  const key = refundPosts()[0].body.idempotency_key;
  first.unmount();

  // Page reload: fresh modules (no in-memory state), same tab sessionStorage.
  const reloaded = await mount(await loadPage());
  await assertSameKeyOnRetry(reloaded, key);
  reloaded.unmount();
});

test("#24 a remount while the refund is in flight still records its late outcome", async () => {
  const late = deferred();
  let attempts = 0;
  financeApi("rcpt-late", () => { attempts += 1; return attempts === 1 ? late.promise : { id: "refund-3", kind: "refund" }; });
  const Page = await loadPage();
  const root = await mount(Page);
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;

  // Navigate away and back (same modules): the instance that sent the request is gone.
  root.render(h("main"));
  await settle(root);
  await mount(Page, root);
  late.reject(timeout());
  await settle(root);
  assert.equal(loadPendingRefunds(globalThis.sessionStorage)["rcpt-late"]?.key, key, "the late timeout keeps the key stored");
  await assertSameKeyOnRetry(root, key);
  root.unmount();
});

/** Reopen the dialog after the earlier attempt got its answer: no warning, empty form, a fresh key. */
async function assertFreshDialog(root, oldKey, amount = "10000") {
  await openRefund(root);
  assert.doesNotMatch(textOf(root.tree), new RegExp(PENDING_REFUND_NOTICE.slice(0, 40)), "no 'unconfirmed' warning once the answer is known");
  assert.equal(field(root, "Số tiền hoàn (₫)").props.value, "", "the old content is not prefilled");
  const before = refundPosts().length;
  await fillAndSubmit(root, amount, "Hoàn thêm");
  const next = refundPosts()[before];
  assert.ok(next, "the new refund is sent");
  assert.notEqual(next.body.idempotency_key, oldKey, "a new refund never reuses a consumed key");
  return next;
}
const LATE_ANSWER = /Lần hoàn trước của chứng từ này đã có kết quả/;

test("#24 a late success after a remount forgets the stored key and the visible dialog mints a fresh one", async () => {
  const late = deferred();
  let attempts = 0;
  financeApi("rcpt-late-ok", () => { attempts += 1; return attempts === 1 ? late.promise : { id: "refund-4b", kind: "refund" }; });
  const Page = await loadPage();
  const root = await mount(Page);
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;
  assert.ok(loadPendingRefunds(globalThis.sessionStorage)["rcpt-late-ok"]?.key, "the attempt is stored before the answer arrives");
  root.render(h("main"));
  await settle(root);
  await mount(Page, root);
  late.resolve({ id: "refund-4", kind: "refund" });
  await settle(root);
  assert.equal(loadPendingRefunds(globalThis.sessionStorage)["rcpt-late-ok"], undefined);
  // Review INT2-MONEY: the visible instance must not offer the consumed key from a copy loaded at mount.
  await assertFreshDialog(root, key);
  root.unmount();
});

test("#24 + #73 a late success after the header 'Làm mới' remount reloads the visible lists", async () => {
  const late = deferred();
  let attempts = 0;
  const receipt = financeApi("rcpt-header-late", () => { attempts += 1; return attempts === 1 ? late.promise : { id: "refund-7", kind: "refund" }; });
  const root = await mount(await loadPage());
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;
  fire(headerRefresh(root), "onClick");
  await settle(root);
  assert.ok([...root.instances.keys()].some((id) => id.includes("<SiteFinance#4-1>")), "SiteFinance was remounted");
  const count = (suffix) => countCalls((call) => call.method === "get" && call.url === `/api/v2/sites/4/${suffix}`);
  const before = { shifts: count("cash-shifts"), payments: count("payments"), revenue: count("revenue") };

  receipt.refundable_amount = 37500; // the server recorded the first refund
  late.resolve({ id: "refund-6", kind: "refund" });
  await settle(root);
  assert.equal(loadPendingRefunds(globalThis.sessionStorage)["rcpt-header-late"], undefined);
  assert.deepEqual({ shifts: count("cash-shifts"), payments: count("payments"), revenue: count("revenue") },
    { shifts: before.shifts + 1, payments: before.payments + 1, revenue: before.revenue + 1 },
    "the visible page reloads its lists when a refund sent by the replaced instance settles");
  await openRefund(root);
  assert.match(textOf(root.tree), /Có thể hoàn tối đa 37\D?500/, "the dialog shows the refundable amount after the late refund");
  await closeDialog(root);
  await assertFreshDialog(root, key);
  root.unmount();
});

test("#24 a dialog opened before the late answer arrived does not resend the consumed key", async () => {
  const late = deferred();
  let attempts = 0;
  financeApi("rcpt-open-late", () => { attempts += 1; return attempts === 1 ? late.promise : { id: "refund-8", kind: "refund" }; });
  const root = await mount(await loadPage());
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;
  fire(headerRefresh(root), "onClick");
  await settle(root);
  await openRefund(root); // the new instance offers the unconfirmed attempt (same key, same content)
  assert.match(textOf(root.tree), new RegExp(PENDING_REFUND_NOTICE.slice(0, 40)));
  late.resolve({ id: "refund-6", kind: "refund" });
  await settle(root);
  // The manager changes the amount and confirms: the earlier attempt already has its answer, so the
  // page sends nothing with the consumed key, closes the dialog and says why.
  await fillAndSubmit(root, "10000", null);
  assert.equal(refundPosts().length, 1, "nothing is sent with the consumed key");
  assert.equal(dialogOpen(root), false);
  assert.match(textOf(root.tree), LATE_ANSWER);
  await assertFreshDialog(root, key);
  root.unmount();
});

test("#24 a late timeout never brings back a key that a newer attempt confirmed", async () => {
  const late = deferred();
  let attempts = 0;
  financeApi("rcpt-late-timeout", () => { attempts += 1; return attempts === 1 ? late.promise : { id: "refund-9", kind: "refund" }; });
  const Page = await loadPage();
  const root = await mount(Page);
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;
  root.render(h("main"));
  await settle(root);
  await mount(Page, root);
  await assertSameKeyOnRetry(root, key); // the retry is confirmed by the server
  assert.equal(loadPendingRefunds(globalThis.sessionStorage)["rcpt-late-timeout"], undefined);
  late.reject(timeout()); // the first request's answer was lost after all
  await settle(root);
  assert.equal(loadPendingRefunds(globalThis.sessionStorage)["rcpt-late-timeout"], undefined, "the confirmed key stays forgotten");
  await assertFreshDialog(root, key);
  root.unmount();
});

test("#24 a retry the server refuses closes the dialog; reopening mints a fresh key", async () => {
  let attempts = 0;
  const conflict = () => Object.assign(new Error("Request failed with status code 409"),
    { response: { status: 409, data: { detail: "Mã yêu cầu hoàn tiền đã được dùng cho nội dung khác." } } });
  financeApi("rcpt-conflict", () => { attempts += 1; if (attempts === 1) throw timeout(); if (attempts === 2) throw conflict(); return { id: "refund-10", kind: "refund" }; });
  const root = await mount(await loadPage());
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;
  await closeDialog(root);
  await openRefund(root);
  await fillAndSubmit(root, "10000", null); // edited retry: the first attempt had been recorded with other content
  assert.equal(refundPosts()[1].body.idempotency_key, key);
  assert.equal(dialogOpen(root), false, "a refused retry does not leave the consumed key in an open dialog");
  assert.match(textOf(root.tree), /đã được dùng cho nội dung khác/, "the refusal stays visible on the page");
  assert.equal(loadPendingRefunds(globalThis.sessionStorage)["rcpt-conflict"], undefined);
  await assertFreshDialog(root, key);
  root.unmount();
});

test("#24 with sessionStorage blocked the uncertain key still survives the header 'Làm mới' remount", async () => {
  setGlobal("sessionStorage", blockedStorage);
  let attempts = 0;
  financeApi("rcpt-blocked", () => { attempts += 1; if (attempts === 1) throw timeout(); return { id: "refund-5", kind: "refund" }; });
  const root = await mount(await loadPage());
  await openRefund(root);
  await fillAndSubmit(root);
  const key = refundPosts()[0].body.idempotency_key;
  await closeDialog(root);
  fire(headerRefresh(root), "onClick");
  await settle(root);
  assert.ok([...root.instances.keys()].some((id) => id.includes("<SiteFinance#4-1>")), "SiteFinance was remounted");
  await assertSameKeyOnRetry(root, key);
  root.unmount();
});

test("#24 helpers: an attempt is stored before it is sent; the in-memory copy covers blocked storage", async () => {
  const { beginRefundAttempt, refundDialogState, settleRefundAttempt } = await import("../src/pages/Expansion/siteFinanceRefund.js");
  const storage = new MemoryStorage();
  const attempt = { key: "k-helper", amount: 1000, method: "transfer", reason: "Trả lại" };
  const begun = beginRefundAttempt({}, "rcpt-helper", attempt, storage);
  assert.deepEqual(loadPendingRefunds(storage)["rcpt-helper"], attempt);
  assert.deepEqual(refundDialogState(begun, "rcpt-helper", () => "fresh"), { key: "k-helper", amount: "1000", method: "transfer", reason: "Trả lại", uncertain: true });
  // Blocked storage: the same page load still finds the attempt.
  assert.equal(loadPendingRefunds(blockedStorage)["rcpt-helper"].key, "k-helper");
  // A definitive answer forgets it everywhere.
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-helper", attempt, { response: { status: 409 } }, storage);
  assert.equal(loadPendingRefunds(storage)["rcpt-helper"], undefined);
  assert.equal(loadPendingRefunds(blockedStorage)["rcpt-helper"], undefined);
});

test("#24 helpers: only the attempt that owns the stored key settles it", async () => {
  const { beginRefundAttempt, settleRefundAttempt } = await import("../src/pages/Expansion/siteFinanceRefund.js");
  const storage = new MemoryStorage();
  const older = { key: "k-older", amount: 1000, method: "cash", reason: "Lần 1" };
  const newer = { key: "k-newer", amount: 2000, method: "cash", reason: "Lần 2" };
  beginRefundAttempt({}, "rcpt-own", newer, storage);
  // A late answer for an older key neither drops nor replaces the newer attempt's key.
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-own", older, undefined, storage);
  assert.equal(loadPendingRefunds(storage)["rcpt-own"]?.key, "k-newer");
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-own", older, { response: { status: 409 } }, storage);
  assert.equal(loadPendingRefunds(storage)["rcpt-own"]?.key, "k-newer");
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-own", older, timeout(), storage);
  assert.deepEqual(loadPendingRefunds(storage)["rcpt-own"], newer);
  // The owner's success forgets it; a later timeout for that confirmed key does not bring it back.
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-own", newer, undefined, storage);
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-own", newer, timeout(), storage);
  assert.equal(loadPendingRefunds(storage)["rcpt-own"], undefined);
  // An older key confirmed earlier is not brought back either.
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-own", older, timeout(), storage);
  assert.equal(loadPendingRefunds(storage)["rcpt-own"], undefined);
  // An unconfirmed key whose entry is missing is kept: losing a key could record a refund twice.
  const lost = { key: "k-lost", amount: 3000, method: "transfer", reason: "Lần 3" };
  settleRefundAttempt(loadPendingRefunds(storage), "rcpt-own", lost, timeout(), storage);
  assert.deepEqual(loadPendingRefunds(storage)["rcpt-own"], lost);
});
