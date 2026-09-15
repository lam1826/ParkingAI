import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";
import BillingBasisDetails from "../ParkingSession/components/BillingBasisDetails";
import PrepaidDetails from "../ParkingSession/components/PrepaidDetails";
import { getSessionStatusPresentation } from "../ParkingSession/sessionPresentation";
import { dateOnly, dateTime, money } from "./shared";
import SessionFeePayment from "./SessionFeePayment";

// Customer history and payment APIs require the existing session access grant.
export default function PortalSessionDetails({ session, onClose, onChanged }) {
  return <Dialog open fullWidth maxWidth="sm" onClose={onClose} aria-labelledby="portal-session-title">
    <DialogTitle id="portal-session-title">Lượt gửi — {session.license_plate}</DialogTitle>
    <DialogContent dividers><Stack spacing={2}>
      <Typography>{getSessionStatusPresentation(session.status).label}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>Mã lượt: {session.id || session.session_id}</Typography>
      <Typography>Giờ vào: {dateTime(session.check_in_time)}</Typography>
      {session.check_out_time && <Typography>Giờ ra: {dateTime(session.check_out_time)}</Typography>}
      {session.parking_fee != null && <Typography fontWeight={700}>{session.prepaid ? "Phí phát sinh khi ra" : "Phí khi ra"}: {money(session.parking_fee)}</Typography>}
      {session.status !== "active" && session.online_paid > 0 && <>
        <Typography>Đã trả online: {money(session.online_paid)}</Typography>
        <Typography>Thu thêm khi ra: {money(session.balance_due)}</Typography>
      </>}
      {session.monthly_coverage_end && <Typography>Quyền vé tháng của lượt đến hết {dateOnly(session.monthly_coverage_end)}.</Typography>}
      <PrepaidDetails prepaid={session.prepaid} />
      <BillingBasisDetails basis={session.billing_basis} active={session.status === "active"} />
      {session.status === "active" && <SessionFeePayment key={session.id} sessionId={session.id} onChanged={onChanged} />}
    </Stack></DialogContent>
    <DialogActions><Button onClick={onClose}>Đóng</Button></DialogActions>
  </Dialog>;
}
