import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import api from "../../../services/api";
import { formatBusinessDateOnly, formatBusinessTimestamp } from "../../../utils/formatDate";
import { formatParkingFee } from "../../../utils/formatCurrency";
import { useRemote } from "../../Expansion/shared";
import BillingBasisDetails from "./BillingBasisDetails";
import PrepaidDetails from "./PrepaidDetails";
import { getSessionStatusPresentation } from "../sessionPresentation";
import { createSessionExceptionFlow, validCorrectionPlate, validExceptionReason } from "../sessionExceptionFlow";

const actionLabels = { cancelled: "Hủy lượt vào nhầm", lost_ticket: "Xác nhận mất vé", plate_corrected: "Sửa biển số" };
const eligibilityKeys = { cancel: "cancel", "lost-ticket": "lost_ticket", "correct-plate": "correct_plate" };
const actionInstructions = {
  cancel: "Hủy lượt vào nhầm sẽ giữ lịch sử và giải phóng vị trí đỗ. Kiểm tra đúng xe trước khi xác nhận.",
  "lost-ticket": "Ghi nhận việc quản lý đã kiểm tra phương tiện và xác minh vé thất lạc. Sau đó tiếp tục xem phí và cho xe ra; không thêm phụ phí mất vé.",
  "correct-plate": "Hệ thống hủy vé sai và tạo vé thay thế, giữ nguyên giờ vào, vị trí và giá đã ghi nhận. Kiểm tra biển số mới rồi in vé thay thế cho khách.",
};
const successMessages = {
  cancelled: "Đã hủy lượt và trả chỗ trống; lịch sử được giữ lại.",
  lost_ticket: "Đã lưu xác nhận mất vé. Tiếp tục xem phí trước khi cho xe ra.",
  plate_corrected: "Đã sửa biển số bằng lượt thay thế. Vé cũ đã hủy; hãy in vé mới cho khách.",
};

