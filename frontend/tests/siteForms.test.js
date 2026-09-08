import test from "node:test";
import assert from "node:assert/strict";
import { bookingBody, bookingTimestamp, checkoutAdapters, nextBookingWindow } from "../src/pages/Expansion/siteForms.js";
import { createCheckoutFlow } from "../src/pages/ParkingSession/checkoutFlow.js";

const form = { vehicle_id: "3", slot_id: "7", start_at: "2026-09-07T09:00", end_at: "2026-09-07T11:00" };

test("booking timestamps preserve Vietnam business time independently of workstation timezone", () => {
  assert.equal(bookingTimestamp(form.start_at), "2026-09-07T09:00:00+07:00");
  assert.equal(Date.parse(bookingTimestamp(form.start_at)), Date.parse("2026-09-07T02:00:00Z"));
  assert.deepEqual(nextBookingWindow(Date.parse("2026-12-31T16:58:21Z")), { start_at: "2027-01-01T00:04", end_at: "2027-01-01T02:04" });
});

test("impossible calendar dates, missing zones, and reversed windows are rejected", () => {
  for (const value of ["2026-02-29T10:00", "2026-04-31T09:00", "2026-09-07", "2026-09-07T24:00", "2026-09-07T09:60"]) {
    assert.throws(() => bookingTimestamp(value));
  }
  assert.equal(bookingTimestamp("2028-02-29T10:00"), "2028-02-29T10:00:00+07:00");
  assert.throws(() => bookingBody(form, "", "request-111111111"));
  assert.throws(() => bookingBody({ ...form, end_at: form.start_at }, 1, "request-111111111"));
});

test("booking body drops client authority and retains identity for exact retries", () => {
  const untrusted = { ...form, customer_id: 8, status: "arrived", price: 0, is_occupied: false };
  const first = bookingBody(untrusted, 2, "request-111111111");
  assert.deepEqual(first, { site_id: 2, vehicle_id: 3, slot_id: 7, start_at: "2026-09-07T09:00:00+07:00", end_at: "2026-09-07T11:00:00+07:00", request_id: "request-111111111" });
  assert.deepEqual(bookingBody(untrusted, 2, "request-111111111"), first);
  assert.equal("slot_id" in bookingBody(form, 2, "request-111111111", { waitlist: true }), false);
});

test("numeric identifiers must be positive safe integers", () => {
  for (const value of ["-1", "0", "1.5", "9007199254740993", "abc"]) {
    assert.throws(() => bookingBody({ ...form, vehicle_id: value }, 1, "request-111111111"));
    assert.throws(() => bookingBody({ ...form, slot_id: value }, 1, "request-111111111"));
  }
});

test("scoped checkout uses signed quote and retries the same body after a network failure", async () => {
  const gets = [], puts = [];
  let clock = 0;
  const adapters = checkoutAdapters({
    get: async (path) => { gets.push(path); return { data: { session_id: "S", quote_token: "signed-quote", license_plate: "51A12345", parking_fee: 12000, duration_minutes: 60, check_in_time: "2026-09-07T08:00:00+07:00", quoted_at: "2026-09-07T09:00:00+07:00", expires_at: "2026-09-07T09:02:00+07:00" } }; },
    put: async (path, body) => { puts.push({ path, body }); if (puts.length === 1) throw new Error("Connection interrupted"); return { data: { id: "S", status: "completed" } }; },
  }, 12);
  const flow = createCheckoutFlow({ sessionId: "S", ...adapters, now: () => clock });
  await flow.start();
  await flow.submit();
  assert.equal(puts.length, 0);
  flow.setPaymentMethod("cash"); flow.setPaymentConfirmed(true); await flow.submit();
  assert.equal(flow.getSnapshot().phase, "uncertain");
  clock = 999999; await flow.submit();
  assert.equal(flow.getSnapshot().phase, "completed");
  assert.deepEqual(gets, ["/api/v2/sites/12/sessions/S/checkout-quote"]);
  assert.equal(puts[0].path, "/api/v2/sites/12/sessions/S/check-out");
  assert.equal(puts[0].body, puts[1].body);
  assert.deepEqual(puts[0].body, { quote_token: "signed-quote", payment_confirmed: true, payment_method: "cash" });
  flow.stop();
});
