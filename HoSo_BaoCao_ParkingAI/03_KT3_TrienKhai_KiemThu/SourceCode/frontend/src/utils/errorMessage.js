/** FastAPI detail may be a list of validation objects, never a React child. */
export function getErrorMessage(error, fallback = "Không thể thực hiện yêu cầu. Vui lòng thử lại.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => typeof item === "string" ? item : item?.msg)
      .filter((item) => typeof item === "string" && item.trim());
    if (messages.length) return [...new Set(messages)].join(". ");
  }
  if (typeof error?.message === "string" && !error.response) return error.message;
  return fallback;
}
