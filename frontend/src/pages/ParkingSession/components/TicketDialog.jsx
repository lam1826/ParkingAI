import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";
import PrintIcon from "@mui/icons-material/Print";
import { useEffect, useState } from "react";
import api from "../../../services/api";
import formatDate from "../../../utils/formatDate";
import { getTicketPresentation } from "../ticketPresentation";
import "./ticketPrint.css";

export default function TicketDialog({ sessionId, siteId, onClose, onCheckOut, canManage = false }) {
  const [loadedTicket, setTicket] = useState(null);
  // A dialog can still be animating out when a new scan arrives. Never expose
  // the previous session's actions while the next ticket is loading.
  const ticket = loadedTicket?.session_id === sessionId ? loadedTicket : null;
  const presentation = getTicketPresentation(ticket);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [rotating, setRotating] = useState(false);
  useEffect(() => {
    if (!sessionId) return;
    let ignore = false;
    setTicket(null);
    setError("");
    setNotice("");
    const path = siteId ? `/api/v2/sites/${encodeURIComponent(siteId)}/sessions/${encodeURIComponent(sessionId)}/ticket`
      : `/api/v1/parking-sessions/${encodeURIComponent(sessionId)}/ticket`;
    api.get(path).then(({ data }) => {
      if (!ignore) setTicket(data);
    }).catch(() => { if (!ignore) setError("Không tải được vé. Hãy đóng và thử lại."); });
    return () => { ignore = true; };
  }, [sessionId, siteId]);

  return <Dialog open={Boolean(sessionId)} onClose={onClose} maxWidth="xs" fullWidth className="parking-ticket-dialog">
    <DialogTitle>{presentation.title}</DialogTitle>
    <DialogContent>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {!ticket && !error && <CircularProgress aria-label="Đang tải vé" />}
      {ticket && <Stack className="parking-ticket-print" data-ticket-session={ticket.session_id} spacing={1} sx={{ textAlign: "center", py: 1 }}>
        <Typography variant="h6">ParkingAI · {presentation.title}</Typography>
        <Typography variant="h4" fontWeight={700}>{ticket.license_plate}</Typography>
        <Typography>Vị trí: {ticket.slot || "Chưa xếp"}</Typography>
        <Typography>Vào: {formatDate(ticket.check_in_time, "HH:mm:ss - DD/MM/YYYY")}</Typography>
        {ticket.check_out_time && <Typography>Ra: {formatDate(ticket.check_out_time, "HH:mm:ss - DD/MM/YYYY")}</Typography>}
        <Typography fontWeight={700}>{presentation.summary}</Typography>
        <Box component="img" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(ticket.qr_svg)}`} alt="Mã QR tra cứu lượt gửi xe" sx={{ width: 240, height: 240, maxWidth: "100%", alignSelf: "center" }} />
        <Typography variant="caption" sx={{ overflowWrap: "anywhere" }}>Mã lượt: {ticket.session_id}</Typography>
        <Typography variant="caption">{presentation.instruction}</Typography>
        {ticket.payment_access_code && <Box sx={{ pt: 2, borderTop: "1px solid", borderColor: "divider" }}>
          <Typography fontWeight={700}>Mã tra phí riêng của khách</Typography>
          <Typography variant="caption" component="p" sx={{ overflowWrap: "anywhere", mt: 1, userSelect: "all" }}>{ticket.payment_access_code}</Typography>
          <Typography variant="caption" component="p" sx={{ mt: 1 }}>Giữ riêng mã này. Người có mã có thể xem phí và thanh toán lượt gửi.</Typography>
        </Box>}
      </Stack>}
      {notice && <Alert severity="info" sx={{ mt: 2 }}>{notice}</Alert>}
    </DialogContent>
    <DialogActions sx={{ flexWrap: "wrap", gap: 1, p: 2 }}>
      <Button onClick={onClose}>Đóng</Button>
      {ticket?.payment_access_code && <Button onClick={async () => {
        try { await navigator.clipboard.writeText(ticket.payment_access_code); setNotice("Đã sao chép mã tra phí. Chỉ gửi cho khách giữ vé."); }
        catch { setNotice("Chưa sao chép được. Bạn có thể chọn mã trên vé rồi sao chép."); }
      }}>Sao chép mã tra phí</Button>}
      {ticket && canManage && siteId && presentation.canCheckOut && <Button disabled={rotating} onClick={async () => {
        setRotating(true); setError("");
        try {
          await api.post(`/api/v2/sites/${encodeURIComponent(siteId)}/sessions/${encodeURIComponent(sessionId)}/ticket-payment-code/rotate`);
          const { data } = await api.get(`/api/v2/sites/${encodeURIComponent(siteId)}/sessions/${encodeURIComponent(sessionId)}/ticket`);
          setTicket(data); setNotice("Đã cấp mã mới và thu hồi quyền truy cập từ mã cũ. In lại vé để giao cho khách.");
        } catch { setError("Chưa xác nhận được mã mới. Đóng rồi tải lại vé để kiểm tra trước khi gửi lại."); }
        finally { setRotating(false); }
      }}>Đổi mã tra phí</Button>}
      {presentation.canCheckOut && onCheckOut && <Button color="error" onClick={() => onCheckOut(sessionId)}>Xem phí và cho xe ra</Button>}
      <Button variant="contained" startIcon={<PrintIcon />} disabled={!ticket} onClick={() => window.print()}>In vé</Button>
    </DialogActions>
  </Dialog>;
}
