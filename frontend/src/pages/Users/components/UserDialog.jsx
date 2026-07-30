import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  MenuItem,
  FormControlLabel,
  Switch,
} from "@mui/material";

const UserDialog = ({ open, onClose, onSave, user, roles }) => {
  const [formData, setFormData] = useState({
    username: "",
    full_name: "",
    role_id: "",
    is_active: true,
    password: "",
  });

  useEffect(() => {
    if (user) {
      setFormData({
        username: user.username || "",
        full_name: user.full_name || "",
        role_id: user.role_id ?? "",
        is_active: user.is_active ?? true,
        password: "",
      });
    } else {
      setFormData({
        username: "",
        full_name: "",
        role_id: "",
        is_active: true,
        password: "",
      });
    }
  }, [user, open]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const payload = { ...formData, role_id: Number(formData.role_id) };
    // Khi chỉnh sửa, chỉ gửi password nếu người dùng thực sự nhập mật khẩu mới
    if (user && !payload.password) {
      delete payload.password;
    }
    onSave(payload);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle sx={{ fontWeight: "bold" }}>
          {user ? "Chỉnh sửa người dùng" : "Thêm người dùng mới"}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label="Tên đăng nhập"
              name="username"
              value={formData.username}
              onChange={handleChange}
              required
              fullWidth
              autoFocus
              disabled={!!user}
              helperText={user ? "Không thể thay đổi tên đăng nhập" : ""}
            />
            <TextField
              label="Họ và tên"
              name="full_name"
              value={formData.full_name}
              onChange={handleChange}
              required
              fullWidth
            />
            <TextField
              select
              label="Vai trò"
              name="role_id"
              value={formData.role_id}
              onChange={handleChange}
              required
              fullWidth
            >
              {roles.map((role) => (
                <MenuItem key={role.id} value={role.id}>
                  {role.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={user ? "Mật khẩu mới (để trống nếu không đổi)" : "Mật khẩu"}
              name="password"
              type="password"
              value={formData.password}
              onChange={handleChange}
              required={!user}
              fullWidth
            />
            <FormControlLabel
              control={
                <Switch
                  checked={formData.is_active}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, is_active: e.target.checked }))
                  }
                  name="is_active"
                />
              }
              label="Đang hoạt động"
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} color="inherit">
            Hủy
          </Button>
          <Button type="submit" variant="contained">
            {user ? "Cập nhật" : "Thêm mới"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default UserDialog;
