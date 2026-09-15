import { useEffect, useState, useSyncExternalStore } from "react";
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { createPortalOrderFlow } from "./portalOrderFlow";
import { matchingPlans, portalOrderBody, productDuration, productKind } from "./portalOffers";
import { nextBookingWindow } from "./siteForms";
import { formLayout, money, requestKey, Section, send } from "./shared";
import { paymentModes, paymentModeLabel } from "./onlinePaymentState";

export default function PortalPurchase({ vehicles, plans, demoPaymentsEnabled, onCreated, onLocked, visible, initialKind = "monthly" }) {
  const [form, setForm] = useState(() => ({ vehicle_id: "", plan_id: "", zone_id: "", kind: ["monthly", "hourly", "daily"].includes(initialKind) ? initialKind : "monthly", start_at: nextBookingWindow().start_at }));
  const [flow] = useState(() => {
    const token = localStorage.getItem("token");
    return createPortalOrderFlow({ createOrder: (body) => send("/me/orders", body), createKey: requestKey, onCreated,
      isAuthorized: () => Boolean(token) && localStorage.getItem("token") === token });
  });
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const pending = state.phase === "submitting", uncertain = state.phase === "uncertain";
  const locked = pending || uncertain;
  const vehicleRows = vehicles.data || [], planRows = plans.data || [];
  const vehicle = vehicleRows.find((row) => String(row.id) === String(form.vehicle_id));
  const choices = matchingPlans(planRows, vehicle, form.kind);
  const selectedPlan = choices.find((row) => String(row.id) === String(form.plan_id));
  const timed = selectedPlan && productKind(selectedPlan) !== "monthly";
  const modes = paymentModes(selectedPlan, demoPaymentsEnabled);
  const paymentMode = modes.includes(form.payment_mode) ? form.payment_mode : modes[0];
  const catalogBusy = plans.loading || vehicles.loading;
  const catalogError = plans.error || vehicles.error;
  useEffect(() => { onLocked?.(locked); return () => onLocked?.(false); }, [locked, onLocked]);
  useEffect(() => {
    const protect = (event) => { if (!flow.canReset()) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [flow]);
  const edit = (field) => (event) => setForm((old) => ({ ...old, [field]: event.target.value,
    ...(["vehicle_id", "kind"].includes(field) ? { plan_id: "", zone_id: "" } : field === "plan_id" ? { zone_id: "" } : {}) }));
  const submit = (event) => {
    event.preventDefault();
    void flow.submit((key) => portalOrderBody(form, planRows, vehicleRows, paymentMode, key));
  };
  return <Box sx={{ display: visible ? "block" : "none" }}><Section title="Mua vé và đặt chỗ" description="Chọn xe đã xác minh, loại vé và gói phù hợp. Giá và thời hạn cuối cùng được ghi trên đơn.">
    {catalogError && <Alert severity="error" action={<Button disabled={catalogBusy || locked} onClick={() => { void vehicles.reload(); void plans.reload(); }}>Thử lại</Button>}>{catalogError}</Alert>}
    {catalogBusy && <Typography role="status">Đang tải xe và gói vé…</Typography>}
    {state.error && <Alert severity={uncertain ? "warning" : "error"}>{state.error}</Alert>}
    {state.phase === "completed" ? <Stack spacing={2}>
      <Alert severity="success">Đã tạo đơn. Kiểm tra thời hạn và thanh toán ở phần chi tiết bên dưới.</Alert>
      <Button variant="outlined" sx={{ alignSelf: "flex-start" }} onClick={() => flow.reset()}>Mua thêm vé</Button>
    </Stack> : <Box component="form" onSubmit={submit}>
      <Box component="fieldset" disabled={locked || catalogBusy || !!catalogError} sx={{ ...formLayout, border: 0, p: 0, m: 0, minWidth: 0 }}>
        <TextField select required label="Xe sử dụng" value={vehicle ? form.vehicle_id : ""} onChange={edit("vehicle_id")}>{vehicleRows.map((car) => <MenuItem key={car.id} value={car.id}>{car.license_plate} · {car.type_name}</MenuItem>)}</TextField>
        <TextField select required label="Loại vé" value={form.kind} onChange={edit("kind")}><MenuItem value="monthly">Vé tháng</MenuItem><MenuItem value="hourly">Vé giờ</MenuItem><MenuItem value="daily">Vé ngày (24 giờ)</MenuItem></TextField>
        <TextField select required label="Gói vé" value={selectedPlan ? form.plan_id : ""} disabled={!vehicle} onChange={edit("plan_id")}>{choices.map((plan) => <MenuItem key={plan.id} value={plan.id}>{plan.name} · {productDuration(plan)} · {money(plan.price)}</MenuItem>)}</TextField>
        <TextField select required label="Hình thức thanh toán" value={paymentMode || ""} disabled={!selectedPlan} onChange={edit("payment_mode")}>{modes.map((mode) => <MenuItem key={mode} value={mode}>{paymentModeLabel(mode)}</MenuItem>)}</TextField>
        {timed && <>
          <TextField required type="datetime-local" label="Bắt đầu (giờ Việt Nam)" value={form.start_at} onChange={edit("start_at")} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField select label="Khu vực đỗ" value={selectedPlan.eligible_zones?.some((zone) => String(zone.id) === String(form.zone_id)) ? form.zone_id : ""} onChange={edit("zone_id")}>
            <MenuItem value="">Hệ thống chọn khu phù hợp</MenuItem>{selectedPlan.eligible_zones?.map((zone) => <MenuItem key={zone.id} value={zone.id}>{zone.name}</MenuItem>)}
          </TextField>
        </>}
      </Box>
      {!catalogBusy && !catalogError && !vehicleRows.length && <Typography color="text.secondary" sx={{ mt: 2 }}>Bạn cần xe đã được xác minh. Mở mục Xe của tôi để gửi yêu cầu thêm xe.</Typography>}
      {!catalogBusy && !catalogError && vehicle && !choices.length && <Typography color="text.secondary" sx={{ mt: 2 }}>Chưa có gói {form.kind === "monthly" ? "vé tháng" : form.kind === "hourly" ? "vé giờ" : "vé ngày"} cho loại xe này. Chọn loại vé khác hoặc liên hệ bãi.</Typography>}
      {selectedPlan && <Alert severity={timed && !selectedPlan.eligible_zones?.length ? "warning" : "info"} sx={{ mt: 2 }}>
        {timed ? (!selectedPlan.eligible_zones?.length ? "Gói này chưa có khu vực đang phục vụ. Hãy chọn gói khác."
          : "Một lượt gửi trong khung giờ cố định. Đến muộn không kéo dài giờ kết thúc. Đơn giữ chỗ tối đa 10 phút để thanh toán; phí quá giờ theo giá chốt trên đơn.")
          : "Vé tháng áp dụng nhiều lượt trong kỳ, đến hết ngày cuối. Vé tháng không bảo đảm một chỗ trống khi bãi đã đầy."}
      </Alert>}
      <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 2, flexWrap: "wrap" }}>
        <Button type="submit" variant="contained" disabled={pending || (!uncertain && (catalogBusy || !!catalogError || !selectedPlan || (timed && !selectedPlan.eligible_zones?.length)))}>
          {pending ? "Đang tạo đơn…" : uncertain ? "Thử lại yêu cầu đã gửi" : timed ? "Tạo đơn giữ chỗ" : "Tạo đơn mua vé tháng"}
        </Button>
        {state.error && !locked && <Button type="button" variant="outlined" onClick={() => flow.reset()}>Bắt đầu yêu cầu mới</Button>}
      </Stack>
    </Box>}
  </Section></Box>;
}
