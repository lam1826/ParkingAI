import { getErrorMessage } from "../../utils/errorMessage.js";

export function createPortalOrderFlow({ createOrder, createKey, isAuthorized = () => true, onCreated }) {
  let state = { phase: "editing", error: "", order: null, attempt: null, key: createKey() };
  const listeners = new Set();
  const update = (changes) => { state = { ...state, ...changes }; listeners.forEach((listener) => listener()); };
  const unresolved = () => ["submitting", "uncertain"].includes(state.phase);
  return {
    getSnapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    canReset: () => !unresolved(),
    reset() { if (!unresolved()) update({ phase: "editing", error: "", order: null, attempt: null, key: createKey() }); },
    async submit(buildBody) {
      if (state.phase === "submitting" || state.phase === "completed") return;
      if (!isAuthorized()) { update({ error: "Phiên đăng nhập đã thay đổi. Đăng nhập và kiểm tra đơn trước khi tiếp tục." }); return; }
      let body = state.attempt;
      if (!body) {
        try { body = Object.freeze({ ...buildBody(state.key) }); }
        catch (error) { update({ error: error.message }); return; }
      }
      update({ phase: "submitting", error: "", attempt: body });
      let result;
      try {
        result = await createOrder(body);
        if (!result?.id || typeof result.status !== "string") throw new Error("Máy chủ trả về dữ liệu đơn chưa đầy đủ.");
      } catch (error) {
        const status = error?.response?.status;
        const definitive = status >= 400 && status < 500 && ![408, 429].includes(status);
        update({ phase: definitive ? "editing" : "uncertain", attempt: definitive ? null : body,
          error: definitive ? getErrorMessage(error, "Chưa tạo được đơn. Kiểm tra lựa chọn rồi thử lại.")
            : "Chưa xác nhận được đơn đã tạo. Thử lại chính yêu cầu đã gửi; nội dung và mã yêu cầu được giữ nguyên." });
        return;
      }
      if (!isAuthorized()) {
        update({ phase: "uncertain", error: "Phiên đăng nhập đã thay đổi sau khi gửi. Đăng nhập đúng tài khoản để kiểm tra đơn; chưa tạo yêu cầu khác." });
        return;
      }
      update({ phase: "completed", error: "", order: result, attempt: null });
      // Refresh failures must not turn a successful creation into another order.
      onCreated?.(result);
    },
  };
}
