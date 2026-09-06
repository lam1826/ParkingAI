import assert from "node:assert/strict";
import test from "node:test";
import { getTicketPresentation } from "../src/pages/ParkingSession/ticketPresentation.js";

test("cancelled ticket is labelled cancelled in its dialog and printed content with no exit action", () => {
  const view = getTicketPresentation({ status: "cancelled", parking_fee: null });
  assert.equal(view.title, "Vé gửi xe đã hủy");
  assert.match(view.summary, /đã hủy/i);
  assert.doesNotMatch(view.summary, /Xe đang trong bãi|Phí gửi xe/);
  assert.equal(view.canCheckOut, false);
  assert.doesNotMatch(view.instruction, /nhận xe/);
});

test("only an active ticket permits checkout; completed ticket preserves a free receipt", () => {
  assert.equal(getTicketPresentation({ status: "active" }).canCheckOut, true);
  const receipt = getTicketPresentation({ status: "completed", parking_fee: 0 });
  assert.equal(receipt.title, "Biên nhận gửi xe");
  assert.equal(receipt.summary, "Phí gửi xe: 0");
  assert.equal(receipt.canCheckOut, false);
});

test("unknown or missing ticket status fails closed instead of claiming the vehicle is parked", () => {
  for (const ticket of [null, {}, { status: "unexpected" }]) {
    const view = getTicketPresentation(ticket);
    assert.equal(view.canCheckOut, false);
    assert.doesNotMatch(view.summary, /Xe đang trong bãi/);
  }
});
