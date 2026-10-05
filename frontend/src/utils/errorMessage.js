// Axios failures without a server answer: the request may or may not have been
// applied, so the caller's fallback (e.g. "Chưa xác nhận được kết quả…") is shown
// instead of the raw English axios text ("Network Error", "timeout of …").
const TRANSPORT_CODES = new Set(["ECONNABORTED", "ETIMEDOUT", "ERR_NETWORK", "ERR_CANCELED"]);
function transportFailure(error) {
  return !error?.response && (error?.isAxiosError === true || error?.request != null || TRANSPORT_CODES.has(error?.code));
}

/** FastAPI detail may be a list of validation objects, never a React child. */
export function getErrorMessage(error, fallback = "Không thể thực hiện yêu cầu. Vui lòng thử lại.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => typeof item === "string" ? item : item?.msg)
      .filter((item) => typeof item === "string" && item.trim());
    if (messages.length) return [...new Set(messages)].join(". ");
  }
  if (transportFailure(error)) return fallback;
  // An error the page threw itself (no request involved) carries its own message.
  if (typeof error?.message === "string" && error.message.trim() && !error.response) return error.message;
  return fallback;
}
