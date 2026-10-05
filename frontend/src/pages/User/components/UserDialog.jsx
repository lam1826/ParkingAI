import { useState, useEffect } from "react";
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField, Grid, MenuItem, CircularProgress, FormControlLabel, Switch } from "@mui/material";
import { autoSelectedRoleId, defaultAssignmentSiteId, siteAssignmentRole } from "../accountAssignment";
import { singleSiteId } from "../../../utils/singleSiteMode";

function configuredSiteId() {
  try { return singleSiteId(); } catch { return null; }
}

const initialForm = {
  username: "",
  password: "", // Chỉ dùng khi tạo mới
  full_name: "",
  role_id: "",
  is_active: true,
};

const NO_SITES = [];

const UserDialog = ({ inline = false, isOpen, onClose, onSave, user, roles, sites = NO_SITES, submitting }) => {
  const [form, setForm] = useState(initialForm);
  const selectedRole = roles.find((role) => String(role.id) === String(form.role_id));
  // Only an Admin receives the lot list; a Manager's staff join the managed lot.
  const assignsSite = !user && sites.length > 0 && Boolean(siteAssignmentRole(selectedRole?.name));
  // Untouched choice follows the lot list as it loads; an explicit choice (even "") wins.
  const siteValue = form.site_id ?? defaultAssignmentSiteId(sites, configuredSiteId());
  // Admin sees every role; without "staff" a new employee cannot be created.
  const staffRoleMissing = !user && roles.some((role) => String(role.name).toLowerCase() === "admin")
    && !roles.some((role) => String(role.name).toLowerCase() === "staff");

  useEffect(() => {
    if (user) {
      setForm({
        username: user.username || "",
        password: "", // Ẩn password khi edit
        full_name: user.full_name || "",
        role_id: user.role_id || user.role?.id || "",
        is_active: user.is_active !== undefined ? user.is_active : true,
      });
    } else {
      setForm({ ...initialForm, role_id: autoSelectedRoleId(roles) });
    }
  }, [user, isOpen, roles]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (submitting) return;
    const submitData = { ...form };
    // Nếu là edit và không nhập mật khẩu mới, xóa trường password đi
    if (user && !submitData.password) {
      delete submitData.password;
    }
    if (assignsSite) submitData.site_id = siteValue;
    else delete submitData.site_id;
    submitData.role_id = Number(submitData.role_id);
    onSave(submitData);
  };

  if (inline) return isOpen ? <section className="surface core-editor" aria-labelledby="account-form-title">
    <div className="section-head"><h2 id="account-form-title">{user ? "Sửa tài khoản" : "Thêm tài khoản"}</h2></div>
    <form className="form-grid" onSubmit={handleSubmit}>
      <label className="field">Họ và tên<input autoFocus name="full_name" required value={form.full_name} disabled={submitting} onChange={handleChange} autoComplete="off" /></label>
      <label className="field">Tên đăng nhập<input name="username" required value={form.username} disabled={Boolean(user) || submitting} onChange={handleChange} autoComplete="off" /></label>
      <label className="field">Vai trò<select name="role_id" required value={form.role_id} disabled={Boolean(autoSelectedRoleId(roles)) || submitting} onChange={handleChange}><option value="">Chọn vai trò</option>{roles.map(role => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label>
      {staffRoleMissing && <p className="inline-note warning core-wide" role="status">Chưa có vai trò nhân viên (staff). Khôi phục vai trò chuẩn ở trang Vai trò trước khi tạo tài khoản nhân viên.</p>}
      {assignsSite && <label className="field">Bãi phân công<select name="site_id" value={siteValue} disabled={submitting} onChange={handleChange}>
        {sites.length > 1 && <option value="">Chưa phân công (cấp sau ở Cấu hình bãi)</option>}
        {sites.map(site => <option key={site.id} value={String(site.id)}>{site.name}</option>)}
      </select></label>}
      <label className="field">{user ? "Mật khẩu mới (để trống nếu không đổi)" : "Mật khẩu"}<input type="password" name="password" required={!user} value={form.password} disabled={submitting} onChange={handleChange} autoComplete="new-password" /></label>
      <label className="checkbox-field"><input type="checkbox" name="is_active" checked={form.is_active} disabled={submitting} onChange={handleChange} /><span>Tài khoản hoạt động</span></label>
      <div className="form-actions core-wide"><button className="button primary" disabled={submitting}>{submitting ? "Đang lưu…" : user ? "Lưu thay đổi" : "Tạo tài khoản"}</button><button type="button" className="button secondary" disabled={submitting} onClick={onClose}>Hủy</button></div>
    </form>
  </section> : null;

  return (
    <Dialog open={isOpen} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight="bold">
        {user ? "Cập nhật Tài khoản" : "Tạo mới Tài khoản"}
      </DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth required size="small"
                label="Tên đăng nhập"
                name="username"
                disabled={!!user} // Không cho đổi username khi edit
                value={form.username}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth size="small" type="password"
                label={user ? "Mật khẩu mới (Để trống nếu không đổi)" : "Mật khẩu"}
                name="password"
                required={!user}
                value={form.password}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth required size="small"
                label="Họ và tên"
                name="full_name"
                value={form.full_name}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth select required size="small"
                label="Vai trò"
                name="role_id"
                disabled={Boolean(autoSelectedRoleId(roles)) || submitting}
                value={form.role_id}
                onChange={handleChange}
              >
                {roles.map((r) => (
                  <MenuItem key={r.id} value={r.id}>{r.name}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={form.is_active}
                    onChange={handleChange}
                    name="is_active"
                    color="primary"
                  />
                }
                label="Trạng thái Hoạt động"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} variant="outlined" disabled={submitting}>Hủy</Button>
          <Button
            type="submit" variant="contained" disabled={submitting}
            startIcon={submitting && <CircularProgress size={18} color="inherit" />}
          >
            {user ? "Lưu thay đổi" : "Tạo tài khoản"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default UserDialog;
