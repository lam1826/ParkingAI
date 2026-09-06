import { getErrorMessage } from "../../utils/errorMessage.js";

const REQUOTE_CODES = new Set(["checkout_quote_expired", "checkout_quote_changed"]);
const RECONFIRM_NOTICE = "Phí cần được cập nhật. Kiểm tra số tiền mới và xác nhận lại trước khi cho xe ra.";
const UNKNOWN_OUTCOME = "Chưa xác nhận được kết quả xe ra. Giữ nguyên lượt này và thử lại để kiểm tra yêu cầu đã gửi; không thu tiền lần nữa.";

function errorMessage(error, fallback) {
  const message = error?.response?.data?.detail?.message;
  return typeof message === "string" && message.trim() ? message : getErrorMessage(error, fallback);
}

function validQuote(quote, sessionId) {
  return quote?.session_id === sessionId && typeof quote.quote_token === "string" && quote.quote_token.length > 0
    && typeof quote.license_plate === "string" && quote.license_plate.length > 0
    && Number.isSafeInteger(quote.parking_fee) && quote.parking_fee >= 0
    && Number.isSafeInteger(quote.duration_minutes) && quote.duration_minutes >= 0
    && Number.isFinite(Date.parse(quote.check_in_time))
    && Number.isFinite(Date.parse(quote.quoted_at)) && Number.isFinite(Date.parse(quote.expires_at))
    && Date.parse(quote.expires_at) > Date.parse(quote.quoted_at);
}

/** Own the quote/confirmation lifetime independently of rendering. An uncertain
 * write retains the same immutable body: expiry must never turn a retry into a
 * new payment decision. stop() invalidates work on session/auth boundary changes.
 */
export function createCheckoutFlow({ sessionId, loadQuote, confirmCheckout, onCompleted,
  isAuthorized = () => true, now = () => performance.now() }) {
  let active = false;
  let generation = 0;
  let submittedBody = null;
  let state = { phase: "idle", quote: null, paymentMethod: "", paymentConfirmed: false,
    error: "", notice: "", expiresAt: 0, expired: false };
  const listeners = new Set();
  const current = (request = generation) => active && request === generation && isAuthorized();
  const update = (patch) => { state = { ...state, ...patch }; listeners.forEach(listener => listener()); };

  async function refresh(notice = "") {
    if (!current() || submittedBody || state.phase === "loading" || state.phase === "submitting") return;
    const request = ++generation;
    const requestedAt = now();
    update({ phase: "loading", quote: null, error: "", notice, paymentMethod: "", paymentConfirmed: false, expired: false });
    try {
      const quote = await loadQuote(sessionId);
      if (!current(request)) return;
      if (!validQuote(quote, sessionId)) throw new Error("Thông tin phí không hợp lệ. Hãy tải lại phí trước khi thao tác.");
      // Relative server TTL avoids depending on the workstation's clock. Count
      // from request start conservatively so network delay cannot extend a quote.
      const expiresAt = requestedAt + Date.parse(quote.expires_at) - Date.parse(quote.quoted_at);
      update({ phase: "ready", quote, expiresAt, expired: now() >= expiresAt });
    } catch (error) {
      if (current(request)) update({ phase: "error", error: errorMessage(error, "Không tải được phí. Hãy kiểm tra kết nối và tải lại.") });
    }
  }

  async function submit() {
    if (!current() || !["ready", "uncertain"].includes(state.phase)) return;
    if (!submittedBody) {
      if (now() >= state.expiresAt) { await refresh(RECONFIRM_NOTICE); return; }
      const free = state.quote.parking_fee === 0;
      if (!free && (!state.paymentConfirmed || !["cash", "transfer"].includes(state.paymentMethod))) return;
      submittedBody = Object.freeze({ quote_token: state.quote.quote_token,
        payment_confirmed: true, payment_method: free ? null : state.paymentMethod });
    }
    const request = ++generation;
    update({ phase: "submitting", error: "", notice: "" });
    let result;
    try {
      result = await confirmCheckout(sessionId, submittedBody);
      if (!current(request)) return;
      if (result?.id !== sessionId || result.status !== "completed") throw new Error("Chưa nhận được kết quả xe ra hợp lệ.");
    } catch (error) {
      if (!current(request)) return;
      const status = error?.response?.status;
      const code = error?.response?.data?.detail?.code;
      if (status === 409 && REQUOTE_CODES.has(code)) {
        submittedBody = null;
        update({ phase: "ready" });
        await refresh(RECONFIRM_NOTICE);
      } else if (status >= 400 && status < 500 && ![408, 429].includes(status)) {
        // A definitive rejection is safe to dismiss. A different operator's
        // completed checkout or a permission failure must not trigger a new PUT.
        submittedBody = null;
        update({ phase: "error", quote: null, paymentMethod: "", paymentConfirmed: false,
          error: errorMessage(error, "Không thể xác nhận xe ra. Hãy kiểm tra lại lượt gửi xe.") });
      } else {
        update({ phase: "uncertain", error: UNKNOWN_OUTCOME });
      }
      return;
    }
    submittedBody = null;
    update({ phase: "completed", result });
    onCompleted?.(result);
    return result;
  }

  return {
    getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    start() { active = true; if (state.phase === "loading") state = { ...state, phase: "idle" }; return refresh(); },
    stop() { active = false; generation += 1; },
    refresh,
    submit,
    canDismiss: () => !["submitting", "uncertain"].includes(state.phase),
    tick() { if (current() && state.phase === "ready" && !state.expired && now() >= state.expiresAt) update({ expired: true }); },
    setPaymentMethod(value) {
      if (current() && state.phase === "ready" && !submittedBody && ["", "cash", "transfer"].includes(value)) {
        update({ paymentMethod: value, paymentConfirmed: false });
      }
    },
    setPaymentConfirmed(value) {
      if (current() && state.phase === "ready" && !submittedBody) update({ paymentConfirmed: value === true });
    },
  };
}
