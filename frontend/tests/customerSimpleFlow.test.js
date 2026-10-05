import assert from "node:assert/strict";
import test from "node:test";
import { advanceBookingBody, feeLookupBody, portalTab, refreshFeeLookup, uncertainMutation, validFeeLookup } from "../src/pages/Expansion/customerFlow.js";
import { chatRequest, chatScopeKey } from "../src/components/ai/chatRequest.js";

const types = [{ id: 1, name: "Ô tô", requires_plate: true }, { id: 2, name: "Xe đạp", requires_plate: false }];
const form = { license_plate: "59a-123.45", vehicle_type_id: "1", start_at: "2026-09-24T00:15", end_at: "2026-09-24T02:15" };
test("advance booking declares identity without ownership or prepayment and uses Vietnam time", () => {
  assert.deepEqual(advanceBookingBody(form, 5, types, "unique-request-id"), { site_id: 5, license_plate: "59A-123.45", vehicle_type_id: 1, start_at: "2026-09-24T00:15:00+07:00", end_at: "2026-09-24T02:15:00+07:00", request_id: "unique-request-id" });
  assert.equal(advanceBookingBody({ ...form, license_plate: "", vehicle_type_id: 2 }, 5, types, "unique-request-id").license_plate, "");
  assert.throws(() => advanceBookingBody({ ...form, license_plate: "" }, 5, types, "unique-request-id"));
  assert.throws(() => advanceBookingBody({ ...form, end_at: form.start_at }, 5, types, "unique-request-id"));
  assert.throws(() => advanceBookingBody({ ...form, start_at: "2026-02-30T00:15" }, 5, types, "unique-request-id"));
});
test("fee lookup sends narrow proof only in request body, never claims ownership", () => {
  const body = feeLookupBody({ ...form, ticket_proof: "  private-proof  " }, 5);
  assert.deepEqual(body, { site_id: 5, license_plate: "59A-123.45", vehicle_type_id: 1, ticket_proof: "private-proof" });
  assert.equal("ticket_proof" in feeLookupBody(form, 5), false);
  assert.throws(() => feeLookupBody({ ...form, ticket_proof: "x".repeat(161) }, 5));
});
test("fee result requires active scoped session and consistent real balance", () => {
  const result = { session: { id: "s-1", license_plate: "59A-123.45", status: "active", check_in_time: "2026-09-24T00:15:00+07:00" }, access: { kind: "ticket" }, payment_status: { session_id: "s-1", gross_fee: 20000, online_paid: 5000, balance_due: 15000 } };
  assert.equal(validFeeLookup(result), true);
  assert.equal(validFeeLookup({ ...result, payment_status: { ...result.payment_status, session_id: "other" } }), false);
  assert.equal(validFeeLookup({ ...result, payment_status: { ...result.payment_status, balance_due: 0 } }), false);
  assert.equal(validFeeLookup({ ...result, session: { ...result.session, status: "completed" } }), false);
});
const ownedLookup = () => ({ session: { id: "owned-stay", license_plate: "30A-999.99", vehicle_type_id: 1,
  status: "active", check_in_time: "2026-10-02T10:00:00+07:00" }, access: { kind: "owned", expires_at: null },
  payment_status: { session_id: "owned-stay", session_status: "active", gross_fee: 50000, online_paid: 0,
    balance_due: 50000, can_quote: false, server_now: "2026-10-02T11:10:00+07:00" } });
