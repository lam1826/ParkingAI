import { useEffect, useState } from "react";
import { Alert, Box, Button, Stack, TextField, Typography } from "@mui/material";
import { dateOnly, dateTime, money, Section, StateChip } from "./shared";
import { entitlementLabel, holdRemaining, orderStatusLabel, ownerCan, productDuration, productKind, productLabel } from "./portalOffers";
import OnlinePaymentPanel from "./OnlinePaymentPanel";
import { paymentModeLabel } from "./onlinePaymentState";

export default function PortalOrderDetails({ order, busy, onRefresh, onSimulate, onCancel, onRefund }) {
  const [reason, setReason] = useState("");
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (order.status !== "pending" || !order.hold_expires_at) return;
    const started = performance.now();
    const timer = window.setInterval(() => setElapsed(performance.now() - started), 1000);
    return () => window.clearInterval(timer);
  }, [order.status, order.hold_expires_at]);
  const timed = productKind(order) !== "monthly";
  const remaining = holdRemaining(order, elapsed);
  const needsRefresh = order.status === "pending" && remaining === 0;
  const demo = order.payment_mode === "demo";
  const tariff = order.overstay_basis;
  const canPay = ownerCan(order, "simulate") && demo && Boolean(order.demo_token) && !needsRefresh;
  return <Section title="Chi tiết đơn vé" description={`Mã đơn: ${order.id}`} actions={<Button variant="outlined" disabled={busy} onClick={onRefresh}>Cập nhật trạng thái</Button>}>
    <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ alignItems: "flex-start" }}>
      {canPay && order.demo_qr_svg && <Box component="img" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(order.demo_qr_svg)}`} alt="Mã QR mô phỏng đồ án, không chuyển tiền ngân hàng" sx={{ width: 220, maxWidth: "100%", height: 220, bgcolor: "white", alignSelf: "center" }} />}
      <Stack spacing={2} sx={{ minWidth: 0, flex: 1 }}>
        <Box><Typography variant="h5" component="h3">{order.plan_name || `${productLabel(order)} · gói #${order.plan_id}`}</Typography><Typography color="text.secondary">{productLabel(order)}{order.duration_days || order.duration_minutes ? ` · ${productDuration(order)}` : ""} · {paymentModeLabel(order.payment_mode)}</Typography></Box>
        <Typography variant="h5" component="p" fontWeight={700}>{money(order.amount)}</Typography>
        <Box><StateChip value={order.status} label={orderStatusLabel(order.status)} /></Box>
        <Box component="dl" sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "160px 1fr" }, gap: 0.75, m: 0, "& dt": { color: "text.secondary" }, "& dd": { m: 0, mb: { xs: 1, sm: 0 }, overflowWrap: "anywhere" } }}>
          <Typography component="dt">Hiệu lực</Typography><Typography component="dd">{timed ? `${dateTime(order.start_at)} – ${dateTime(order.end_at)}` : `${dateOnly(order.start_date)} – hết ${dateOnly(order.end_date)}`}</Typography>
          {timed && <><Typography component="dt">Hạn đến bãi</Typography><Typography component="dd">Trước {dateTime(order.arrival_deadline)}</Typography><Typography component="dt">Chỗ được xếp</Typography><Typography component="dd">{order.slot ? `${order.slot.zone_name} · ${order.slot.name}` : "Chưa được xếp chỗ"}</Typography><Typography component="dt">Quyền gửi xe</Typography><Typography component="dd">{entitlementLabel(order.entitlement_status)}</Typography></>}
          {order.hold_expires_at && <><Typography component="dt">Hạn thanh toán giữ chỗ</Typography><Typography component="dd">{dateTime(order.hold_expires_at)}</Typography></>}
        </Box>
        {timed && <Typography color="text.secondary">Gói dùng cho một lượt liên tục. Đến muộn không đổi giờ kết thúc. Nhân viên xác nhận xe thực sự vào bãi; mua vé chưa phải là xe đã vào.</Typography>}
        {!timed && <Typography color="text.secondary">Vé tháng dùng nhiều lượt theo kỳ, không mặc nhiên giữ một ô đỗ.</Typography>}
        {tariff && <Typography>Phí quá giờ đã chốt: <strong>{money(tariff.unit_price)} / {tariff.ticket_type === "DAILY" ? "24 giờ" : "giờ"}</strong>, tính từ cuối gói theo từng đơn vị bắt đầu. {tariff.effective_date && `Giá áp dụng ngày ${dateOnly(tariff.effective_date)}.`}</Typography>}
        {timed && !tariff && <Typography color="text.secondary">Đơn chưa có thông tin giá quá giờ được lưu.</Typography>}
        {order.status === "pending" && remaining > 0 && <Typography color="text.secondary">Giữ chỗ còn khoảng {Math.floor(remaining / 60)} phút {remaining % 60} giây theo giờ máy chủ.</Typography>}
        {needsRefresh && <Alert severity="warning">Đã tới hạn giữ chỗ hiển thị. Cập nhật trạng thái để biết kết quả từ máy chủ trước khi tiếp tục.</Alert>}
        {order.status === "review" && <Alert severity="warning">Đơn cần quản lý đối soát. Trạng thái nhận tiền và quyền vào bãi đang được kiểm tra; không tạo lại đơn để thay thế khoản đã trả.</Alert>}
        {order.status === "pending" && order.payment_mode === "manual" && <Alert severity="info">Mang mã đơn đến quầy để xác nhận thu tiền{timed ? " trước hạn giữ chỗ trên đơn" : ""}. Chỉ trạng thái máy chủ xác nhận mới cấp quyền sử dụng.</Alert>}
        {order.payment_mode === "payos" && <OnlinePaymentPanel key={order.id} orderId={order.id} onOrderRefresh={onRefresh} />}
        {canPay && order.demo_payload && <TextField label="Nội dung QR mô phỏng" value={order.demo_payload} multiline slotProps={{ input: { readOnly: true } }} />}
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          {canPay && [["success", "Giả lập thanh toán thành công"], ["failed", "Giả lập thất bại"]].map(([outcome, label]) => <Button key={outcome} variant={outcome === "success" ? "contained" : "outlined"} disabled={busy} onClick={() => onSimulate(outcome)}>{label}</Button>)}
          {ownerCan(order, "cancel") && <Button variant="outlined" color="error" disabled={busy} onClick={onCancel}>Hủy đơn chưa thanh toán</Button>}
        </Stack>
        {ownerCan(order, "request_refund") && <Box component="form" onSubmit={(event) => { event.preventDefault(); onRefund(reason.trim()); }}><Stack spacing={1}>
          <TextField required label="Lý do yêu cầu hoàn" value={reason} onChange={(event) => setReason(event.target.value)} disabled={busy} multiline minRows={2} inputProps={{ maxLength: 500 }} />
          <Typography variant="body2" color="text.secondary">{demo ? "Đây là yêu cầu hoàn mô phỏng đồ án." : "Quản lý sẽ kiểm tra điều kiện và khoản thanh toán."} Gửi yêu cầu chưa có nghĩa tiền đã được hoàn.</Typography>
          <Button type="submit" variant="outlined" disabled={busy || !reason.trim()} sx={{ alignSelf: "flex-start" }}>Gửi yêu cầu hoàn</Button>
        </Stack></Box>}
      </Stack>
    </Stack>
  </Section>;
}
