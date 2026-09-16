import { useCallback, useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { Alert, Box, Button, Stack, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { endpoint, formLayout, read, RemoteSection, useRemote } from "./shared";

const EMPTY = { address: "", description: "", opening_hours: "", contact_phone: "", contact_email: "", latitude: "", longitude: "" };

function fromProfile(profile) {
  return { address: profile.address || "", description: profile.description || "", opening_hours: profile.opening_hours || "",
    contact_phone: profile.contact?.phone || "", contact_email: profile.contact?.email || "",
    latitude: profile.location ? String(profile.location.latitude) : "", longitude: profile.location ? String(profile.location.longitude) : "" };
}

// The server validates again; the browser only turns blanks into nulls and numbers into numbers.
export function profileBody(form) {
  const text = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
  const latitude = form.latitude === "" ? null : Number(form.latitude);
  const longitude = form.longitude === "" ? null : Number(form.longitude);
  if ((latitude === null) !== (longitude === null)) throw new Error("Nhập cả vĩ độ và kinh độ, hoặc để trống cả hai.");
  if (latitude !== null && (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180)) throw new Error("Tọa độ không hợp lệ (vĩ độ −90…90, kinh độ −180…180).");
  return { address: (form.address || "").trim(), description: text(form.description), opening_hours: text(form.opening_hours),
    contact_phone: text(form.contact_phone), contact_email: text(form.contact_email), latitude, longitude };
}

/** Manager editor for the public introduction page; staff see the same data read-only. */
export default function PublicProfileForm({ siteId, action }) {
  const load = useCallback(() => read(`/sites/${siteId}/public-profile`), [siteId]);
  const remote = useRemote(load);
  const [form, setForm] = useState(EMPTY);
  const [problem, setProblem] = useState("");
  useEffect(() => { if (remote.data) setForm(fromProfile(remote.data)); }, [remote.data]);
  const change = (name) => (event) => setForm((old) => ({ ...old, [name]: event.target.value }));
  const canEdit = Boolean(remote.data?.can_edit);
  return <RemoteSection remote={remote} title="Trang giới thiệu công khai" description="Thông tin dưới đây hiển thị cho khách chưa đăng nhập tại /gioi-thieu. Ô để trống sẽ hiện “Chưa cập nhật”; không tự điền địa chỉ, giờ hay giá."
    actions={<Button component={RouterLink} to="/gioi-thieu" variant="outlined" target="_blank" rel="noopener">Xem trang công khai</Button>}>
    {(profile) => <Stack spacing={2}>
      {!canEdit && <Alert severity="info">Chỉ quản lý của bãi này mới được cập nhật thông tin công khai; bạn đang xem ở chế độ chỉ đọc.</Alert>}
      <Typography variant="body2" color="text.secondary">Cập nhật lần cuối: {profile.profile_updated_at ? new Date(profile.profile_updated_at).toLocaleString("vi-VN") : "chưa cập nhật"}. Gói vé và giá vãng lai lấy từ mục Gói vé và Bảng giá hiện hành.</Typography>
      <Box component="form" sx={formLayout} onSubmit={(event) => {
        event.preventDefault();
        setProblem("");
        let body;
        try { body = profileBody(form); } catch (error) { setProblem(error.message); return; }
        void action.run(() => api.put(endpoint(`/sites/${siteId}/public-profile`), body), "Đã cập nhật trang giới thiệu.", () => remote.reload());
      }}>
        <TextField label="Địa chỉ" value={form.address} onChange={change("address")} disabled={!canEdit || action.busy} slotProps={{ htmlInput: { maxLength: 250 } }} />
        <TextField label="Giờ mở cửa" value={form.opening_hours} onChange={change("opening_hours")} disabled={!canEdit || action.busy} placeholder="Ví dụ: 06:00–22:00 hằng ngày" slotProps={{ htmlInput: { maxLength: 500 } }} />
        <TextField label="Điện thoại liên hệ" value={form.contact_phone} onChange={change("contact_phone")} disabled={!canEdit || action.busy} slotProps={{ htmlInput: { maxLength: 20, inputMode: "tel" } }} />
        <TextField label="Email liên hệ" type="email" value={form.contact_email} onChange={change("contact_email")} disabled={!canEdit || action.busy} slotProps={{ htmlInput: { maxLength: 100 } }} />
        <TextField label="Vĩ độ" value={form.latitude} onChange={change("latitude")} disabled={!canEdit || action.busy} placeholder="10.7769" slotProps={{ htmlInput: { inputMode: "decimal" } }} helperText="Để trống nếu chưa có tọa độ; chỉ đường sẽ dùng địa chỉ." />
        <TextField label="Kinh độ" value={form.longitude} onChange={change("longitude")} disabled={!canEdit || action.busy} placeholder="106.7009" slotProps={{ htmlInput: { inputMode: "decimal" } }} />
        <TextField label="Mô tả bãi" value={form.description} onChange={change("description")} disabled={!canEdit || action.busy} multiline minRows={3} sx={{ gridColumn: "1 / -1" }} slotProps={{ htmlInput: { maxLength: 2000 } }} />
        {problem && <Alert severity="error" sx={{ gridColumn: "1 / -1" }}>{problem}</Alert>}
        {canEdit && <Button type="submit" variant="contained" disabled={action.busy}>Lưu thông tin công khai</Button>}
      </Box>
    </Stack>}
  </RemoteSection>;
}
