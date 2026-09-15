import test from "node:test";
import assert from "node:assert/strict";
import { checkoutLink, createPaymentLinkFlow, paymentDisplay, paymentModes } from "./onlinePaymentState.js";
import { portalOrderBody } from "./portalOffers.js";

const view = (changes = {}) => ({ order_id: "order-1", enabled: true, state: "ready", amount: 12000, currency: "VND",
  server_now: "2026-09-15T10:00:00+07:00", expires_at: "2026-09-15T10:01:00+07:00",
  can_create: false, can_refresh: true, can_cancel: true, qr_svg: "<svg/>", checkout_url: "https://pay.payos.vn/link", ...changes });
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test("QR hides at server deadline, uncertain state and disabled provider", () => {
  assert.equal(paymentDisplay(view(), 59999).payable, true);
  for (const [data, elapsed] of [[view(), 60000], [view({ enabled: false }), 0], [view({ state: "unknown" }), 0], [view({ state: "paid" }), 0], [view({ server_now: null }), 0]]) {
    assert.deepEqual(paymentDisplay(data, elapsed), { payable: false, url: null, qr: null });
  }
});
test("payment page URL allows only exact HTTPS payOS host", () => {
  assert.equal(checkoutLink("https://pay.payos.vn/abc"), "https://pay.payos.vn/abc");
  for (const value of ["javascript:alert(1)", "http://pay.payos.vn/a", "https://pay.payos.vn.evil/a", "https://user@pay.payos.vn/a", "https://pay.payos.vn:8443/a", null]) assert.equal(checkoutLink(value), null);
});
test("a provider link retained for review cannot invite payment when the server hides its instructions", () => {
  const closedSource = view({ qr_svg: null, checkout_url: null, can_create: false });
  assert.deepEqual(paymentDisplay(closedSource), { payable: false, url: null, qr: null });
});
test("payOS offered only by enabled server catalog, never inferred from demo setting", () => {
  assert.deepEqual(paymentModes({}, true), ["demo", "manual"]);
  assert.deepEqual(paymentModes({ payment_modes: ["manual", "payos"] }, false), ["manual", "payos"]);
  assert.deepEqual(paymentModes({ payment_modes: ["demo", "payos", "unknown"] }, false), ["payos"]);
  const vehicle = { id: 2, vehicle_type_id: 1 }, plan = { id: 3, vehicle_type_id: 1, product_kind: "monthly" }, form = { vehicle_id: 2, plan_id: 3 };
  assert.throws(() => portalOrderBody(form, [plan], [vehicle], "payos", "request1"));
  assert.equal(portalOrderBody(form, [{ ...plan, payment_modes: ["payos"] }], [vehicle], "payos", "request1").payment_mode, "payos");
});
test("lost create response never repeats POST automatically and clears instructions", async () => {
  const calls = [];
  const flow = createPaymentLinkFlow({ orderId: "order-1", request: async (action) => {
    calls.push(action); if (action === "create") throw new Error("lost response"); return view({ state: "not_created", can_create: true });
  } });
  await flow.load(); await flow.mutate("create");
  assert.equal(flow.getSnapshot().phase, "uncertain"); assert.equal(flow.getSnapshot().data, null);
  await flow.mutate("create"); assert.deepEqual(calls, ["load", "create"]);
});
test("in-flight mutations are serialized and only current server data enables actions", async () => {
  const pending = deferred(), calls = [];
  const flow = createPaymentLinkFlow({ orderId: "order-1", request: async (action) => { calls.push(action); return action === "load" ? view() : pending.promise; } });
  await flow.load(); const first = flow.mutate("refresh");
  assert.equal(flow.getSnapshot().data, null);
  await flow.mutate("cancel", { reason: "No longer needed" }); await flow.load();
  assert.deepEqual(calls, ["load", "refresh"]);
  pending.resolve(view({ state: "paid", can_refresh: false, can_cancel: false })); await first;
  await flow.mutate("cancel"); assert.equal(calls.length, 2);
});
test("unmount and account changes discard late sensitive responses", async () => {
  const pending = deferred(); let authorized = true;
  const flow = createPaymentLinkFlow({ orderId: "order-1", isAuthorized: () => authorized, request: () => pending.promise });
  const load = flow.load(); authorized = false; pending.resolve(view()); await load;
  assert.equal(flow.getSnapshot().data, null); assert.equal(flow.getSnapshot().phase, "unauthorized");
  const second = deferred(), stopped = createPaymentLinkFlow({ orderId: "order-1", request: () => second.promise });
  const old = stopped.load(); stopped.invalidate(); second.resolve(view()); await old;
  assert.equal(stopped.getSnapshot().data, null);
});
test("another order or unsafe amount cannot become payment instructions", async () => {
  for (const data of [view({ order_id: "other" }), view({ amount: 1.5 }), view({ currency: "USD" })]) {
    const flow = createPaymentLinkFlow({ orderId: "order-1", request: async () => data });
    await flow.load(); assert.equal(flow.getSnapshot().phase, "uncertain"); assert.equal(flow.getSnapshot().data, null);
  }
});

test("session QR is bound to both quote and session, never accepted as an order QR", async () => {
  const fee = view({ order_id: null, quote_id: "fee-1", session_id: "session-1" });
  const build = (data) => createPaymentLinkFlow({ quoteId: "fee-1", sessionId: "session-1", request: async () => data });
  const valid = build(fee); await valid.load(); assert.equal(valid.getSnapshot().phase, "ready");
  for (const data of [{ ...fee, quote_id: "fee-2" }, { ...fee, session_id: "other" }, { ...fee, order_id: "order-1" }]) {
    const wrong = build(data); await wrong.load(); assert.equal(wrong.getSnapshot().data, null);
  }
  const order = createPaymentLinkFlow({ orderId: "order-1", request: async () => fee });
  await order.load(); assert.equal(order.getSnapshot().data, null);
});
