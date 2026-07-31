import { useState, useEffect } from "react";
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField, Grid, MenuItem, CircularProgress, FormControlLabel, Switch } from "@mui/material";

const initialForm = {
  username: "",
  password: "", // Chỉ dùng khi tạo mới
  full_name: "",
  email: "",
  role_id: "",
  is_active: true,
};

const UserDialog = ({ isOpen, onClose, onSave, user, roles, submitting }) => {
  const [form, setForm] = useState(initialForm);

  useEffect(() => {
    if (user) {
      setForm({
        username: user.username || "",
        password: "", // Ẩn password khi edit
        full_name: user.full_name || "",
        email: user.email || "",
        role_id: user.role_id || user.role?.id || "",
        is_active: user.is_active !== undefined ? user.is_active : true,
      });
    } else {
      setForm(initialForm);
    }
  }, [user, isOpen]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const submitData = { ...form };
    // Nếu là edit và không nhập mật khẩu mới, xóa trường password đi
    if (user && !submitData.password) {
      delete submitData.password;
    }
    onSave(submitData);
  };

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
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth size="small" type="email"
                label="Email"
                name="email"
                value={form.email}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth select required size="small"
                label="Vai trò (Role)"
                name="role_id"
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