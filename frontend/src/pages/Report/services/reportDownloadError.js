import { joinMessages } from "../../../utils/errorMessage.js";

function formatValidationDetail(detail) {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!Array.isArray(detail)) return "";

  // The server's message already names the field in Vietnamese ("Ngày báo cáo:
  // ngày không hợp lệ."), so the raw location (anchor_date) is not repeated (B-05).
  return joinMessages(detail
    .map((item) => (item && typeof item === "object" && typeof item.msg === "string" ? item.msg : ""))
    .filter(Boolean), "; ");
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
