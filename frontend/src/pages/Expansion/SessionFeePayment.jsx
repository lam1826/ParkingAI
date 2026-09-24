import { useEffect, useState, useSyncExternalStore } from "react";
import { Alert, Button, Stack, Typography } from "@mui/material";
import OnlinePaymentPanel from "./OnlinePaymentPanel";
import { createSessionFeeFlow } from "./sessionFeeState";
import { dateTime, money, read, requestKey, send } from "./shared";

export default function SessionFeePayment({ sessionId, siteId, onChanged }) {
  const [flow] = useState(() => {
    const token = localStorage.getItem("token");
    const path = siteId ? `/sites/${encodeURIComponent(siteId)}/sessions/${encodeURIComponent(sessionId)}`
      : `/me/sessions/${encodeURIComponent(sessionId)}`;
    return createSessionFeeFlow({ sessionId, isAuthorized: () => Boolean(token) && localStorage.getItem("token") === token,
      loadStatus: () => read(`${path}/payment-status`), createQuote: (body) => send(`${path}/payment-quote`, body), createKey: requestKey });
  });
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  useEffect(() => { void flow.load(); return () => flow.invalidate(); }, [flow]);
  const busy = ["loading", "creating"].includes(state.phase), uncertain = state.phase === "uncertain";
  const data = state.data, quote = data?.latest_quote;
  const closed = ["completed", "cancelled"].includes(data?.session_status);
  const refresh = async () => { await flow.load(); await onChanged?.(); };
  return <Stack spacing={2} component="section" aria-label="Thanh toán phí lượt gửi">
    <Typography variant="h6" component="h3">Thanh toán phí lượt gửi</Typography>
    <Typography color="text.secondary">{closed ? "Lượt đã kết thúc. Kiểm tra các khoản đã thu và chứng từ trong lịch sử." : "Thanh toán trước khi ra. Lượt gửi chỉ kết thúc khi xe được ghi nhận ra tại cổng; thời gian gửi thêm có thể phát sinh phí."}</Typography>
    {busy && <Typography role="status">Đang kiểm tra phí và khoản đã trả…</Typography>}
    {state.error && <Alert severity={uncertain ? "warning" : "error"}>{state.error}</Alert>}
    {data && <>
      <Typography>Tổng phí hiện tại: <strong>{money(data.gross_fee)}</strong></Typography>
      <Typography>Đã trả online: <strong>{money(data.online_paid)}</strong></Typography>
      <Typography variant="h5" component="p">{data.session_status === "completed" ? "Đã thu khi ra" : "Còn thanh toán"}: {money(data.balance_due)}</Typography>
      {data.paid_through && <Typography>Đã trả đến: {dateTime(data.paid_through)}</Typography>}
      {data.message && <Alert severity={data.enabled ? "info" : "warning"}>{data.message}</Alert>}
    </>}
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
      <Button variant="outlined" disabled={busy || uncertain || state.phase === "unauthorized"} onClick={() => void refresh()}>Cập nhật số dư</Button>
      {!closed && (data?.can_quote && data.enabled || uncertain) && <Button variant="contained" disabled={busy} onClick={() => void flow.create()}>
        {uncertain ? "Thử lại yêu cầu đã gửi" : "Lập đề nghị thanh toán QR"}
      </Button>}
    </Stack>
    {quote && !closed && state.phase === "ready" && <>
      <Typography variant="body2" color="text.secondary">Đề nghị {quote.id.slice(0, 8)} · Số tiền {money(quote.balance_due)} · Hết hạn {dateTime(quote.expires_at)}</Typography>
      <OnlinePaymentPanel key={quote.id} quoteId={quote.id} sessionId={sessionId} onOrderRefresh={refresh} />
    </>}
  </Stack>;
}
