import assert from "node:assert/strict";
import test from "node:test";
import { createCheckoutFlow } from "../src/pages/ParkingSession/checkoutFlow.js";

const quote = (changes = {}) => ({ session_id: "A", quote_token: "quote-1", license_plate: "59A-12345", check_in_time: "2026-09-06T08:00:00+07:00", quoted_at: "2026-09-06T10:00:00+07:00", expires_at: "2026-09-06T10:02:00+07:00", duration_minutes: 120, parking_fee: 25000, monthly_coverage_end: null, slot_name: "A01", zone_name: "Khu A", ...changes });
function deferred() { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function setup(overrides = {}) {
  let clock = 1000;
  const writes = []; const reads = []; const completed = [];
  const flow = createCheckoutFlow({ sessionId: "A", now: () => clock, isAuthorized: () => true,
    loadQuote: async id => { reads.push(id); return quote(); },
    confirmCheckout: async (id, body) => { writes.push({ id, body }); return { id, status: "completed", parking_fee: 25000 }; },
    onCompleted: result => completed.push(result), ...overrides });
  return { flow, writes, reads, completed, setTime: value => { clock = value; } };
}
function approve(flow, method = "cash") { flow.setPaymentMethod(method); flow.setPaymentConfirmed(true); }

test("preview/cancel never writes, and paid checkout requires both method and explicit confirmation", async () => {
  const { flow, writes } = setup();
  await flow.start();
  assert.equal(flow.getSnapshot().paymentMethod, "");
  assert.equal(flow.getSnapshot().paymentConfirmed, false);
  await flow.submit(); assert.equal(writes.length, 0);
  flow.setPaymentMethod("cash");
  await flow.submit(); assert.equal(writes.length, 0);
  flow.stop(); await flow.submit(); assert.equal(writes.length, 0);
});

test("double confirmation produces one request and one completion", async () => {
  const pending = deferred(); const writes = [];
  const { flow, completed } = setup({ confirmCheckout: async (id, body) => { writes.push({ id, body }); return pending.promise; } });
  await flow.start(); approve(flow, "transfer");
  const first = flow.submit(); const second = flow.submit();
  assert.equal(flow.getSnapshot().phase, "submitting"); assert.equal(writes.length, 1);
  pending.resolve({ id: "A", status: "completed", parking_fee: 25000 });
  await Promise.all([first, second]);
  assert.deepEqual(writes[0].body, { quote_token: "quote-1", payment_confirmed: true, payment_method: "transfer" });
  assert.equal(completed.length, 1);
});

test("zero fee uses the explicit free exit action and never sends a payment method", async () => {
  const { flow, writes } = setup({ loadQuote: async () => quote({ parking_fee: 0 }) });
  await flow.start(); flow.setPaymentMethod("cash"); await flow.submit();
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].body, { quote_token: "quote-1", payment_confirmed: true, payment_method: null });
});

test("expiry before the first write loads a fresh fee and clears approval without charging", async () => {
  let loads = 0;
  const { flow, writes, setTime } = setup({ loadQuote: async () => quote({ quote_token: `Q${++loads}` }) });
  await flow.start(); approve(flow); setTime(121001); await flow.submit();
  assert.equal(loads, 2); assert.equal(writes.length, 0);
  assert.equal(flow.getSnapshot().quote.quote_token, "Q2");
  assert.equal(flow.getSnapshot().paymentConfirmed, false);
  assert.equal(flow.getSnapshot().paymentMethod, "");
});

test("unknown network outcome replays the identical body even after expiry; no refresh or method change", async () => {
  let loads = 0; const writes = [];
  const { flow, setTime } = setup({ loadQuote: async () => { loads += 1; return quote(); }, confirmCheckout: async (id, body) => {
    writes.push(body); if (writes.length === 1) throw new Error("Network Error"); return { id, status: "completed" };
  } });
  await flow.start(); approve(flow, "transfer"); await flow.submit();
  assert.equal(flow.getSnapshot().phase, "uncertain"); assert.equal(flow.canDismiss(), false);
  setTime(999999); flow.setPaymentMethod("cash"); flow.setPaymentConfirmed(false); await flow.refresh(); await flow.submit();
  assert.equal(loads, 1); assert.equal(writes.length, 2); assert.equal(writes[0], writes[1]);
  assert.equal(writes[1].payment_method, "transfer");
});

