import { getErrorMessage } from "../../utils/errorMessage.js";

export const paymentModeLabel = (mode) => ({ demo: "DEMO — không chuyển tiền", manual: "Thu tại quầy", payos: "Chuyển khoản QR qua payOS" })[mode] || "Chưa xác định";
export function paymentModes(plan, demoEnabled) {
  const modes = Array.isArray(plan?.payment_modes) ? plan.payment_modes : ["manual", ...(demoEnabled ? ["demo"] : [])];
  return ["demo", "manual", "payos"].filter((mode) => modes.includes(mode) && (mode !== "demo" || demoEnabled));
}
export function checkoutLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "pay.payos.vn" && !url.username && !url.password && !url.port ? url.href : null;
  } catch { return null; }
}
export function paymentDisplay(data, elapsedMilliseconds = 0) {
  const end = Date.parse(data?.expires_at), server = Date.parse(data?.server_now);
  const validTime = Number.isFinite(end) && Number.isFinite(server) && server + Math.max(0, elapsedMilliseconds) < end;
  const url = checkoutLink(data?.checkout_url);
  const qr = typeof data?.qr_svg === "string" && data.qr_svg.startsWith("<") ? data.qr_svg : null;
  const payable = data?.enabled === true && data.state === "ready" && validTime && Boolean(url || qr);
  return { payable, url: payable ? url : null, qr: payable ? qr : null };
}

// Network uncertainty clears payment instructions. Only a fresh server response
// can restore them; a browser return URL never changes the financial outcome.
export function createPaymentLinkFlow({ orderId, quoteId, sessionId, request, isAuthorized = () => true }) {
  let state = { phase: "idle", data: null, error: "", version: 0 };
  let generation = 0, active = false;
  const listeners = new Set();
  const update = (changes) => { state = { ...state, ...changes }; listeners.forEach((fn) => fn()); };
  async function execute(action, body) {
    if (active) return;
    if (!isAuthorized()) { update({ data: null, phase: "unauthorized", error: "Phiên đăng nhập đã thay đổi. Đăng nhập lại để kiểm tra đơn." }); return; }
    const turn = ++generation;
    active = true;
    update({ phase: action === "load" ? "loading" : "acting", error: "", data: null });
    try {
      const data = await request(action, body);
      if (turn !== generation || !isAuthorized()) return;
      const matches = quoteId ? data?.quote_id === quoteId && data.session_id === sessionId && data.order_id == null
        : data?.order_id === orderId && data.quote_id == null;
      if (!matches || typeof data.enabled !== "boolean" || !Number.isSafeInteger(data.amount) || data.amount <= 0 || data.currency !== "VND" || !["not_created", "creating", "unknown", "ready", "paid", "cancelled", "expired", "review"].includes(data.state)) {
        throw new Error("Chưa nhận được trạng thái thanh toán hợp lệ.");
      }
      update({ phase: "ready", data, error: "", version: state.version + 1 });
    } catch (error) {
      if (turn === generation && isAuthorized()) update({ phase: "uncertain", data: null,
        error: getErrorMessage(error, "Chưa xác nhận được kết quả. Tải lại trạng thái của đơn này trước khi thanh toán.") });
    } finally {
      if (turn === generation) active = false;
      if (turn === generation && !isAuthorized()) update({ phase: "unauthorized", data: null,
        error: "Phiên đăng nhập đã thay đổi. Đăng nhập lại để kiểm tra đơn." });
    }
  }
  return {
    subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); },
    getSnapshot: () => state,
    load: () => execute("load"),
    mutate(action, body) {
      const permission = { create: "can_create", refresh: "can_refresh", cancel: "can_cancel" }[action];
      if (!permission || state.data?.[permission] !== true || !state.data.enabled) return Promise.resolve();
      return execute(action, body);
    },
    invalidate() { generation += 1; active = false; update({ phase: "idle", data: null, error: "" }); },
  };
}
