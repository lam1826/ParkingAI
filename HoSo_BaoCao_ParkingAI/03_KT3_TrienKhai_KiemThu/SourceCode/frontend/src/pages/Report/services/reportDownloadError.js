function formatValidationDetail(detail) {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!Array.isArray(detail)) return "";

  return detail
    .map((item) => {
      if (!item || typeof item !== "object") return "";
      const location = Array.isArray(item.loc)
        ? item.loc.slice(1).join(".")
        : "";
      const message = typeof item.msg === "string" ? item.msg : "";
      if (!message) return "";
      return location ? `${location}: ${message}` : message;
    })
    .filter(Boolean)
    .join("; ");
}

function detailFromPayload(payload) {
  if (!payload || typeof payload !== "object") return "";
  return formatValidationDetail(payload.detail);
}

/**
 * Axios giữ response lỗi ở dạng Blob khi request download dùng responseType
 * "blob". Giải mã JSON của FastAPI để UI không đánh mất detail nghiệp vụ.
 */
export async function extractReportDownloadErrorMessage(error, fallback) {
  const payload = error?.response?.data;
  const directDetail = detailFromPayload(payload);
  if (directDetail) return directDetail;

  if (payload && typeof payload.text === "function") {
    try {
      const parsed = JSON.parse(await payload.text());
      return detailFromPayload(parsed) || fallback;
    } catch {
      return fallback;
    }
  }

  return fallback;
}
