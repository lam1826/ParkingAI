import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const insightCardSource = readFileSync(
  new URL("../src/pages/Dashboard/components/AIInsightCard.jsx", import.meta.url),
  "utf8",
);
const dashboardHookSource = readFileSync(
  new URL("../src/pages/Dashboard/hooks/useDashboard.js", import.meta.url),
  "utf8",
);

test("Dashboard ghi đúng provenance: gợi ý theo quy tắc, không gắn nhãn Gemini/AI", () => {
  assert.doesNotMatch(insightCardSource, /AI Insight/);
  assert.doesNotMatch(insightCardSource, /Gemini AI/);
  assert.match(insightCardSource, /Gợi ý vận hành/);
  assert.match(insightCardSource, /label="Theo quy tắc"/);

  assert.doesNotMatch(dashboardHookSource, /AI Service/);
  assert.match(dashboardHookSource, /Không thể tải gợi ý vận hành/);
});
