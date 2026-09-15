import { Alert, Box, Stack, Typography } from "@mui/material";
import { billingPresentation } from "../billingPresentation";

export default function BillingBasisDetails({ basis, active = false, preview = false }) {
  const presentation = billingPresentation(basis);
  if (!presentation.available) return <Typography color="text.secondary">
    {preview ? "Chưa có thông tin căn cứ giá cho phí xem trước này." : active ? "Căn cứ giá sẽ hiển thị khi xem phí xe ra." : "Lượt lịch sử này chưa có căn cứ giá được lưu."}
  </Typography>;
  return <Stack spacing={1.5}>
    <Typography component="h3" variant="subtitle1" fontWeight={700}>{presentation.prepaid ? "Căn cứ phí phát sinh" : "Căn cứ tính phí"}</Typography>
    <Typography color="text.secondary">{presentation.sourceLabel}</Typography>
    {presentation.legacy && <Alert severity="info">Lượt này được tạo trước khi ghi nhận giá lúc xe vào. Hệ thống giữ chính sách tính phí cũ cho lượt này.</Alert>}
    <Box component="dl" sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "170px 1fr" }, gap: 0.75, m: 0,
      "& dt": { color: "text.secondary" }, "& dd": { m: 0, mb: { xs: 1, sm: 0 }, overflowWrap: "anywhere" } }}>
      {presentation.rows.map((row) => <Box key={row.label} sx={{ display: "contents" }}>
        <Typography component="dt">{row.label}</Typography><Typography component="dd">{row.value}</Typography>
      </Box>)}
    </Box>
  </Stack>;
}