test("cash departure updates the lookup state without reinterpreting collected cash as online credit", () => {
  // Exact monetary/state shape observed through real isolated lookup, cash checkout and status APIs.
  const before = ownedLookup();
  const payment = { ...before.payment_status, session_status: "completed" };
  const result = refreshFeeLookup(before, payment);
  assert.equal(result.session.status, "completed");
  assert.equal(result.payment_status.balance_due, 50000, "Completed contract preserves the cashier share already collected");
  assert.equal(result.payment_status.online_paid, 0, "Cash must never be relabelled as online credit");
  assert.equal(result.session.id, before.session.id);
  assert.equal(result.access, before.access);
  assert.equal(before.session.status, "active", "The old snapshot is not mutated");
  assert.equal(validFeeLookup(result), false, "A completed result is not a fresh active lookup");
});
test("cancelled and fully online paid departures become terminal lookup results", () => {
  const before = ownedLookup();
  const cancelled = refreshFeeLookup(before, { ...before.payment_status,
    session_status: "cancelled", gross_fee: 0, balance_due: 0 });
  assert.equal(cancelled.session.status, "cancelled");
  const onlineCompleted = refreshFeeLookup(before, { ...before.payment_status,
    session_status: "completed", online_paid: 50000, balance_due: 0 });
  assert.equal(onlineCompleted.session.status, "completed");
  assert.equal(onlineCompleted.payment_status.online_paid, 50000);
  assert.equal(onlineCompleted.payment_status.balance_due, 0);
});
test("refresh rejects other stays, malformed totals and unknown status instead of retaining old debt", () => {
  const before = ownedLookup();
  for (const change of [{ session_id: "another-stay" }, { balance_due: 0 }, { gross_fee: -1 },
    { online_paid: "0" }, { session_status: "checking_out" }, { session_status: undefined }]) {
    assert.equal(refreshFeeLookup(before, { ...before.payment_status, ...change }), null);
  }
  assert.equal(refreshFeeLookup(before, null), null);
  assert.equal(refreshFeeLookup(null, before.payment_status), null);
});
test("a fresh active balance may change while a closed stay can never reopen", () => {
  const before = ownedLookup();
  const paid = refreshFeeLookup(before, { ...before.payment_status, online_paid: 20000, balance_due: 30000 });
  assert.equal(paid.session.status, "active");
  assert.equal(paid.payment_status.balance_due, 30000);
  for (const terminal of ["completed", "cancelled"]) {
    const closed = refreshFeeLookup(before, { ...before.payment_status, session_status: terminal });
    assert.equal(refreshFeeLookup(closed, before.payment_status), null);
    assert.equal(refreshFeeLookup(closed, { ...before.payment_status, session_status: terminal }).session.status, terminal);
  }
});
test("uncertain booking response keeps original request while validation errors allow correction", () => {
  for (const status of [408, 429, 500, 502]) assert.equal(uncertainMutation({ response: { status } }), true);
  for (const status of [400, 403, 404, 409, 422]) assert.equal(uncertainMutation({ response: { status } }), false);
  assert.equal(uncertainMutation(new Error("network")), true);
});
test("customer chat cannot select internal analysis even through staff/report shortcut", () => {
  for (const action of ["question", "staff", "weekly"]) assert.deepEqual(chatRequest({ role: "customer", siteId: 5, question: "Doanh thu?", action, createKey: () => { throw new Error("must not be called"); } }), { path: "/api/v2/public/sites/5/assistant", body: { question: "Doanh thu?" } });
  assert.throws(() => chatRequest({ role: "guest", siteId: 5, question: "test" }));
  assert.throws(() => chatRequest({ role: "customer", siteId: "", question: "test" }));
});
test("internal chat sends server-scoped request with Vietnam day and role-separated cache", () => {
  const request = chatRequest({ role: "staff", siteId: 5, question: "Báo cáo tuần", action: "weekly", createKey: () => "id", now: new Date("2026-09-23T18:00:00Z") });
  assert.equal(request.path, "/api/v2/sites/5/ai/analyses");
  assert.deepEqual(request.body, { kind: "report", period: "week", anchor_date: "2026-09-24", question: "", request_id: "id" });
  assert.notEqual(chatScopeKey(1, "manager", 5), chatScopeKey(1, "staff", 5));
  assert.notEqual(chatScopeKey(1, "customer", 5), chatScopeKey(2, "customer", 5));
  assert.notEqual(chatScopeKey(1, "customer", 5), chatScopeKey(1, "customer", 6));
});
test("customer query navigation responds to menu changes and preserves old payment returns", () => {
  assert.equal(portalTab(new URLSearchParams("tab=tickets")), 1);
  assert.equal(portalTab(new URLSearchParams("tab=support")), 5);
  assert.equal(portalTab(new URLSearchParams("tab=tickets&view=history")), 3);
  assert.equal(portalTab(new URLSearchParams("order=123")), 2);
  assert.equal(portalTab(new URLSearchParams("tab=purchase&kind=monthly")), 2);
  assert.equal(portalTab(new URLSearchParams("tab=vehicles")), 0);
  assert.equal(portalTab(new URLSearchParams("tab=notifications")), 4);
});
