import assert from "node:assert/strict";
import test from "node:test";
import { advanceBookingBody, feeLookupBody, portalTab, uncertainMutation, validFeeLookup } from "../src/pages/Expansion/customerFlow.js";
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
