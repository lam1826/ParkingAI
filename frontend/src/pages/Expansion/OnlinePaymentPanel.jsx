import { useEffect, useState, useSyncExternalStore } from "react";
import { Alert, Box, Button, Stack, TextField, Typography } from "@mui/material";
import { createPaymentLinkFlow, paymentDisplay } from "./onlinePaymentState";
import { dateTime, money, read, send } from "./shared";

export default function OnlinePaymentPanel({ orderId, quoteId, sessionId, onOrderRefresh }) {
  const [flow] = useState(() => {
    const token = localStorage.getItem("token"), path = quoteId ? `/session-fee-quotes/${encodeURIComponent(quoteId)}/payment-link`
      : `/me/orders/${encodeURIComponent(orderId)}/payment-link`;
    return createPaymentLinkFlow({ orderId, quoteId, sessionId, isAuthorized: () => Boolean(token) && localStorage.getItem("token") === token,
      request: (action, body) => action === "load" ? read(path) : send(path + (action === "create" ? "" : `/${action}`), body || {}) });
  });
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const [reason, setReason] = useState("");
  const [tick, setTick] = useState({ version: -1, elapsed: 0 });
  useEffect(() => {
    void flow.load();
    const refresh = () => { if (document.visibilityState === "visible") void flow.load(); };
    const timer = window.setInterval(refresh, 15000);
    document.addEventListener("visibilitychange", refresh);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", refresh); flow.invalidate(); };
  }, [flow]);
  useEffect(() => {
    const started = performance.now();
    const timer = window.setInterval(() => setTick({ version: state.version, elapsed: performance.now() - started }), 1000);
    return () => window.clearInterval(timer);
  }, [state.version]);
  const data = state.data, busy = state.phase === "loading" || state.phase === "acting";
  const display = paymentDisplay(data, tick.version === state.version ? tick.elapsed : 0);
  const changed = async (action, body) => { await flow.mutate(action, body); await onOrderRefresh?.(); };
  return <Stack spacing={2} component="section" aria-label="Thanh toán chuyển khoản">
    <Typography variant="h6" component="h4">Thanh toán chuyển khoản</Typography>
    {busy && <Typography role="status">Đang kiểm tra trạng thái thanh toán…</Typography>}
    {state.error && <Alert severity="warning">{state.error}</Alert>}
    {data && <Alert severity={data.state === "paid" ? "success" : data.state === "review" ? "warning" : "info"}>{data.message}</Alert>}
    {data && <Typography>Số tiền: <strong>{money(data.amount)}</strong> · Hạn thanh toán: {dateTime(data.expires_at)}</Typography>}
    {display.qr && <Box component="img" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(display.qr)}`}
      alt={`QR chuyển khoản ${money(data.amount)} cho ${quoteId ? "lượt gửi" : "đơn vé"} đang xem`} sx={{ width: 240, height: 240, maxWidth: "100%", objectFit: "contain", bgcolor: "common.white", alignSelf: "flex-start" }} />}
    {display.payable && <Typography color="text.secondary">Kiểm tra người nhận và số tiền trong ứng dụng ngân hàng. Chỉ chuyển một lần; hệ thống sẽ đối soát và cập nhật khoản đã trả.</Typography>}
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
      {data?.can_create && <Button variant="contained" disabled={busy} onClick={() => void changed("create")}>Tạo QR thanh toán</Button>}
      {display.url && <Button component="a" href={display.url} target="_blank" rel="noopener noreferrer" variant="contained">Mở trang thanh toán payOS</Button>}
      {data?.can_refresh && <Button variant="outlined" disabled={busy} onClick={() => void changed("refresh")}>Kiểm tra giao dịch</Button>}
      <Button variant="outlined" disabled={busy || state.phase === "unauthorized"} onClick={() => void flow.load()}>Tải lại trạng thái</Button>
      {data?.state === "paid" && <Button variant="outlined" disabled={busy} onClick={onOrderRefresh}>{quoteId ? "Cập nhật số còn thu" : "Xem vé đã cấp"}</Button>}
    </Stack>
    {data?.can_cancel && <Box component="form" onSubmit={(event) => { event.preventDefault(); void changed("cancel", { reason: reason.trim() }); }}>
      <Stack spacing={1}>
        <TextField label="Lý do hủy liên kết thanh toán" required value={reason} onChange={(event) => setReason(event.target.value)}
          disabled={busy} inputProps={{ minLength: 3, maxLength: 200 }} />
        <Typography variant="body2" color="text.secondary">Khoản chuyển đến sau khi hủy cần quản lý đối soát. Hủy liên kết không tự hoàn tiền.</Typography>
        <Button type="submit" color="error" variant="outlined" disabled={busy || reason.trim().length < 3} sx={{ alignSelf: "flex-start" }}>Xác nhận hủy liên kết</Button>
      </Stack>
    </Box>}
  </Stack>;
}
