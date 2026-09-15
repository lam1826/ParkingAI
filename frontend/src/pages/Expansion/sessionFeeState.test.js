import test from "node:test";
import assert from "node:assert/strict";
import { createSessionFeeFlow } from "./sessionFeeState.js";
const balance = { session_id: "A", gross_fee: 10000, online_paid: 5000, balance_due: 5000, enabled: true, can_quote: true, latest_quote: null };
const quote = { ...balance, id: "Q", status: "pending", expires_at: "2026-09-15T10:05:00+07:00" };
const make = (overrides = {}) => createSessionFeeFlow({ sessionId: "A", loadStatus: async () => balance, createQuote: async () => quote, createKey: () => "same-key", ...overrides });
test("reading a balance creates no payment; disabled and zero-due status cannot create quotes", async () => {
  let writes = 0;
  for (const data of [{ ...balance, enabled: false }, { ...balance, can_quote: false, online_paid: 10000, balance_due: 0 }]) {
    const flow = make({ loadStatus: async () => data, createQuote: async () => { writes++; return quote; } });
    await flow.load(); await flow.create();
  }
  assert.equal(writes, 0);
});
test("unknown create result preserves exact request and does not allow another quote or status overwrite", async () => {
  const calls = []; let reads = 0;
  const flow = make({ loadStatus: async () => { reads++; return balance; }, createQuote: async (body) => {
    calls.push(body); if (calls.length === 1) throw new Error("lost"); return quote;
  } });
  await flow.load(); await flow.create(); assert.equal(flow.getSnapshot().phase, "uncertain");
  await flow.load(); assert.equal(reads, 1); await flow.create();
  assert.equal(calls[0], calls[1]); assert.deepEqual(calls[1], { request_id: "same-key" });
  assert.equal(flow.getSnapshot().data.latest_quote.id, "Q"); await flow.create(); assert.equal(calls.length, 2);
});
test("mismatched source or inconsistent amounts fail closed", async () => {
  for (const data of [{ ...balance, session_id: "B" }, { ...balance, balance_due: 0 }, { ...balance, latest_quote: { ...quote, session_id: "B" } }]) {
    const flow = make({ loadStatus: async () => data }); await flow.load();
    assert.equal(flow.getSnapshot().phase, "error"); assert.equal(flow.getSnapshot().data, null);
  }
});
test("quote crossing a billing block updates visible totals without marking proposed coverage as paid", async () => {
  const flow = make({ loadStatus: async () => ({ ...balance, paid_through: "2026-09-15T09:00:00+07:00" }),
    createQuote: async () => ({ ...quote, gross_fee: 15000, balance_due: 10000, paid_through: "2026-09-15T11:00:00+07:00" }) });
  await flow.load(); await flow.create();
  assert.equal(flow.getSnapshot().data.balance_due, 10000);
  assert.equal(flow.getSnapshot().data.gross_fee, 15000);
  assert.equal(flow.getSnapshot().data.paid_through, "2026-09-15T09:00:00+07:00");
});
test("late status response after unmount or authentication change is discarded", async () => {
  let resolve, allowed = true;
  const flow = make({ loadStatus: () => new Promise((yes) => { resolve = yes; }), isAuthorized: () => allowed });
  const task = flow.load(); allowed = false; resolve(balance); await task;
  assert.equal(flow.getSnapshot().phase, "unauthorized"); assert.equal(flow.getSnapshot().data, null);
  allowed = true; const second = flow.load(); flow.invalidate(); resolve(balance); await second;
  assert.equal(flow.getSnapshot().data, null);
});
