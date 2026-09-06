import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";
import PrintIcon from "@mui/icons-material/Print";
import { useEffect, useState } from "react";
import api from "../../../services/api";
import formatDate from "../../../utils/formatDate";
import { getTicketPresentation } from "../ticketPresentation";
import "./ticketPrint.css";

export default function TicketDialog({ sessionId, onClose, onCheckOut }) {
  const [loadedTicket, setTicket] = useState(null);
  // A dialog can still be animating out when a new scan arrives. Never expose
  // the previous session's actions while the next ticket is loading.
  const ticket = loadedTicket?.session_id === sessionId ? loadedTicket : null;
  const presentation = getTicketPresentation(ticket);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!sessionId) return;
    let ignore = false;
    setTicket(null);
    setError("");
    api.get(`/api/v1/parking-sessions/${encodeURIComponent(sessionId)}/ticket`).then(({ data }) => {
      if (!ignore) setTicket(data);
    }).catch(() => { if (!ignore) setError("Không tải được vé. Hãy đóng và thử lại."); });
    return () => { ignore = true; };
  }, [sessionId]);

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
      </Stack>}
    </DialogContent>
    <DialogActions sx={{ flexWrap: "wrap", gap: 1, p: 2 }}>
      <Button onClick={onClose}>Đóng</Button>
      {presentation.canCheckOut && onCheckOut && <Button color="error" onClick={() => onCheckOut(sessionId)}>Xem phí và cho xe ra</Button>}
      <Button variant="contained" startIcon={<PrintIcon />} disabled={!ticket} onClick={() => window.print()}>In vé</Button>
    </DialogActions>
  </Dialog>;
}
