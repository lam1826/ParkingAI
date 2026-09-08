import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { dateTime, endpoint, formLayout, money, PageControls, read, Records, Section, send, StateChip, useAction, useRemote } from "./shared";
import SiteVehiclePicker from "./SiteVehiclePicker";

const PAGE_SIZE = 50;

export default function FleetSection({ organizations = [], canManage = false, siteId }) {
  const [choice, setChoice] = useState("");
  const organizationId = organizations.some((row) => String(row.id) === String(choice)) ? choice : organizations[0]?.id || "";
  const [vehicle, setVehicle] = useState(null);
  const [memberId, setMemberId] = useState("");
  const [page, setPage] = useState(0);
  const load = useCallback(() => organizationId
    ? read(`/organizations/${organizationId}/fleet`, { limit: PAGE_SIZE, offset: page * PAGE_SIZE })
    : Promise.resolve(null), [organizationId, page]);
  const remote = useRemote(load);
  const action = useAction(remote.reload);
  useEffect(() => { setVehicle(null); setMemberId(""); setPage(0); }, [organizationId]);
  const submit = (kind) => (event) => {
    event.preventDefault();
    const id = Number(kind === "fleet" ? vehicle?.id : memberId);
    void action.run(() => {
      if (!Number.isSafeInteger(id) || id < 1) throw new Error("Mã phải là số nguyên dương.");
      return send(`/organizations/${organizationId}/${kind}`, { [kind === "fleet" ? "vehicle_id" : "user_id"]: id });
    }, kind === "fleet" ? "Đã thêm xe vào nhóm." : "Đã cấp quyền xem nhóm.");
  };
  return <Section title="Đội xe" description="Chỉ tổng hợp lượt gửi tại bãi của nhóm, kể từ khi xe được thêm vào nhóm.">
    {!organizations.length ? <Typography color="text.secondary">Chưa có nhóm xe được cấp quyền xem.</Typography> : <>
      <TextField select label="Nhóm xe" value={organizationId} onChange={(event) => setChoice(event.target.value)} disabled={action.busy} sx={{ maxWidth: 480 }}>
        {organizations.map((row) => <MenuItem key={row.id} value={row.id}>{row.name}</MenuItem>)}
      </TextField>
      {remote.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={remote.reload} disabled={remote.loading}>Thử lại</Button>}>{remote.error}</Alert>}
      {action.error && <Alert severity="error">{action.error}</Alert>}
      {action.notice && <Alert severity="success">{action.notice}</Alert>}
      {remote.loading && <Typography role="status">Đang tải đội xe…</Typography>}
      {!remote.loading && remote.data && <>
        <Typography>Tổng lượt: {remote.data.total_sessions ?? 0} · Đang đỗ: {remote.data.active_sessions} · Đã hoàn tất: {remote.data.completed_sessions} · Tổng phí lượt gửi: {money(remote.data.parking_fees)}</Typography>
        <Typography variant="body2" color="text.secondary">{remote.data.fee_note || "Tổng phí lượt gửi chưa trừ hoàn tiền và không phải hóa đơn công nợ."}</Typography>
        <Records rows={remote.data.vehicles} columns={[
          { key: "vehicle_id", label: "Mã xe" }, { key: "license_plate", label: "Biển số" },
          { key: "joined_at", label: "Tham gia nhóm", render: (row) => dateTime(row.joined_at) },
          ...(canManage ? [{ key: "remove", label: "Thao tác", render: (row) => <Button color="error" disabled={action.busy}
            onClick={() => void action.run(() => api.delete(endpoint(`/organizations/${organizationId}/fleet/${row.vehicle_id}`)), "Đã gỡ xe khỏi nhóm.")}>Gỡ xe</Button> }] : []),
        ]} />
        <Records rows={remote.data.sessions} empty="Chưa có lượt gửi trong phạm vi nhóm." columns={[
          { key: "license_plate", label: "Biển số" }, { key: "slot_name", label: "Vị trí" },
          { key: "check_in_time", label: "Giờ vào", render: (row) => dateTime(row.check_in_time) },
          { key: "check_out_time", label: "Giờ ra", render: (row) => dateTime(row.check_out_time) },
          { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} /> },
          { key: "parking_fee", label: "Phí", render: (row) => row.parking_fee == null ? "Chưa tính phí" : money(row.parking_fee) },
        ]} />
        <PageControls page={page} count={remote.data.sessions?.length || 0} size={PAGE_SIZE} busy={remote.loading || action.busy} onChange={setPage} />
      </>}
      {canManage && <Stack spacing={2}>
        <Box component="form" onSubmit={submit("fleet")} sx={formLayout}>
          <SiteVehiclePicker siteId={siteId} value={vehicle} onChange={setVehicle} disabled={action.busy} label="Xe cần thêm vào nhóm" />
          <Button type="submit" variant="outlined" disabled={action.busy}>Thêm xe vào nhóm</Button>
        </Box>
        <Box component="form" onSubmit={submit("members")} sx={formLayout}>
          <TextField label="Mã tài khoản được xem nhóm" type="number" required value={memberId} onChange={(event) => setMemberId(event.target.value)} slotProps={{ htmlInput: { min: 1, step: 1 } }} />
          <Button type="submit" variant="outlined" disabled={action.busy}>Cấp quyền xem</Button>
          <Button color="error" disabled={action.busy || !Number.isSafeInteger(Number(memberId)) || Number(memberId) < 1}
            onClick={() => void action.run(() => api.delete(endpoint(`/organizations/${organizationId}/members/${Number(memberId)}`)), "Đã thu hồi quyền xem của tài khoản.")}>Thu hồi quyền tài khoản này</Button>
        </Box>
      </Stack>}
    </>}
  </Section>;
}
