import { getErrorMessage } from "../../utils/errorMessage.js";

const integer = (value) => Number.isSafeInteger(value) && value >= 0;
export function validSessionBalance(data, sessionId) {
  return data?.session_id === sessionId && integer(data.gross_fee) && integer(data.online_paid)
    && integer(data.balance_due) && data.balance_due === Math.max(data.gross_fee - data.online_paid, 0);
}
const validQuote = (data, sessionId) => validSessionBalance(data, sessionId) && typeof data.id === "string"
  && ["pending", "fulfilled", "cancelled", "expired", "review"].includes(data.status)
  && Number.isFinite(Date.parse(data.expires_at));

export function createSessionFeeFlow({ sessionId, loadStatus, createQuote, createKey, isAuthorized = () => true }) {
  let generation = 0, active = false, attempt = null;
  let state = { phase: "idle", data: null, error: "" };
  const listeners = new Set();
  const update = (changes) => { state = { ...state, ...changes }; listeners.forEach((fn) => fn()); };
  async function execute(creating) {
    if (active || (!creating && attempt) || !isAuthorized()) return;
    if (creating && !attempt && (!state.data?.can_quote || !state.data.enabled)) return;
    if (creating && !attempt) attempt = Object.freeze({ request_id: createKey() });
    const turn = ++generation;
    active = true; update({ phase: creating ? "creating" : "loading", error: "" });
    try {
      const data = creating ? await createQuote(attempt) : await loadStatus();
      if (turn !== generation || !isAuthorized()) return;
      if (creating) {
        if (!validQuote(data, sessionId)) throw new Error("Đề nghị thanh toán chưa hợp lệ.");
        attempt = null;
        update({ phase: "ready", data: { ...state.data, can_quote: false, latest_quote: data,
          gross_fee: data.gross_fee, online_paid: data.online_paid, balance_due: data.balance_due, server_now: data.server_now,
          // Quote coverage is prospective. It must never be presented as money
          // already paid; a changed credit total needs a fresh status timestamp.
          paid_through: data.online_paid === state.data?.online_paid ? state.data.paid_through : null } });
      } else {
        if (!validSessionBalance(data, sessionId) || typeof data.enabled !== "boolean" || typeof data.can_quote !== "boolean"
            || (data.latest_quote && !validQuote(data.latest_quote, sessionId))) throw new Error("Số dư chưa hợp lệ.");
        update({ phase: "ready", data });
      }
    } catch (error) {
      if (turn !== generation || !isAuthorized()) return;
      const status = error?.response?.status;
      const uncertain = creating && !(status >= 400 && status < 500 && ![408, 429].includes(status));
      if (!uncertain) attempt = null;
      update({ phase: uncertain ? "uncertain" : "error", data: uncertain ? state.data : null,
        error: uncertain ? "Chưa xác nhận được đề nghị đã tạo. Thử lại chính yêu cầu đã gửi trước khi thanh toán."
          : getErrorMessage(error, "Không tải được số dư. Vui lòng thử lại.") });
    } finally {
      if (turn === generation) {
        active = false;
        if (!isAuthorized()) update({ phase: "unauthorized", data: null, error: "Phiên đăng nhập đã thay đổi. Đăng nhập lại để xem lượt gửi." });
      }
    }
  }
  return {
    subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); }, getSnapshot: () => state,
    load: () => execute(false), create: () => execute(true),
    invalidate() { generation += 1; active = false; update({ phase: "idle", data: null, error: "" }); },
  };
}
