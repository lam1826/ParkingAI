import assert from "node:assert/strict";
import test from "node:test";

import { extractReportDownloadErrorMessage } from "../src/pages/Report/services/reportDownloadError.js";


test("export đọc detail tiếng Việt từ Blob JSON lỗi của FastAPI", async () => {
  const error = {
    response: {
      data: new Blob(
        [JSON.stringify({ detail: "Khoảng ngày báo cáo không hợp lệ." })],
        { type: "application/json" },
      ),
    },
  };

  assert.equal(
    await extractReportDownloadErrorMessage(error, "Lỗi dự phòng"),
    "Khoảng ngày báo cáo không hợp lệ.",
  );
});


test("export chuẩn hóa detail 422 dạng mảng trong Blob", async () => {
  const error = {
    response: {
      data: new Blob([
        JSON.stringify({
          detail: [
            { loc: ["query", "anchor_date"], msg: "Input should be a valid date" },
          ],
        }),
      ]),
    },
  };

  assert.equal(
    await extractReportDownloadErrorMessage(error, "Lỗi dự phòng"),
    "anchor_date: Input should be a valid date",
  );
});


test("export dùng detail object thường và fallback an toàn cho Blob hỏng", async () => {
  assert.equal(
    await extractReportDownloadErrorMessage(
      { response: { data: { detail: "Không đủ quyền xuất báo cáo." } } },
      "Lỗi dự phòng",
    ),
    "Không đủ quyền xuất báo cáo.",
  );

  assert.equal(
    await extractReportDownloadErrorMessage(
      { response: { data: new Blob(["not-json"]) } },
      "Lỗi dự phòng",
    ),
    "Lỗi dự phòng",
  );
});
