import { Alert, Stack, Typography } from "@mui/material";
import { prepaidPresentation } from "../billingPresentation";

export default function PrepaidDetails({ prepaid }) {
  if (!prepaid) return null;
  const details = prepaidPresentation(prepaid);
  if (!details.available) return <Typography color="text.secondary">Chưa có đủ thông tin gói trả trước để hiển thị.</Typography>;
  return <Stack spacing={0.75}>
    <Typography component="h3" variant="subtitle1" fontWeight={700}>{details.demo ? "Gói đã xác nhận — DEMO" : "Gói đã thanh toán"}: {details.amount}</Typography>
    <Typography>Khung giờ đã mua: {details.start} – {details.end}</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>Đơn vé: {details.orderId}</Typography>
    <Typography color="text.secondary">Khoản gói được ghi riêng. Chỉ thu thêm phí phát sinh khi xe ra quá giờ.</Typography>
    {details.demo && <Alert severity="info">Khoản gói là mô phỏng đồ án, không phải tiền ngân hàng đã nhận.</Alert>}
  </Stack>;
}
