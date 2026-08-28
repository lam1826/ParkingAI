import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { requestSessionCheckout } from "../src/pages/ParkingSession/services/parkingSessionCheckout.js";


test("checkout dùng đúng session ID và endpoint idempotent", async () => {
  const calls = [];
  const apiClient = {
    async put(url, body) {
      calls.push({ url, body });
      return { data: { id: "session-B", status: "completed", parking_fee: 25000 } };
    },
  };

  const result = await requestSessionCheckout(apiClient, "session-B");

  assert.deepEqual(calls, [{
    url: "/api/v1/parking-sessions/session-B/check-out",
    body: {},
  }]);
  assert.equal(result.id, "session-B");
});


test("wiring checkout giữ cả phiên được chọn, không tra lại theo biển số", async () => {
  const [tableSource, hookSource, serviceSource] = await Promise.all([
    readFile(new URL("../src/pages/ParkingSession/components/SessionTable.jsx", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/ParkingSession/hooks/useParkingSession.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/ParkingSession/services/parkingSessionService.js", import.meta.url), "utf8"),
  ]);

  assert.match(tableSource, /setSelectedSession\(params\.row\)/);
  assert.match(tableSource, /onCheckOut\(selectedSession\.id\)/);
  assert.doesNotMatch(tableSource, /setSelectedPlate/);
  assert.match(hookSource, /handleCheckOut = async \(sessionId\)/);
  assert.match(serviceSource, /requestSessionCheckout\(api, sessionId\)/);
  assert.doesNotMatch(serviceSource, /post\("\/parking\/check-out"/);
});
