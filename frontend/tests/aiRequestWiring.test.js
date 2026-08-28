import assert from "node:assert/strict";
import test from "node:test";

import {
  AI_REQUEST_TIMEOUT_MS,
  requestAI,
  requestDailyReport,
  requestWeeklyReport,
} from "../src/services/aiReportService.js";

// Đợt 10A — bổ sung theo yêu cầu: chuyển từ test đọc source bằng regex sang
// BEHAVIORAL test thật. Gọi thẳng module service/action thuần
// (aiReportService.js), truyền fake apiClient để capture chính xác URL và
// payload đã gửi, truyền `now` cố định để test hoàn toàn deterministic —
// không đọc source bằng regex, không mạng, không render JSX.
//
// Lịch sử: bằng chứng RED/GREEN của bộ test REGEX cũ (đọc trực tiếp source
// AIPage.jsx/AIChatbot.jsx) vẫn được giữ nguyên tại
// scratchpad/ai_wiring_RED_evidence.txt và ai_wiring_GREEN_evidence.txt làm
// mốc lịch sử — không còn là bằng chứng cho bộ test HIỆN TẠI. Bằng chứng
// RED/GREEN mới cho bộ test behavioral này nằm tại
// scratchpad/ai_report_service_RED_evidence.txt / _GREEN_evidence.txt.

function fakeApiClient() {
  const calls = [];
  return {
    calls,
    post(url, payload, config) {
      calls.push({ url, payload, config });
      return Promise.resolve({ data: { content: "stub" } });
    },
  };
}

test("mọi AI request dùng timeout riêng 90 giây thay vì timeout API chung 10 giây", async () => {
  const client = fakeApiClient();

  await requestAI(client, "/ai/question", { question: "Tình hình hôm nay?" });

  assert.equal(AI_REQUEST_TIMEOUT_MS, 90_000);
  assert.deepEqual(client.calls[0].config, { timeout: AI_REQUEST_TIMEOUT_MS });
});

test("requestDailyReport: gọi đúng /ai/daily-report với target_date theo giờ VN của `now`", async () => {
  const now = new Date("2026-03-10T10:00:00Z"); // VN 2026-03-10 17:00
  const client = fakeApiClient();

  await requestDailyReport(client, now);

  assert.equal(client.calls.length, 1);
  assert.equal(client.calls[0].url, "/ai/daily-report");
  assert.deepEqual(client.calls[0].payload, { target_date: "2026-03-10" });
});

test("requestWeeklyReport: gọi đúng /ai/weekly-report với start_date/end_date cách nhau đúng 6 ngày, cùng tính từ `now`", async () => {
  const now = new Date("2026-03-10T10:00:00Z"); // VN 2026-03-10 17:00
  const client = fakeApiClient();

  await requestWeeklyReport(client, now);

  assert.equal(client.calls.length, 1);
  assert.equal(client.calls[0].url, "/ai/weekly-report");
  assert.deepEqual(client.calls[0].payload, {
    start_date: "2026-03-04",
    end_date: "2026-03-10",
  });
});

test("boundary VN 00:00:00 — instant đúng nửa đêm VN phải dùng ngày MỚI cho cả daily và weekly", async () => {
  // UTC 2025-12-31T17:00:00Z = VN 2026-01-01T00:00:00 (đúng mốc, chưa qua giây nào)
  const now = new Date("2025-12-31T17:00:00Z");

  const dailyClient = fakeApiClient();
  await requestDailyReport(dailyClient, now);
  assert.deepEqual(dailyClient.calls[0].payload, { target_date: "2026-01-01" });

  const weeklyClient = fakeApiClient();
  await requestWeeklyReport(weeklyClient, now);
  assert.deepEqual(weeklyClient.calls[0].payload, {
    start_date: "2025-12-26",
    end_date: "2026-01-01",
  });
});

test("boundary VN 23:59:59.999 — một khắc trước nửa đêm VN vẫn thuộc ngày CŨ", async () => {
  // UTC 2025-12-31T16:59:59.999Z = VN 2025-12-31T23:59:59.999 (chưa sang ngày mới)
  const now = new Date("2025-12-31T16:59:59.999Z");

  const client = fakeApiClient();
  await requestDailyReport(client, now);
  assert.deepEqual(client.calls[0].payload, { target_date: "2025-12-31" });
});

test("requestDailyReport/requestWeeklyReport: chỉ gọi apiClient.post đúng MỘT lần mỗi action", async () => {
  const now = new Date("2026-05-20T04:00:00Z");
  const dailyClient = fakeApiClient();
  const weeklyClient = fakeApiClient();

  await requestDailyReport(dailyClient, now);
  await requestWeeklyReport(weeklyClient, now);

  assert.equal(dailyClient.calls.length, 1, "daily report chỉ được gọi post() đúng 1 lần");
  assert.equal(weeklyClient.calls.length, 1, "weekly report chỉ được gọi post() đúng 1 lần");
});

test("requestWeeklyReport: hai lần gọi liên tiếp với hai `now` khác nhau cho hai kết quả độc lập, không dính trạng thái/cache", async () => {
  const client = fakeApiClient();
  const nowA = new Date("2026-03-10T10:00:00Z"); // VN 2026-03-10
  const nowB = new Date("2026-07-01T10:00:00Z"); // VN 2026-07-01

  await requestWeeklyReport(client, nowA);
  await requestWeeklyReport(client, nowB);

  assert.deepEqual(client.calls[0].payload, { start_date: "2026-03-04", end_date: "2026-03-10" });
  assert.deepEqual(client.calls[1].payload, { start_date: "2026-06-25", end_date: "2026-07-01" });
});
