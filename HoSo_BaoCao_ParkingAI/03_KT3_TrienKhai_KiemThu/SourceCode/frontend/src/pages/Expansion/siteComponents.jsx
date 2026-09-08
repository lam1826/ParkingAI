import { useRef, useState } from "react";
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { bookingBody, nextBookingWindow } from "./siteForms";
import { formLayout, requestKey, Records, dateTime, StateChip } from "./shared";
import SiteVehiclePicker from "./SiteVehiclePicker";

export function BookingForm({ siteId, slots = [], vehicles, action, onSubmit, kind = "reservation" }) {
  const [form, setForm] = useState(() => ({ vehicle_id: "", slot_id: "", ...nextBookingWindow() }));
  const key = useRef(requestKey());
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const change = (name) => (event) => setForm((old) => ({ ...old, [name]: event.target.value }));
  const waitlist = kind === "waitlist", allocation = kind === "allocation";
  const vehicleType = vehicles?.find((v) => String(v.id) === String(form.vehicle_id))?.vehicle_type_id || selectedVehicle?.vehicle_type_id;
  const choices = slots.filter((s) => !vehicleType || s.vehicle_type_id === vehicleType);
  const submit = (event) => {
    event.preventDefault();
    void action.run(async () => {
      const body = bookingBody(form, siteId, key.current, { waitlist });
      if (allocation && !body.slot_id) throw new Error("Gói bảo đảm chỗ cần chọn vị trí cụ thể.");
      return onSubmit(body);
    }, waitlist ? "Đã tham gia danh sách chờ." : allocation ? "Đã cấp quyền bảo đảm chỗ." : "Đã giữ chỗ. Vui lòng đến trong 15 phút từ giờ bắt đầu.",
    () => { key.current = requestKey(); });
  };
  return <Box component="form" onSubmit={submit}>
    <Box component="fieldset" disabled={action.busy} sx={{ ...formLayout, border: 0, p: 0, m: 0, minWidth: 0 }}>
      {vehicles ? <TextField select label="Xe của tôi" required value={form.vehicle_id} onChange={change("vehicle_id")}>
        {vehicles.map((vehicle) => <MenuItem key={vehicle.id} value={vehicle.id}>{vehicle.license_plate}</MenuItem>)}
      </TextField> : <SiteVehiclePicker siteId={siteId} value={selectedVehicle} disabled={action.busy} onChange={(vehicle) => {
        setSelectedVehicle(vehicle); setForm((old) => ({ ...old, vehicle_id: vehicle?.id || "", slot_id: "" }));
      }} />}
      {!waitlist && <TextField select label={allocation ? "Vị trí bảo đảm" : "Vị trí đỗ"} value={form.slot_id} onChange={change("slot_id")} required={allocation}>
        {!allocation && <MenuItem value="">Hệ thống chọn vị trí phù hợp</MenuItem>}
        {choices.map((slot) => <MenuItem key={slot.id} value={slot.id}>{slot.slot_name} · {slot.zone_name}{slot.is_occupied ? " · Đang có xe" : ""}</MenuItem>)}
      </TextField>}
      <TextField label="Bắt đầu (giờ Việt Nam)" type="datetime-local" required value={form.start_at} onChange={change("start_at")} slotProps={{ inputLabel: { shrink: true } }} />
      <TextField label="Kết thúc (giờ Việt Nam)" type="datetime-local" required value={form.end_at} onChange={change("end_at")} slotProps={{ inputLabel: { shrink: true } }} />
      <Button type="submit" variant="contained" disabled={action.busy || !siteId || (vehicles && vehicles.length === 0)} sx={{ alignSelf: "center", minHeight: 48 }}>
        {action.busy ? "Đang gửi…" : waitlist ? "Tham gia danh sách chờ" : allocation ? "Cấp quyền bảo đảm chỗ" : "Đặt chỗ"}
      </Button>
      <Button type="button" disabled={action.busy} onClick={() => {
        key.current = requestKey(); setSelectedVehicle(null); setForm({ vehicle_id: "", slot_id: "", ...nextBookingWindow() });
      }}>Nhập yêu cầu mới</Button>
    </Box>
    {action.error && <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>Nếu mất kết nối, làm mới lịch để kiểm tra kết quả trước. Gửi lại cùng nội dung giữ nguyên mã yêu cầu; chọn Nhập yêu cầu mới khi cần tạo một đặt chỗ khác.</Typography>}
  </Box>;
}