export default function SessionDetailsDialog({ session, siteId, canManage = false, onClose, onChanged, onCheckout, onBusy, onTicket }) {
  const prefix = siteId ? `/api/v2/sites/${encodeURIComponent(siteId)}/sessions/${encodeURIComponent(session.id)}`
    : `/api/v1/parking-sessions/${encodeURIComponent(session.id)}`;
  const load = useCallback(() => api.get(`${prefix}/exceptions`).then((response) => response.data), [prefix]);
  const history = useRemote(load);
  const [flow] = useState(() => {
    const token = localStorage.getItem("token");
    return createSessionExceptionFlow({ sessionId: session.id,
      authorization: canManage,
      isAuthorized: () => Boolean(token) && localStorage.getItem("token") === token,
      send: async (action, body) => (await api.post(`${prefix}/${action}`, body)).data,
      onCompleted: (result) => { void history.reload(); onChanged?.(result); },
      onRejected: () => { void history.reload(); },
    });
  });
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const pending = state.phase === "submitting";
  const uncertain = state.phase === "uncertain";
  useEffect(() => { flow.setAuthorization(canManage); }, [flow, canManage]);
  useEffect(() => {
    flow.start();
    const protect = (event) => { if (!flow.canDismiss()) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", protect);
    return () => { flow.stop(); window.removeEventListener("beforeunload", protect); };
  }, [flow]);
  useEffect(() => { onBusy?.(pending || uncertain); return () => onBusy?.(false); }, [pending, uncertain, onBusy]);

  const dismiss = () => { if (flow.canDismiss()) onClose(); };
  const status = state.result?.status || history.data?.status || session.status;
  const plate = session.license_plate || session.vehicle?.license_plate || "Chưa có biển số";
  const eligibility = history.data?.eligibility || {};
  const selectedEligibility = eligibility[eligibilityKeys[state.action]];
  const maySubmit = uncertain || (state.phase === "editing" && selectedEligibility?.allowed && validExceptionReason(state.reason)
    && (state.action !== "correct-plate" || validCorrectionPlate(state.licensePlate)) && !history.loading && !history.error);
  const fee = session.parking_fee ?? session.parkingFee;
  return <Dialog open maxWidth="md" fullWidth onClose={dismiss} aria-labelledby="session-details-title">
    <DialogTitle id="session-details-title">Chi tiết lượt gửi — {plate}</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2.5}>
        <Box>
          <Typography fontWeight={700}>{getSessionStatusPresentation(status).label}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>Mã lượt: {session.id}</Typography>
          <Typography>Vào: {formatBusinessTimestamp(session.check_in_time || session.checkInTime)}</Typography>
          {(session.check_out_time || session.checkOutTime) && <Typography>Ra: {formatBusinessTimestamp(session.check_out_time || session.checkOutTime)}</Typography>}
          {status === "completed" && <Typography>{session.prepaid ? "Phí phát sinh khi ra" : "Phí đã ghi nhận"}: {formatParkingFee(fee)} VND</Typography>}
          {session.monthly_coverage_end && <Typography>Quyền vé tháng của lượt: đến hết {formatBusinessDateOnly(session.monthly_coverage_end)}.</Typography>}
        </Box>
        <PrepaidDetails prepaid={session.prepaid} />
        <BillingBasisDetails basis={session.billing_basis} active={status === "active"} />
        {prefix && <>
          <Typography component="h3" variant="subtitle1" fontWeight={700}>Lịch sử xử lý</Typography>
          {history.loading && <Stack direction="row" spacing={1} role="status"><CircularProgress size={18} /><Typography>Đang tải lịch sử…</Typography></Stack>}
          {history.error && <Alert severity="error" action={<Button disabled={pending || uncertain} onClick={history.reload}>Thử lại</Button>}>{history.error}</Alert>}
          {!history.loading && !history.error && !history.data?.events?.length && <Typography color="text.secondary">Chưa có xử lý ngoại lệ cho lượt này.</Typography>}
          {history.data?.events?.map((event) => <Box key={event.id}>
            <Typography fontWeight={700}>{actionLabels[event.action] || "Điều chỉnh lượt gửi"}</Typography>
            <Typography variant="body2" color="text.secondary">{formatBusinessTimestamp(event.created_at)} · {event.actor_username || "Nhân sự bãi"}</Typography>
            <Typography sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>Lý do: {event.reason}</Typography>
            {event.action === "plate_corrected" && <Stack spacing={0.5} sx={{ mt: 0.5 }}>
              <Typography sx={{ overflowWrap: "anywhere" }}>Biển số: {event.before_state?.license_plate || "—"} → {event.after_state?.license_plate || "—"}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>Lượt cũ: {event.before_state?.session_id || "—"} → lượt thay thế: {event.replacement_session_id || "—"}</Typography>
              {event.replacement_session_id && onTicket && <Button variant="text" sx={{ alignSelf: "flex-start" }} disabled={pending || uncertain} onClick={() => { onClose(); onTicket(event.replacement_session_id); }}>Xem / in vé thay thế</Button>}
            </Stack>}
          </Box>)}
          {canManage && <Stack spacing={1.5}>
            <Typography component="h3" variant="subtitle1" fontWeight={700}>Xử lý của quản lý</Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
              <Button variant="outlined" color="error" disabled={pending || uncertain || history.loading || !!history.error || !eligibility.cancel?.allowed} onClick={() => flow.choose("cancel")}>Hủy lượt vào nhầm</Button>
              <Button variant="outlined" disabled={pending || uncertain || history.loading || !!history.error || !eligibility.lost_ticket?.allowed} onClick={() => flow.choose("lost-ticket")}>Xác nhận mất vé</Button>
              <Button variant="outlined" disabled={pending || uncertain || history.loading || !!history.error || !eligibility.correct_plate?.allowed} onClick={() => flow.choose("correct-plate")}>Sửa biển số</Button>
            </Stack>
            {!eligibility.cancel?.allowed && eligibility.cancel?.reason && <Typography variant="body2" color="text.secondary">Hủy lượt: {eligibility.cancel.reason}</Typography>}
            {!eligibility.lost_ticket?.allowed && eligibility.lost_ticket?.reason && <Typography variant="body2" color="text.secondary">Mất vé: {eligibility.lost_ticket.reason}</Typography>}
            {!eligibility.correct_plate?.allowed && eligibility.correct_plate?.reason && <Typography variant="body2" color="text.secondary">Sửa biển số: {eligibility.correct_plate.reason}</Typography>}
            {state.action && state.phase !== "completed" && <>
              <Alert severity={state.action === "cancel" ? "warning" : "info"}>{actionInstructions[state.action]}</Alert>
              {state.action === "correct-plate" && <TextField label="Biển số đúng" value={state.licensePlate} disabled={pending || uncertain}
                onChange={(event) => flow.setLicensePlate(event.target.value)} required slotProps={{ htmlInput: { maxLength: 15 } }} helperText="Nhập từ 4 đến 15 ký tự. Giờ vào và giá đã ghi nhận được giữ nguyên." />}
              <TextField label="Lý do xử lý" multiline minRows={2} value={state.reason} disabled={pending || uncertain} onChange={(event) => flow.setReason(event.target.value)}
                required slotProps={{ htmlInput: { maxLength: 500 } }} helperText="Nhập lý do từ 3 đến 500 ký tự; nội dung được lưu vào lịch sử." />
            </>}
          </Stack>}
        </>}
        {state.error && <Alert severity={uncertain ? "warning" : "error"}>{state.error}</Alert>}
        {state.phase === "completed" && <Alert severity="success">{state.result.event.action === "lost_ticket" && state.result.next_action === "none"
          ? "Xác nhận mất vé đã được lưu; lượt này không còn đang gửi." : successMessages[state.result.event.action]}</Alert>}
      </Stack>
    </DialogContent>
    <DialogActions sx={{ p: 2, gap: 1, flexWrap: "wrap" }}>
      <Button disabled={!flow.canDismiss()} onClick={dismiss}>Đóng</Button>
      {canManage && state.action && state.phase !== "completed" && <Button variant="contained" color={state.action === "cancel" ? "error" : "primary"}
        disabled={pending || !maySubmit} onClick={() => void flow.submit()} startIcon={pending ? <CircularProgress size={18} color="inherit" /> : undefined}>
        {uncertain ? "Thử lại yêu cầu đã gửi" : pending ? "Đang xử lý…" : "Xác nhận và lưu lý do"}
      </Button>}
      {status === "active" && onCheckout && flow.canDismiss() && <Button variant="contained" onClick={() => { onClose(); onCheckout(session.id); }}>Xem phí và cho xe ra</Button>}
      {state.result?.replacement_session_id && onTicket && flow.canDismiss() && <Button variant="contained" onClick={() => { onClose(); onTicket(state.result.replacement_session_id); }}>Xem / in vé thay thế</Button>}
    </DialogActions>
  </Dialog>;
}
