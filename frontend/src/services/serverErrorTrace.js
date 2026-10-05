// A 5xx answer asks the user to quote its trace code (body `request_id`, or the
// exposed X-Request-ID header for handled 500s). The axios interceptor writes
// that code into `response.data.detail`, so getErrorMessage and every ad-hoc
// reader of `detail` show it, and support can look it up in Nhật ký hoạt động.
const TRACE_ID = /^[A-Za-z0-9._-]{1,64}$/;
const SERVER_ERROR_TEXT = "Hệ thống chưa xử lý được yêu cầu. Vui lòng thử lại hoặc cung cấp mã truy vết để được hỗ trợ.";

function isPlainObject(value) {
  if (!value || typeof value !== "object") return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function headerValue(headers, name) {
  if (!headers) return null;
  if (typeof headers.get === "function") return headers.get(name) ?? null;
  return headers[name] ?? headers[name.toLowerCase()] ?? null;
}

/** The trace code of a server response, or null when it carries none. */
export function serverErrorTraceId(response) {
  const body = isPlainObject(response?.data) ? response.data.request_id : null;
  const candidates = [body, headerValue(response?.headers, "x-request-id")];
  for (const candidate of candidates) {
    const value = typeof candidate === "string" ? candidate.trim() : "";
    if (TRACE_ID.test(value)) return value;
  }
  return null;
}

export function traceSuffix(traceId) {
  return `Mã truy vết: ${traceId}`;
}

/**
 * Show the trace code of a 5xx error in its message. Binary or HTML bodies
 * (file downloads, proxy pages) are left untouched. Returns the same error.
 */
export function withServerErrorTrace(error) {
  const response = error?.response;
  if (!response || !(Number(response.status) >= 500)) return error;
  const traceId = serverErrorTraceId(response);
  if (!traceId) return error;
  const data = response.data;
  if (data === undefined || data === null || data === "") {
    response.data = { detail: `${SERVER_ERROR_TEXT} ${traceSuffix(traceId)}.`, request_id: traceId };
  } else if (isPlainObject(data)) {
    const detail = typeof data.detail === "string" ? data.detail.trim() : "";
    if (!detail) {
      if (data.detail === undefined || data.detail === null || data.detail === "") {
        data.detail = `${SERVER_ERROR_TEXT} ${traceSuffix(traceId)}.`;
      }
    } else if (!detail.includes(traceId)) {
      data.detail = `${detail} ${traceSuffix(traceId)}.`;
    }
    if (!data.request_id) data.request_id = traceId;
  } else {
    return error;
  }
  error.traceId = traceId;
  return error;
}