export function Availability({ data }) {
  if (!data) return <Typography color="text.secondary">Chọn bãi để xem vị trí.</Typography>;
  return <Stack spacing={2}>
    <Typography>Tổng {data.total} chỗ · Đang đỗ {data.occupied} · Có thể nhận xe vãng lai {data.available_now} · Đã dành chỗ {data.reserved_slots}</Typography>
    <Alert severity="info">Chỗ đang trống có thể đã được giữ cho thời điểm sau. Hệ thống kiểm tra chính xác khung giờ khi bạn đặt chỗ.</Alert>
    <Records rows={data.slots || []} columns={[
      { key: "slot_name", label: "Vị trí" }, { key: "zone_name", label: "Khu vực" },
      { key: "vehicle_type_id", label: "Mã loại xe" },
      { key: "availability", label: "Hiện trạng", render: (row) => row.is_occupied ? "Đang có xe" : row.reserved ? "Có cam kết giữ chỗ" : "Trống" },
    ]} />
  </Stack>;
}

export function BookingRecords({ rows, onCancel, onArrive, busy, slots = [], vehicles = [] }) {
  return <Records rows={rows} columns={[
    { key: "vehicle_id", label: "Xe", render: (r) => vehicles.find((v) => v.id === r.vehicle_id)?.license_plate || `Xe #${r.vehicle_id}` },
    { key: "slot_id", label: "Vị trí", render: (r) => slots.find((s) => s.id === r.slot_id)?.slot_name || `Chỗ #${r.slot_id}` },
    { key: "start_at", label: "Bắt đầu", render: (r) => dateTime(r.start_at) },
    { key: "end_at", label: "Kết thúc", render: (r) => dateTime(r.end_at) },
    { key: "arrival_deadline", label: "Hạn đến", render: (r) => dateTime(r.arrival_deadline) },
    { key: "status", label: "Trạng thái", render: (r) => <StateChip value={r.status} /> },
    { key: "actions", label: "Thao tác", render: (r) => <Stack direction="row" spacing={1} useFlexGap>
      {onArrive && r.status === "confirmed" && <Button disabled={busy} onClick={() => onArrive(r)} aria-label={`Xác nhận xe ${r.vehicle_id} đã đến`}>Xe đã đến</Button>}
      {onCancel && ["confirmed", "active"].includes(r.status) && <Button color="error" disabled={busy} onClick={() => onCancel(r)} aria-label={`Hủy giữ chỗ xe ${r.vehicle_id}`}>Hủy</Button>}
    </Stack> },
  ]} />;
}

export function WaitlistRecords({ rows, vehicles = [], onOffer, onCancel, busy }) {
  return <Records rows={rows} columns={[
    { key: "vehicle_id", label: "Xe", render: (row) => vehicles.find((vehicle) => vehicle.id === row.vehicle_id)?.license_plate || `Xe #${row.vehicle_id}` },
    { key: "start_at", label: "Bắt đầu", render: (row) => dateTime(row.start_at) },
    { key: "end_at", label: "Kết thúc", render: (row) => dateTime(row.end_at) },
    { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} /> },
    { key: "actions", label: "Thao tác", render: (row) => row.status === "waiting" && <Stack direction="row" spacing={1} useFlexGap>
      {onOffer && <Button disabled={busy} onClick={() => onOffer(row)}>Cấp chỗ trống</Button>}
      {onCancel && <Button color="error" disabled={busy} onClick={() => onCancel(row)}>Rời danh sách chờ</Button>}
    </Stack> },
  ]} />;
}
