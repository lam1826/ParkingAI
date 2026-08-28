import { useContext, useEffect, useState } from "react";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import PersonIcon from "@mui/icons-material/Person";
import { AuthContext } from "../../context/AuthContext";
import authService from "../../services/authService";

const roleLabels = {
  customer: "Khách hàng",
  staff: "Nhân viên",
  manager: "Quản lý",
  admin: "Quản trị viên",
};

export default function ProfilePage() {
  const { user, refreshUser } = useContext(AuthContext);
  const [form, setForm] = useState({ username: "", full_name: "" });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    setForm({ username: user?.username || "", full_name: user?.full_name || "" });
  }, [user]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      await authService.updateProfile({
        username: form.username.trim(),
        full_name: form.full_name.trim(),
      });
      await refreshUser();
      setNotice({ severity: "success", message: "Cập nhật hồ sơ thành công." });
    } catch (error) {
      const detail = error.response?.data?.detail;
      setNotice({ severity: "error", message: typeof detail === "string" ? detail : "Không thể cập nhật hồ sơ." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 760, mx: "auto", py: 3 }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Hồ sơ cá nhân</Typography>
          <Typography color="text.secondary">Cập nhật thông tin hiển thị của tài khoản.</Typography>
        </Box>

        <Card sx={{ borderRadius: 3 }}>
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={3}
              sx={{ alignItems: { xs: "flex-start", sm: "center" }, mb: 3 }}
            >
              <Avatar sx={{ width: 72, height: 72, bgcolor: "primary.main" }}><PersonIcon fontSize="large" /></Avatar>
              <Box>
                <Typography variant="h6" fontWeight={700}>{user?.full_name || user?.username}</Typography>
                <Chip size="small" color="primary" variant="outlined" label={roleLabels[user?.role] || user?.role} />
              </Box>
            </Stack>

            {notice && <Alert severity={notice.severity} sx={{ mb: 2 }}>{notice.message}</Alert>}

            <Box component="form" onSubmit={handleSubmit}>
              <Stack spacing={2.5}>
                <TextField
                  required fullWidth label="Họ và tên" name="full_name"
                  value={form.full_name} onChange={handleChange} inputProps={{ minLength: 2, maxLength: 100 }}
                />
                <TextField
                  required fullWidth label="Tên đăng nhập" name="username"
                  value={form.username} onChange={handleChange} inputProps={{ minLength: 3, maxLength: 50 }}
                  helperText="Chỉ sử dụng chữ cái không dấu, số và các ký tự . _ -"
                />
                <TextField fullWidth label="Vai trò" value={roleLabels[user?.role] || user?.role || ""} disabled />
                <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
                  <Button type="submit" variant="contained" disabled={saving} sx={{ minWidth: 150 }}>
                    {saving ? <CircularProgress size={22} color="inherit" /> : "Lưu thay đổi"}
                  </Button>
                </Box>
              </Stack>
            </Box>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
