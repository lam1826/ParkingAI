// CL-AUTH #64: a 500 that asks the user to quote a trace code shows that code,
// and Nhật ký hoạt động can be filtered by it.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { serverErrorTraceId, withServerErrorTrace } from "../src/services/serverErrorTrace.js";
import { getErrorMessage } from "../src/utils/errorMessage.js";
import { auditLogRequest } from "../src/pages/AuditLog/auditLogQuery.js";

const UNHANDLED = "Hệ thống chưa xử lý được yêu cầu. Vui lòng thử lại hoặc cung cấp mã truy vết để được hỗ trợ.";

function serverError(status, data, headers = {}) {
  return { message: `Request failed with status code ${status}`, response: { status, data, headers } };
}

test("the unhandled-500 trace code reaches the message the user sees", () => {
  const error = withServerErrorTrace(serverError(500, { detail: UNHANDLED, request_id: "trace-unhandled-500" },
    { "x-request-id": "trace-unhandled-500" }));
  const shown = getErrorMessage(error);
  assert.match(shown, /cung cấp mã truy vết/);
  assert.ok(shown.includes("trace-unhandled-500"), shown);
  assert.equal(error.traceId, "trace-unhandled-500");
  // Ad-hoc readers of response.data.detail see the same text.
  assert.equal(error.response.data.detail, shown);
});

test("handled 500s carry the code only in the X-Request-ID header", () => {
  const headers = { get: (name) => (name.toLowerCase() === "x-request-id" ? "abc123" : null) };
  const error = withServerErrorTrace(serverError(500, { detail: "Không thể truy cập cơ sở dữ liệu do lỗi hệ thống." }, headers));
  assert.equal(getErrorMessage(error), "Không thể truy cập cơ sở dữ liệu do lỗi hệ thống. Mã truy vết: abc123.");
  assert.equal(error.response.data.request_id, "abc123");
  const empty = withServerErrorTrace(serverError(503, "", { "x-request-id": "zz-9" }));
  assert.match(getErrorMessage(empty), /Mã truy vết: zz-9\.$/);
});

test("the code is added once, and only to server errors with a valid code", () => {
  const error = serverError(500, { detail: UNHANDLED, request_id: "once" });
  withServerErrorTrace(error);
  withServerErrorTrace(error);
  assert.equal(error.response.data.detail.split("once").length - 1, 1);

  const conflict = withServerErrorTrace(serverError(409, { detail: "Xung đột dữ liệu.", request_id: "nope" }));
  assert.equal(getErrorMessage(conflict), "Xung đột dữ liệu.");
  const forged = withServerErrorTrace(serverError(500, { detail: "Lỗi.", request_id: "<script>" }));
  assert.equal(getErrorMessage(forged), "Lỗi.");
  assert.equal(serverErrorTraceId({ data: { request_id: "x".repeat(65) } }), null);

  // File downloads (Blob) and proxy HTML pages are left untouched.
  const blob = new Blob(["{}"]);
  const download = withServerErrorTrace(serverError(500, blob, { "x-request-id": "file-1" }));
  assert.equal(download.response.data, blob);
  const html = withServerErrorTrace(serverError(502, "<html>Bad gateway</html>", { "x-request-id": "edge-1" }));
  assert.equal(html.response.data, "<html>Bad gateway</html>");
  // Network failures have no response at all: no trace code is attached, and
  // (integration R2, CL-LEDGER request 3) the caller's fallback is shown instead
  // of the raw English axios text.
  const offline = withServerErrorTrace({ message: "Network Error", request: {} });
  assert.equal(offline.traceId, undefined);
  assert.equal(getErrorMessage(offline), "Không thể thực hiện yêu cầu. Vui lòng thử lại.");
});

test("every axios error passes through the trace annotation", async () => {
  const source = await readFile(new URL("../src/services/api.js", import.meta.url), "utf8");
  assert.match(source, /import \{ withServerErrorTrace \} from "\.\/serverErrorTrace"/);
  assert.match(source, /withServerErrorTrace\(error\);\s*\n\s*if \(error\.response\)/);
});

test("the audit log can be filtered by the trace code", async () => {
  assert.deepEqual(auditLogRequest({ requestId: " trace-unhandled-500 " }).params,
    { skip: 0, limit: 26, request_id: "trace-unhandled-500" });
  assert.match(auditLogRequest({ requestId: "bad code!" }).error, /Mã truy vết/);
  const page = await readFile(new URL("../src/pages/AuditLog/AuditLogPage.jsx", import.meta.url), "utf8");
  assert.match(page, /Mã truy vết<input value=\{typed\.requestId\}/);
});
