import { useCallback, useState } from "react";
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { endpoint, formLayout, PageControls, read, Records, RemoteSection, Section, send, usePage, useRemote } from "./shared";
import { useExpansion } from "../../context/ExpansionContext";

export function CreateSiteForm({ action, onCreated }) {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  return <Section title="Tạo bãi đỗ xe" description="Sau khi tạo bãi, thêm khu vực và vị trí đỗ trong mục Cấu hình bãi.">
    <Box component="form" onSubmit={(event) => {
      event.preventDefault();
      void action.run(() => send("/sites", { name: name.trim(), address: address.trim() }), "Đã tạo bãi.", (result) => {
        setName(""); setAddress(""); window.dispatchEvent(new Event("parkingai:sites-changed")); onCreated?.(result);
      });
    }} sx={formLayout}>
      <TextField label="Tên bãi" value={name} onChange={(event) => setName(event.target.value)} required slotProps={{ htmlInput: { maxLength: 100 } }} />
      <TextField label="Địa chỉ" value={address} onChange={(event) => setAddress(event.target.value)} slotProps={{ htmlInput: { maxLength: 250 } }} />
      <Button type="submit" variant="contained" disabled={action.busy}>Tạo bãi</Button>
    </Box>
  </Section>;
}

export default function SiteConfiguration({ siteId, zones, types, members, isAdmin, action }) {
  const capabilities = useExpansion();
  const [edit, setEdit] = useState(null);
  const page = usePage();
  const loadSlots = useCallback(() => capabilities?.site_finance_enabled ? read(`/sites/${siteId}/slots`, { offset: page.page * 25, limit: 25 }) : Promise.resolve([]), [siteId, page.page, capabilities?.site_finance_enabled]);
  const inventory = useRemote(loadSlots);
  const [zone, setZone] = useState({ name: "", capacity: "10" });
  const [slot, setSlot] = useState({ slot_name: "", zone_id: "", vehicle_type_id: "" });
  const [member, setMember] = useState({ user_id: "", role: "staff" });
  const change = (setter, name) => (event) => setter((old) => ({ ...old, [name]: event.target.value }));
  return <Stack spacing={3}>
    <Section title="Khu vực đỗ" description="Tên khu vực và mã vị trí là duy nhất trong toàn hệ thống. Có thể dùng tên bãi làm tiền tố.">
      <Box component="form" sx={formLayout} onSubmit={(event) => {
        event.preventDefault();
        void action.run(() => send(`/sites/${siteId}/zones`, { name: zone.name.trim(), capacity: Number(zone.capacity) }), "Đã tạo khu vực.", () => setZone((old) => ({ ...old, name: "" })));
      }}>
        <TextField label="Tên khu vực" required value={zone.name} onChange={change(setZone, "name")} slotProps={{ htmlInput: { maxLength: 50 } }} />
        <TextField label="Sức chứa tối đa" required type="number" value={zone.capacity} onChange={change(setZone, "capacity")} slotProps={{ htmlInput: { min: 0, step: 1, max: 10000 } }} />
        <Button type="submit" variant="contained" disabled={action.busy}>Thêm khu vực</Button>
      </Box>
      <Records rows={zones} columns={[{ key: "id", label: "Mã khu" }, { key: "name", label: "Tên khu vực" }, { key: "capacity", label: "Sức chứa" }, { key: "is_active", label: "Hoạt động", render: (row) => row.is_active ? "Có" : "Không" }, ...(capabilities?.site_finance_enabled ? [{ key: "edit", label: "Thao tác", render: (row) => <Button disabled={action.busy} onClick={() => setEdit({ kind: "zones", ...row })}>Sửa khu vực</Button> }] : [])]} />
    </Section>
    <Section title="Thêm vị trí đỗ" description="Chỗ mới chưa có xe. Trạng thái có xe chỉ thay đổi qua thao tác xe vào/ra.">
      <Box component="form" sx={formLayout} onSubmit={(event) => {
        event.preventDefault();
        void action.run(() => send(`/sites/${siteId}/slots`, { slot_name: slot.slot_name.trim(), zone_id: Number(slot.zone_id), vehicle_type_id: Number(slot.vehicle_type_id) }), "Đã tạo vị trí đỗ.", () => { setSlot((old) => ({ ...old, slot_name: "" })); void inventory.reload(); });
      }}>
        <TextField label="Mã vị trí" required value={slot.slot_name} onChange={change(setSlot, "slot_name")} slotProps={{ htmlInput: { maxLength: 50 } }} />
        <TextField select label="Khu vực" required value={slot.zone_id} onChange={change(setSlot, "zone_id")}>
          {zones.filter((row) => row.is_active).map((row) => <MenuItem key={row.id} value={row.id}>{row.name}</MenuItem>)}
        </TextField>
        <TextField select label="Loại xe" required value={slot.vehicle_type_id} onChange={change(setSlot, "vehicle_type_id")}>
          {types.map((row) => <MenuItem key={row.id} value={row.id}>{row.name}</MenuItem>)}
        </TextField>
        <Button type="submit" variant="contained" disabled={action.busy || !zones.length || !types.length}>Thêm vị trí</Button>
      </Box>
    </Section>
    <Section title="Nhân sự được phân công" description={isAdmin ? "Tài khoản phải có vai trò nhân viên hoặc quản lý trước khi cấp quyền tại bãi." : "Quản trị viên hệ thống cấp và thu hồi quyền vận hành theo từng bãi."}>
      <Records rows={members} columns={[
        { key: "user_id", label: "Mã tài khoản" }, { key: "role", label: "Quyền tại bãi", render: (row) => row.role === "manager" ? "Quản lý bãi" : "Nhân viên bãi" },
        ...(isAdmin ? [{ key: "remove", label: "Thao tác", render: (row) => <Button color="error" disabled={action.busy} onClick={() => void action.run(() => api.delete(endpoint(`/sites/${siteId}/members/${row.user_id}`)), "Đã thu hồi quyền tại bãi.")}>Thu hồi quyền</Button> }] : []),
      ]} />
      {isAdmin && <Box component="form" sx={formLayout} onSubmit={(event) => {
        event.preventDefault();
        void action.run(() => send(`/sites/${siteId}/members`, { user_id: Number(member.user_id), role: member.role }), "Đã cập nhật quyền tại bãi.");
      }}>
        <TextField label="Mã tài khoản nhân sự" type="number" required value={member.user_id} onChange={change(setMember, "user_id")} slotProps={{ htmlInput: { min: 1, step: 1 } }} />
        <TextField select label="Quyền tại bãi" value={member.role} onChange={change(setMember, "role")}>
          <MenuItem value="staff">Nhân viên bãi</MenuItem><MenuItem value="manager">Quản lý bãi</MenuItem>
        </TextField>
        <Button type="submit" variant="contained" disabled={action.busy}>Cấp / cập nhật quyền</Button>
      </Box>}
      {isAdmin && <Typography variant="body2" color="text.secondary">Quản trị viên hệ thống có quyền tại mọi bãi và không xuất hiện trong danh sách phân công.</Typography>}
    </Section>
    {capabilities?.site_finance_enabled && <RemoteSection remote={inventory} title="Danh sách vị trí" description="Bao gồm vị trí đã tạm ngừng. Không thể thay đổi vị trí có xe hoặc đang được giữ trái với cam kết." actions={<Button onClick={inventory.reload} disabled={inventory.loading || action.busy}>Làm mới vị trí</Button>}>{(rows) => <>
      <Records rows={rows} columns={[{ key: "slot_name", label: "Mã vị trí" }, { key: "zone_id", label: "Khu vực", render: (row) => zones.find((zone) => zone.id === row.zone_id)?.name || row.zone_id }, { key: "is_active", label: "Hoạt động", render: (row) => row.is_active ? "Có" : "Tạm ngừng" }, { key: "edit", label: "Thao tác", render: (row) => <Button disabled={action.busy} onClick={() => setEdit({ kind: "slots", ...row })}>Sửa vị trí</Button> }]} />
      <PageControls page={page.page} size={25} count={rows.length} onChange={page.setPage} busy={inventory.loading || action.busy} />
    </>}</RemoteSection>}
    <Dialog open={!!edit} onClose={() => { if (!action.busy) setEdit(null); }} fullWidth maxWidth="sm">
      {edit && <Box component="form" onSubmit={(event) => {
        event.preventDefault();
        const body = edit.kind === "zones" ? { name: edit.name.trim(), capacity: Number(edit.capacity), is_active: edit.is_active } : { slot_name: edit.slot_name.trim(), zone_id: Number(edit.zone_id), vehicle_type_id: Number(edit.vehicle_type_id), is_active: edit.is_active };
        void action.run(() => api.patch(endpoint(`/sites/${siteId}/${edit.kind}/${edit.id}`), body), "Đã cập nhật cấu hình bãi.", () => { setEdit(null); void inventory.reload(); });
      }}><DialogTitle>{edit.kind === "zones" ? "Sửa khu vực" : "Sửa vị trí đỗ"}</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
        {action.error && <Alert severity="error">{action.error}</Alert>}
        <TextField autoFocus required label={edit.kind === "zones" ? "Tên khu vực" : "Mã vị trí"} value={edit.name ?? edit.slot_name} disabled={action.busy} onChange={(event) => setEdit({ ...edit, [edit.kind === "zones" ? "name" : "slot_name"]: event.target.value })} slotProps={{ htmlInput: { maxLength: 50 } }} />
        {edit.kind === "zones" ? <TextField required type="number" label="Sức chứa tối đa" value={edit.capacity} disabled={action.busy} onChange={(event) => setEdit({ ...edit, capacity: event.target.value })} slotProps={{ htmlInput: { min: 0, max: 10000, step: 1 } }} /> : <>
          <TextField select label="Khu vực" value={edit.zone_id} disabled={action.busy} onChange={(event) => setEdit({ ...edit, zone_id: event.target.value })}>{zones.map((row) => <MenuItem key={row.id} value={row.id}>{row.name}</MenuItem>)}</TextField>
          <TextField select label="Loại xe" value={edit.vehicle_type_id} disabled={action.busy} onChange={(event) => setEdit({ ...edit, vehicle_type_id: event.target.value })}>{types.map((row) => <MenuItem key={row.id} value={row.id}>{row.name}</MenuItem>)}</TextField>
        </>}
        <FormControlLabel label="Cho phép sử dụng" control={<Checkbox checked={edit.is_active} disabled={action.busy} onChange={(event) => setEdit({ ...edit, is_active: event.target.checked })} />} />
      </Stack></DialogContent><DialogActions><Button disabled={action.busy} onClick={() => setEdit(null)}>Quay lại</Button><Button type="submit" disabled={action.busy} variant="contained">Lưu thay đổi</Button></DialogActions></Box>}
    </Dialog>
  </Stack>;
}
