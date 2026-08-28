import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("dashboard chỉ cho thế hệ refresh mới nhất cập nhật state", async () => {
  const source = await readFile(
    new URL("../src/pages/Dashboard/hooks/useDashboard.js", import.meta.url),
    "utf8",
  );

  assert.match(source, /createLatestRequestGate/);
  assert.match(source, /dashboardRequestGate\.current\.begin\(\)/);
  assert.match(source, /requestGate\.isCurrent\(requestGeneration\)/);
  assert.match(source, /return \(\) => dashboardRequestGate\.current\.invalidate\(\)/);

  const guardedUpdates = source.match(/requestGate\.isCurrent\(requestGeneration\)/g) || [];
  assert.ok(guardedUpdates.length >= 8, "mọi nhánh success/error/finally phải bị chặn bởi generation");
});