test("quote 409 requires fresh confirmation with the new fee", async () => {
  let loads = 0; let writes = 0;
  const { flow } = setup({ loadQuote: async () => quote({ quote_token: `Q${++loads}`, parking_fee: loads * 10000 }), confirmCheckout: async () => {
    writes += 1; throw { response: { status: 409, data: { detail: { code: "checkout_quote_changed", message: "Phí đã thay đổi" } } } };
  } });
  await flow.start(); approve(flow); await flow.submit();
  assert.equal(flow.getSnapshot().quote.parking_fee, 20000);
  assert.equal(flow.getSnapshot().paymentConfirmed, false); assert.match(flow.getSnapshot().notice, /xác nhận lại/i);
  await flow.submit(); assert.equal(writes, 1);
});

test("late quote and completion are ignored on unmount or auth change", async () => {
  const pending = deferred(); const a = setup({ loadQuote: () => pending.promise });
  const loading = a.flow.start(); a.flow.stop(); pending.resolve(quote()); await loading;
  assert.equal(a.flow.getSnapshot().quote, null);
  let authorized = true; const checkout = deferred();
  const b = setup({ isAuthorized: () => authorized, confirmCheckout: () => checkout.promise });
  await b.flow.start(); approve(b.flow); const submitting = b.flow.submit(); authorized = false;
  checkout.resolve({ id: "A", status: "completed" }); await submitting;
  assert.equal(b.completed.length, 0);
});

test("mismatched or malformed quotes never enable payment; failures remain visible", async () => {
  for (const invalid of [quote({ session_id: "B" }), quote({ parking_fee: -1 }), quote({ parking_fee: null }), quote({ expires_at: "invalid" }), quote({ quote_token: "" })]) {
    const { flow, writes } = setup({ loadQuote: async () => invalid });
    await flow.start(); assert.equal(flow.getSnapshot().phase, "error");
    approve(flow); await flow.submit(); assert.equal(writes.length, 0);
  }
});

test("server 5xx keeps the same approved request; a definitive conflict never reprices automatically", async () => {
  const writes = []; let loads = 0;
  const { flow } = setup({ loadQuote: async () => { loads += 1; return quote(); }, confirmCheckout: async (id, body) => {
    writes.push(body);
    if (writes.length === 1) throw { response: { status: 503 } };
    throw { response: { status: 409, data: { detail: { code: "checkout_confirmation_conflict", message: "Lượt này đã được xác nhận bởi người khác." } } } };
  } });
  await flow.start(); approve(flow); await flow.submit();
  assert.equal(flow.getSnapshot().phase, "uncertain");
  await flow.submit();
  assert.equal(writes[0], writes[1]); assert.equal(loads, 1);
  assert.equal(flow.getSnapshot().phase, "error"); assert.equal(flow.getSnapshot().quote, null);
  assert.equal(flow.getSnapshot().error, "Lượt này đã được xác nhận bởi người khác.");
  assert.equal(flow.canDismiss(), true);
});

test("a method change resets receipt confirmation and an expired preview cannot remain actionable", async () => {
  const { flow, setTime, writes } = setup();
  await flow.start(); approve(flow); flow.setPaymentMethod("transfer");
  assert.equal(flow.getSnapshot().paymentConfirmed, false);
  await flow.submit(); assert.equal(writes.length, 0);
  setTime(121000); flow.tick(); assert.equal(flow.getSnapshot().expired, true);
});

test("slow quote reads consume TTL; a restarted flow ignores the previous session request", async () => {
  const first = deferred(); let requests = 0;
  const { flow, setTime } = setup({ loadQuote: () => { requests += 1; return requests === 1 ? first.promise : Promise.resolve(quote({ quote_token: "new" })); } });
  const old = flow.start(); flow.stop(); setTime(3000); await flow.start();
  first.resolve(quote({ quote_token: "old" })); await old;
  assert.equal(flow.getSnapshot().quote.quote_token, "new");
  assert.equal(flow.getSnapshot().expiresAt, 123000);
});
