import { requestId as newRequestId } from "../../utils/requestId.js";
import { getErrorMessage } from "../../utils/errorMessage.js";

const EVENT_ACTIONS = { cancel: "cancelled", "lost-ticket": "lost_ticket", "correct-plate": "plate_corrected" };
const NEXT_ACTIONS = { cancel: "none", "lost-ticket": "checkout", "correct-plate": "print_replacement_ticket" };

function matchesResult(action, result) {
  if (action === "lost-ticket") {
    return (result.status === "active" && result.next_action === "checkout")
      || (["completed", "cancelled", "checking_out"].includes(result.status) && result.next_action === "none");
  }
  return result.status === "cancelled" && result.next_action === NEXT_ACTIONS[action];
}

export function validCorrectionPlate(plate) {
  return typeof plate === "string" && plate.trim().length >= 4 && plate.trim().length <= 15;
}

export function validExceptionReason(reason) {
  return typeof reason === "string" && reason.trim().length >= 3 && reason.trim().length <= 500;
}

export function createSessionExceptionFlow({ sessionId, send, onCompleted, onRejected,
  requestId = newRequestId, isAuthorized = () => true, authorization = true }) {
  let active = false;
  let authorized = authorization;
  let generation = 0;
  let attempt = null;
  let state = { phase: "idle", action: null, reason: "", licensePlate: "", error: "", result: null };
  const listeners = new Set();
  const update = (patch) => { state = { ...state, ...patch }; listeners.forEach((listener) => listener()); };
  const current = (request) => active && authorized && generation === request && isAuthorized();
  const editable = () => active && ["idle", "editing", "completed"].includes(state.phase);

  async function submit() {
    if (!active || !authorized || !isAuthorized() || !["editing", "uncertain"].includes(state.phase)) return;
    if (!attempt) {
      if (!EVENT_ACTIONS[state.action] || !validExceptionReason(state.reason)) return;
      if (state.action === "correct-plate" && !validCorrectionPlate(state.licensePlate)) return;
      attempt = Object.freeze({ action: state.action,
        body: Object.freeze({ reason: state.reason.trim(), request_id: requestId(),
          ...(state.action === "correct-plate" ? { license_plate: state.licensePlate.trim().toUpperCase() } : {}) }) });
    }
    const request = ++generation;
    update({ phase: "submitting", error: "" });
    let result;
    try {
      result = await send(attempt.action, attempt.body);
      if (!current(request)) return;
      if (result?.session_id !== sessionId || result?.event?.action !== EVENT_ACTIONS[attempt.action]
          || !matchesResult(attempt.action, result)
          || (attempt.action === "correct-plate" && (typeof result.replacement_session_id !== "string"
            || !result.replacement_session_id || result.replacement_session_id === sessionId))) throw new Error("Unknown result");
    } catch (error) {
      if (!current(request)) return;
      const status = error?.response?.status;
      if (status >= 400 && status < 500 && ![408, 429].includes(status)) {
        attempt = null;
        update({ phase: "editing", error: getErrorMessage(error, "Lượt gửi đã thay đổi hoặc bạn không có quyền xử lý. Hãy kiểm tra lại.") });
        onRejected?.();
      } else {
        update({ phase: "uncertain", error: "Chưa xác nhận được kết quả. Giữ nguyên nội dung và thử lại yêu cầu đã gửi để kiểm tra; không tạo yêu cầu khác." });
      }
      return;
    }
    attempt = null;
    update({ phase: "completed", result });
    onCompleted?.(result);
    return result;
  }

  return {
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot: () => state,
    start() { active = true; },
    stop() { active = false; generation += 1; },
    setAuthorization(value) { authorized = value === true; },
    canDismiss: () => !["submitting", "uncertain"].includes(state.phase),
    choose(action) {
      if (editable() && EVENT_ACTIONS[action]) {
        attempt = null;
        update({ phase: "editing", action, reason: "", licensePlate: "", error: "", result: null });
      }
    },
    setReason(reason) { if (editable()) update({ reason }); },
    setLicensePlate(licensePlate) { if (editable()) update({ licensePlate }); },
    submit,
  };
}
