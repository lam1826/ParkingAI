import { toBusinessDateString } from "./businessDate.js";

export function sessionSearchParams(page, filters) {
  const params = { ...page };
  for (const key of ["license_plate", "status", "date_from", "date_to"]) {
    if (filters[key]) params[key] = filters[key];
  }
  return params;
}

export function analysisPayload({ kind, period, anchorDate, question, requestId }, now = new Date()) {
  return { kind, period, anchor_date: anchorDate || toBusinessDateString(now),
    question: kind === "question" ? question.trim() : "", request_id: requestId };
}
