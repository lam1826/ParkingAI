import { useEffect, useState, useSyncExternalStore } from "react";
import { Alert, Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControl, FormControlLabel, FormLabel, Radio, RadioGroup, Stack, Typography } from "@mui/material";
import { formatBusinessDateOnly, formatBusinessTimestamp } from "../../../utils/formatDate";
import { formatParkingFee } from "../../../utils/formatCurrency";
import { formatParkingDuration } from "../sessionPresentation";
import { createCheckoutFlow } from "../checkoutFlow";
import parkingSessionService from "../services/parkingSessionService";

export default function CheckoutDialog({ sessionId, onClose, onCompleted }) {
  const [flow] = useState(() => {
    const token = localStorage.getItem("token");
    return createCheckoutFlow({ sessionId, loadQuote: parkingSessionService.getCheckoutQuote,
      confirmCheckout: parkingSessionService.checkOut, onCompleted,
      isAuthorized: () => Boolean(token) && localStorage.getItem("token") === token });
  });
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  useEffect(() => {
    void flow.start();
    const timer = window.setInterval(flow.tick, 1000);
    const protectPending = (event) => {
      if (!flow.canDismiss()) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", protectPending);
    return () => { flow.stop(); window.clearInterval(timer); window.removeEventListener("beforeunload", protectPending); };
  }, [flow]);

  const { quote, phase, paymentMethod, paymentConfirmed, expired } = state;
  const loading = phase === "idle" || phase === "loading";
  const pending = phase === "submitting";
  const uncertain = phase === "uncertain";
  const free = quote?.parking_fee === 0;
  const editable = phase === "ready" && !expired;
  const canConfirm = uncertain || (editable && (free || (Boolean(paymentMethod) && paymentConfirmed)));
  const dismiss = () => { if (flow.canDismiss()) onClose(); };

  return <Dialog open onClose={dismiss} maxWidth="sm" fullWidth aria-labelledby="checkout-title">
    <DialogTitle id="checkout-title" fontWeight="bold">Xem phí và xác nhận xe ra</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2.5}>
        {state.error && <Alert severity={uncertain ? "warning" : "error"}>{state.error}</Alert>}
        {state.notice && <Alert severity="info">{state.notice}</Alert>}
        {loading && <Stack direction="row" spacing={2} role="status" sx={{ alignItems: "center", py: 3 }}>
          <CircularProgress size={24} /><Typography>Đang lấy phí của lượt gửi xe…</Typography>
        </Stack>}
        {quote && <>
          <Box>
            <Typography variant="h5" component="p" fontWeight={700} sx={{ overflowWrap: "anywhere" }}>{quote.license_plate}</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5, overflowWrap: "anywhere" }}>
              {[quote.zone_name, quote.slot_name].filter(Boolean).join(" · ") || "Chưa có thông tin vị trí"}
            </Typography>
          </Box>
          <Box component="dl" sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "140px 1fr" }, columnGap: 2, rowGap: 0.75, m: 0,
            "& dt": { color: "text.secondary" }, "& dd": { m: 0, mb: { xs: 1, sm: 0 }, overflowWrap: "anywhere" } }}>
            <Typography component="dt">Giờ vào</Typography><Typography component="dd">{formatBusinessTimestamp(quote.check_in_time)}</Typography>
            <Typography component="dt">Thời gian gửi</Typography><Typography component="dd">{formatParkingDuration(quote.duration_minutes)} (tính đến lúc xem phí)</Typography>
            <Typography component="dt">Vé tháng</Typography><Typography component="dd">
              {quote.monthly_coverage_end ? `Lượt này được hưởng quyền vé tháng đến hết ${formatBusinessDateOnly(quote.monthly_coverage_end)}.` : "Lượt này không được áp dụng vé tháng."}
            </Typography>
          </Box>
          <Box sx={{ borderTop: "1px solid", borderBottom: "1px solid", borderColor: "divider", py: 2 }}>
            <Typography>{free ? "Phí gửi xe" : "Số tiền cần thu"}</Typography>
            <Typography variant="h4" component="p" fontWeight={700} sx={{ mt: 0.5, fontVariantNumeric: "tabular-nums" }}>
              {formatParkingFee(quote.parking_fee)} VND
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
              {free ? "Không thu tiền cho lượt xe ra này." : `Phí có hiệu lực đến ${formatBusinessTimestamp(quote.expires_at)}.`}
            </Typography>
          </Box>
          {expired && phase === "ready" && <Alert severity="warning">Phí xem trước đã hết hiệu lực. Tải lại phí và kiểm tra số tiền trước khi xác nhận.</Alert>}
          {!free && <>
            <FormControl disabled={!editable}>
              <FormLabel id="checkout-payment-label">Hình thức đã thu tiền</FormLabel>
              <RadioGroup row aria-labelledby="checkout-payment-label" value={paymentMethod} onChange={event => flow.setPaymentMethod(event.target.value)}>
                <FormControlLabel value="cash" control={<Radio />} label="Tiền mặt" />
                <FormControlLabel value="transfer" control={<Radio />} label="Chuyển khoản" />
              </RadioGroup>
              {paymentMethod === "transfer" && <Typography variant="body2" color="text.secondary">Chỉ xác nhận khi đã kiểm tra tiền vào tài khoản. Hệ thống ghi nhận khoản thu do nhân viên xác nhận.</Typography>}
            </FormControl>
            <FormControlLabel disabled={!editable || !paymentMethod} sx={{ m: 0, alignItems: "flex-start" }}
              control={<Checkbox checked={paymentConfirmed} onChange={event => flow.setPaymentConfirmed(event.target.checked)} sx={{ pt: 0 }} />}
              label={`Tôi xác nhận đã nhận đủ ${formatParkingFee(quote.parking_fee)} VND cho lượt gửi xe này.`} />
          </>}
          {uncertain && <Typography variant="body2">Yêu cầu đã gửi được giữ nguyên, kể cả khi phí xem trước hết hiệu lực. Nút thử lại bên dưới kiểm tra hoặc hoàn tất chính yêu cầu đó.</Typography>}
        </>}
      </Stack>
    </DialogContent>
    <DialogActions sx={{ p: 2, gap: 1, flexWrap: "wrap", "& > :not(style) ~ :not(style)": { ml: 0 } }}>
      <Button variant="outlined" disabled={!flow.canDismiss()} onClick={dismiss}>{phase === "error" ? "Đóng" : "Hủy"}</Button>
      {(phase === "error" || (phase === "ready" && expired)) && <Button variant="contained" onClick={() => void flow.refresh()}>Tải lại phí</Button>}
      {quote && !(phase === "ready" && expired) && <Button variant="contained" disabled={!canConfirm || pending} onClick={() => void flow.submit()}
        startIcon={pending ? <CircularProgress size={18} color="inherit" /> : undefined} sx={{ flex: { xs: "1 1 100%", sm: "0 1 auto" } }}>
        {pending ? "Đang xác nhận…" : uncertain ? "Thử lại yêu cầu đã gửi" : free ? "Xác nhận xe ra miễn phí" : "Đã thu tiền — cho xe ra"}
      </Button>}
    </DialogActions>
  </Dialog>;
}
