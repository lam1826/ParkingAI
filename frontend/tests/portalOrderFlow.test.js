import test from "node:test";
import assert from "node:assert/strict";
import { createPortalOrderFlow } from "../src/pages/Expansion/portalOrderFlow.js";

const input = (key) => ({ plan_id: 2, vehicle_id: 4, idempotency_key: key, start_at: "2026-09-20T10:00:00+07:00" });
const success = { id: "order-1", status: "pending" };

test("unknown network result freezes the original payload/key and prevents a second draft", async () => {
  const sent = [], created = [];
  let nextKey = 0;
  const flow = createPortalOrderFlow({ createKey: () => `key-${++nextKey}`, onCreated: (order) => created.push(order),
    createOrder: async (body) => { sent.push(body); if (sent.length === 1) throw new Error("network"); return success; } });
  await flow.submit(input);
  assert.equal(flow.getSnapshot().phase, "uncertain");
  assert.equal(flow.canReset(), false);
  flow.reset();
  await flow.submit(() => ({ plan_id: 99 }));
  assert.strictEqual(sent[0], sent[1]);
  assert.equal(sent[1].plan_id, 2);
  assert.equal(sent[1].idempotency_key, "key-1");
  assert.equal(created.length, 1);
  await flow.submit(input);
  assert.equal(sent.length, 2);
  flow.reset();
  assert.equal(flow.getSnapshot().key, "key-2");
});

test("double submit while pending issues only one create request", async () => {
  let resolve, calls = 0;
  const flow = createPortalOrderFlow({ createKey: () => "key", createOrder: () => { calls += 1; return new Promise((done) => { resolve = done; }); } });
  const first = flow.submit(input);
  await flow.submit(input);
  assert.equal(calls, 1);
  assert.equal(flow.canReset(), false);
  resolve(success); await first;
  assert.equal(flow.getSnapshot().phase, "completed");
});

test("definitive validation failures allow correction; 408/429/5xx retain the original attempt", async () => {
  for (const status of [400, 409, 422, 408, 429, 500]) {
    const flow = createPortalOrderFlow({ createKey: () => "key", createOrder: async () => { throw { response: { status, data: { detail: "Không có chỗ" } } }; } });
    await flow.submit(input);
    assert.equal(flow.getSnapshot().phase, [400, 409, 422].includes(status) ? "editing" : "uncertain");
  }
});

test("invalid local form makes no request; a malformed server success remains uncertain", async () => {
  let calls = 0;
  const flow = createPortalOrderFlow({ createKey: () => "key", createOrder: async () => { calls += 1; return {}; } });
  await flow.submit(() => { throw new Error("Chọn xe"); });
  assert.equal(calls, 0);
  assert.equal(flow.getSnapshot().phase, "editing");
  await flow.submit(input);
  assert.equal(flow.getSnapshot().phase, "uncertain");
});

test("account changes cannot display another account's late order response", async () => {
  let authorized = true, resolve, created = false;
  const flow = createPortalOrderFlow({ createKey: () => "key", isAuthorized: () => authorized,
    createOrder: () => new Promise((done) => { resolve = done; }), onCreated: () => { created = true; } });
  const result = flow.submit(input); authorized = false; resolve(success); await result;
  assert.equal(flow.getSnapshot().phase, "uncertain");
  assert.equal(flow.getSnapshot().order, null);
  assert.equal(created, false);
});
