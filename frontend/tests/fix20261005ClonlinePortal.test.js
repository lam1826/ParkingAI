import test from "node:test";
import assert from "node:assert/strict";
import { canManageSite, counterInstruction, managedSiteList, monthlyPaymentNotice, orderReviewActions, paymentDeadline, paymentRemaining } from "../src/pages/Expansion/portalState.js";
import { feePaymentChoice } from "../src/pages/Expansion/customerFlow.js";

const sites = [{ id: 1, name: "A", role: "staff" }, { id: 2, name: "B", role: "manager" }, { id: 3, name: "C", role: "admin" }];

test("#21 portal admin actions are offered only on sites the account manages", () => {
  assert.deepEqual(managedSiteList(sites).map((site) => site.id), [2, 3]);
  assert.equal(canManageSite(sites, 1), false);
  assert.equal(canManageSite(sites, "2"), true);
  assert.equal(canManageSite(sites, null), false);
  assert.deepEqual(managedSiteList(undefined), []);
});

test("#52 order review buttons follow the server's allowed decisions", () => {
  assert.deepEqual(orderReviewActions({ status: "review", payment_mode: "demo", review_actions: ["reject"] }), ["reject"]);
  assert.deepEqual(orderReviewActions({ status: "review", payment_mode: "demo", review_actions: ["approve", "reject"] }), ["approve", "reject"]);
  // An older server response without the field must not invent an approve button.
  assert.deepEqual(orderReviewActions({ status: "review", payment_mode: "demo" }), []);
  assert.deepEqual(orderReviewActions({ review_actions: ["refund", "approve"] }), ["approve"]);
});

const monthlyOrder = { status: "pending", product_kind: "monthly", payment_mode: "manual", hold_expires_at: null,
  payment_deadline: "2026-10-05T10:15:00+07:00", server_now: "2026-10-05T10:00:00+07:00" };

test("#25 a pending monthly counter order exposes its payment deadline and countdown", () => {
  assert.equal(paymentDeadline(monthlyOrder), "2026-10-05T10:15:00+07:00");
  assert.equal(paymentRemaining(monthlyOrder, 0), 900);
  assert.equal(paymentRemaining(monthlyOrder, 60000), 840);
  assert.equal(paymentRemaining(monthlyOrder, 3600000), 0);
  assert.equal(paymentDeadline({ ...monthlyOrder, status: "fulfilled" }), null);
  const timed = { ...monthlyOrder, product_kind: "hourly", hold_expires_at: "2026-10-05T10:10:00+07:00" };
  assert.equal(paymentDeadline(timed), "2026-10-05T10:10:00+07:00");
});

test("#25 the counter instruction states the deadline instead of an open-ended visit", () => {
  const text = counterInstruction(monthlyOrder, () => "10:15 05/10/2026");
  assert.match(text, /trước 10:15 05\/10\/2026/);
  assert.match(text, /hết hiệu lực/);
  const timed = counterInstruction({ ...monthlyOrder, product_kind: "daily", hold_expires_at: "2026-10-05T10:10:00+07:00" }, () => "10:10");
  assert.match(timed, /giữ chỗ/);
  assert.match(counterInstruction({ ...monthlyOrder, payment_deadline: null }, () => "x"), /hạn thanh toán trên đơn/);
});

test("#25 the purchase form warns about the monthly payment window", () => {
  assert.match(monthlyPaymentNotice({ product_kind: "monthly", payment_window_minutes: 15 }, "manual"), /15 phút/);
  assert.match(monthlyPaymentNotice({ product_kind: "monthly", payment_window_minutes: 15 }, "manual"), /tại quầy/);
  assert.equal(monthlyPaymentNotice({ product_kind: "monthly" }, "manual"), "");
});

test("#79 with payOS disabled the fee panel shows counter guidance instead of an online CTA", () => {
  const off = { enabled: false, supported: true, can_quote: false, message: "Thanh toán payOS chưa được bật; bạn vẫn có thể thanh toán tại bãi." };
  assert.deepEqual(feePaymentChoice(off), { online: false, message: off.message });
  assert.equal(feePaymentChoice({ enabled: true, supported: true, can_quote: true, message: "x" }).online, true);
  const legacy = feePaymentChoice({ enabled: true, supported: false, message: "Lượt cũ chưa chốt bảng giá bất biến; vui lòng thanh toán tại bãi." });
  assert.equal(legacy.online, false);
  assert.match(legacy.message, /tại bãi/);
  assert.equal(feePaymentChoice({ enabled: false }).online, false);
  assert.match(feePaymentChoice({ enabled: false }).message, /tại bãi/);
});

test("#79 with payOS disabled the staff fee panel makes counter collection primary and hides QR", async () => {
  const { staffFeeActions } = await import("../src/pages/Expansion/sessionFeeState.js");
  const off = staffFeeActions({ enabled: false, supported: true, session_status: "active", can_quote: false,
    message: "Thanh toán payOS chưa được bật; bạn vẫn có thể thanh toán tại bãi." });
  assert.equal(off.online, false);
  assert.equal(off.primary, "cash");
  assert.deepEqual(off.actions, ["cash", "transfer"]);
  assert.match(off.note, /payOS chưa được bật/);
  assert.match(off.note, /tiền mặt hoặc chuyển khoản/);
  // Unknown status (failed to load) never promotes a QR action.
  assert.equal(staffFeeActions(null).online, false);
  assert.match(staffFeeActions(undefined).note, /tiền mặt hoặc chuyển khoản/);
  // A stay billed without an immutable tariff cannot be paid online either.
  assert.equal(staffFeeActions({ enabled: true, supported: false, session_status: "active" }).online, false);
  const on = staffFeeActions({ enabled: true, supported: true, session_status: "active", can_quote: true });
  assert.deepEqual([on.online, on.primary, on.actions, on.note], [true, "online", ["online", "cash"], ""]);
});

test("#54 the decision note field says whether the note is required and where it goes", async () => {
  const { decisionNoteField } = await import("../src/pages/Expansion/portalState.js");
  const vehicleReject = decisionNoteField("vehicle-requests", false);
  assert.equal(vehicleReject.required, true);
  assert.match(vehicleReject.help, /thông báo cho khách/);
  assert.equal(decisionNoteField("vehicle-requests", true).required, false);
  assert.match(decisionNoteField("link-requests", true).help, /thông báo cho khách/);
  const linkReject = decisionNoteField("link-requests", false);
  assert.equal(linkReject.required, false);
  assert.match(linkReject.help, /không được lưu/);
  assert.equal(decisionNoteField("orders", true).required, true);
});
