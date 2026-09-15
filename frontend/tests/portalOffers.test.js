import test from "node:test";
import assert from "node:assert/strict";
import { holdRemaining, matchingPlans, ownerCan, portalOrderBody, portalPlanBody, productDuration } from "../src/pages/Expansion/portalOffers.js";

const vehicle = { id: 4, vehicle_type_id: 2 };
const monthly = { id: 1, vehicle_type_id: 2, product_kind: "monthly", duration_days: 30 };
const hourly = { id: 2, vehicle_type_id: 2, product_kind: "hourly", duration_minutes: 120, eligible_zones: [{ id: 8, name: "A" }] };
const daily = { ...hourly, id: 3, product_kind: "daily", duration_minutes: 1440 };
const plans = [monthly, hourly, daily];
const form = { vehicle_id: "4", plan_id: "2", start_at: "2026-09-20T10:00", zone_id: "8", amount: 1, end_at: "2099-01-01" };

test("timed order submits a Vietnamese start and catalog selection, never client money/end/type", () => {
  const body = portalOrderBody(form, plans, [vehicle], "demo", "fixed-request-key");
  assert.deepEqual(body, { vehicle_id: 4, plan_id: 2, start_at: "2026-09-20T10:00:00+07:00", zone_id: 8, payment_mode: "demo", idempotency_key: "fixed-request-key" });
  const assigned = portalOrderBody({ ...form, zone_id: "" }, plans, [vehicle], "manual", "key");
  assert.equal("zone_id" in assigned, false);
});

test("monthly order retains its original body and ignores stale timed input", () => {
  assert.deepEqual(portalOrderBody({ ...form, plan_id: "1", start_at: "invalid" }, plans, [vehicle], "manual", "monthly-key"), {
    plan_id: 1, vehicle_id: 4, payment_mode: "manual", idempotency_key: "monthly-key",
  });
  assert.equal(productDuration(monthly), "30 ngày");
  assert.equal(productDuration(hourly), "2 giờ");
  assert.equal(productDuration(daily), "24 giờ");
});

test("unverified or mismatched vehicles and stale zones cannot submit", () => {
  assert.equal(matchingPlans(plans, { id: 4, vehicle_type_id: 9 }).length, 0);
  for (const [draft, catalog, cars] of [
    [form, plans, []], [form, plans, [{ ...vehicle, vehicle_type_id: 9 }]],
    [{ ...form, zone_id: "9" }, plans, [vehicle]],
    [form, [{ ...hourly, is_active: false }], [vehicle]],
    [form, [{ ...hourly, eligible_zones: [] }], [vehicle]],
    [{ ...form, start_at: "2026-02-30T10:00" }, plans, [vehicle]],
  ]) assert.throws(() => portalOrderBody(draft, catalog, cars, "demo", "key"));
});

test("manager plan payload distinguishes calendar days, whole hours and one 24-hour period", () => {
  const draft = { name: " Gói A ", price: "20000", vehicle_type_id: "2", duration_days: "30", duration_minutes: "120" };
  assert.deepEqual(portalPlanBody({ ...draft, product_kind: "daily" }, { siteId: "1" }), { name: "Gói A", price: 20000, product_kind: "daily", site_id: 1, vehicle_type_id: 2, duration_minutes: 1440 });
  assert.deepEqual(portalPlanBody({ ...draft, product_kind: "hourly" }, { editing: true }), { name: "Gói A", price: 20000, duration_minutes: 120 });
  assert.deepEqual(portalPlanBody({ ...draft, product_kind: "monthly" }, { editing: true }), { name: "Gói A", price: 20000, duration_days: 30 });
  assert.deepEqual(portalPlanBody({ ...draft, product_kind: "daily" }, { editing: true }), { name: "Gói A", price: 20000 });
  for (const duration of [0, 30, 90, 1441, 1500]) assert.throws(() => portalPlanBody({ ...draft, product_kind: "hourly", duration_minutes: duration }, { siteId: 1 }));
});

test("hold clock uses server baseline and never changes the order status", () => {
  const order = { status: "pending", server_now: "2026-09-15T10:00:00+07:00", hold_expires_at: "2026-09-15T10:10:00+07:00" };
  assert.equal(holdRemaining(order), 600);
  assert.equal(holdRemaining(order, 600000), 0);
  assert.equal(holdRemaining(order, 700000), 0);
  assert.equal(order.status, "pending");
  assert.equal(holdRemaining({ hold_expires_at: order.hold_expires_at }), null);
});

test("payment controls require a server action instead of inferring authority from paid/pending", () => {
  assert.equal(ownerCan({ status: "pending" }, "simulate"), false);
  assert.equal(ownerCan({ status: "fulfilled", allowed_actions: [] }, "request_refund"), false);
  assert.equal(ownerCan({ allowed_actions: ["cancel", "simulate"] }, "simulate"), true);
});
