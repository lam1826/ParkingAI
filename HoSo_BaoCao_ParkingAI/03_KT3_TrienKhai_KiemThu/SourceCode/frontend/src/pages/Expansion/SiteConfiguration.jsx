import { useState } from "react";
import { Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { endpoint, formLayout, Records, Section, send } from "./shared";

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
      <Records rows={zones} columns={[{ key: "id", label: "Mã khu" }, { key: "name", label: "Tên khu vực" }, { key: "capacity", label: "Sức chứa" }, { key: "is_active", label: "Hoạt động", render: (row) => row.is_active ? "Có" : "Không" }]} />
    </Section>
    <Section title="Thêm vị trí đỗ" description="Chỗ mới chưa có xe. Trạng thái có xe chỉ thay đổi qua thao tác xe vào/ra.">
      <Box component="form" sx={formLayout} onSubmit={(event) => {
        event.preventDefault();
        void action.run(() => send(`/sites/${siteId}/slots`, { slot_name: slot.slot_name.trim(), zone_id: Number(slot.zone_id), vehicle_type_id: Number(slot.vehicle_type_id) }), "Đã tạo vị trí đỗ.", () => setSlot((old) => ({ ...old, slot_name: "" })));
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
  </Stack>;
}
