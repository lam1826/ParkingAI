import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { requestMonthlyPassDeactivation } from "../src/pages/MonthlyPass/services/monthlyPassCancellation.js";


test("hủy vé tháng chỉ soft-deactivate và giữ nguyên bản ghi", async () => {
  const calls = [];
  const apiClient = {
    async put(url, body) {
      calls.push({ url, body });
      return { data: { id: 9, is_active: false } };
    },
  };

  const result = await requestMonthlyPassDeactivation(apiClient, 9);

  assert.deepEqual(calls, [{
    url: "/api/v1/monthly-passes/9",
    body: { is_active: false },
  }]);
  assert.equal(result.is_active, false);
});


test("wiring nút Hủy không gọi DELETE vé tháng", async () => {
  const [hookSource, serviceSource] = await Promise.all([
    readFile(new URL("../src/pages/MonthlyPass/hooks/useMonthlyPass.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/MonthlyPass/services/monthlyPassService.js", import.meta.url), "utf8"),
  ]);

  assert.match(hookSource, /monthlyPassService\.deactivate\(selectedPass\.id\)/);
  assert.doesNotMatch(hookSource, /monthlyPassService\.delete\(selectedPass\.id\)/);
  assert.match(serviceSource, /deactivate:/);
});
