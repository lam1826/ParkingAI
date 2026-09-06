import assert from "node:assert/strict";
import test from "node:test";

import { requestCheckoutQuote, requestSessionCheckout } from "../src/pages/ParkingSession/services/parkingSessionCheckout.js";


test("checkout dùng đúng session ID và endpoint idempotent", async () => {
  const calls = [];
  const apiClient = {
    async put(url, body) {
      calls.push({ url, body });
      return { data: { id: "session-B", status: "completed", parking_fee: 25000 } };
    },
  };

  const body = Object.freeze({ quote_token: "signed-Q", payment_confirmed: true, payment_method: "transfer" });
  const result = await requestSessionCheckout(apiClient, "session-B", body);

  assert.deepEqual(calls, [{
    url: "/api/v1/parking-sessions/session-B/check-out",
    body,
  }]);
  assert.equal(result.id, "session-B");
});


test("preview only reads the selected session without a payment write", async () => {
  const calls = [];
  const quote = await requestCheckoutQuote({ async get(url) { calls.push(url); return { data: { parking_fee: 25000 } }; } }, "session/B");
  assert.deepEqual(calls, ["/api/v1/parking-sessions/session%2FB/checkout-quote"]);
  assert.equal(quote.parking_fee, 25000);
});

test("missing confirmation cannot write; server errors reach the dialog unchanged", async () => {
  let writes = 0;
  const conflict = { response: { status: 409, data: { detail: "Phí đã thay đổi" } } };
  const client = { async put() { writes += 1; throw conflict; } };
  await assert.rejects(requestSessionCheckout(client, "A"), /xác nhận/i);
  await assert.rejects(requestSessionCheckout(client, "A", { quote_token: "Q", payment_confirmed: false, payment_method: "cash" }), /xác nhận/i);
  assert.equal(writes, 0);
  await assert.rejects(requestSessionCheckout(client, "A", { quote_token: "Q", payment_confirmed: true, payment_method: null }), error => error === conflict);
  assert.equal(writes, 1);
});
