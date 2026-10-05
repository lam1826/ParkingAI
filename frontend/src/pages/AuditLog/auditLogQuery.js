// The audit table grows without limit, so the page asks the server for ONE
// display page at a time (skip/limit tied to the page controls) instead of
// downloading every matching row on each filter change.
export const AUDIT_PAGE_SIZE = 25;
// Typed filters wait for a pause before querying; selects apply immediately.
export const AUDIT_TEXT_FILTER_DELAY_MS = 400;

const TRACE_ID = /^[A-Za-z0-9._-]{1,64}$/;

/**
 * Query for one display page. One extra row tells whether a next page exists.
 * Returns { params } or { error } when the trace code cannot be valid.
 */
export function auditLogRequest({ action = "", username = "", success = "", requestId = "" } = {}, page = 0) {
  const pageIndex = Number.isInteger(page) && page > 0 ? page : 0;
  const params = { skip: pageIndex * AUDIT_PAGE_SIZE, limit: AUDIT_PAGE_SIZE + 1 };
  if (action) params.action = action;
  const name = String(username ?? "").trim().slice(0, 50);
  if (name) params.username = name;
  if (success !== "" && success !== null && success !== undefined) params.success = success;
  const trace = String(requestId ?? "").trim();
  if (trace) {
    if (!TRACE_ID.test(trace)) {
      return { error: "Mã truy vết chỉ gồm chữ, số và các ký tự . _ - (tối đa 64 ký tự)." };
    }
    params.request_id = trace;
  }
  return { params };
}

/** Rows to show for the page plus whether the server has more. */
export function auditLogPageView(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return { rows: list.slice(0, AUDIT_PAGE_SIZE), hasNext: list.length > AUDIT_PAGE_SIZE };
}

/** True when the typed text filters differ from the ones being queried. */
export function textFiltersPending(typed, applied) {
  return String(typed?.username ?? "") !== String(applied?.username ?? "")
    || String(typed?.requestId ?? "") !== String(applied?.requestId ?? "");
}
