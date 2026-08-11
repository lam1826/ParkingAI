import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Container,
  MenuItem,
  Paper,
  TextField,
  Typography,
} from "@mui/material";
import authService from "../../services/authService";
import PasswordField from "../../components/common/PasswordField";

const initialForm = {
  username: "",
  full_name: "",
  password: "",
  confirm_password: "",
  role: "customer",
  registration_code: "",
};

const roleOptions = [
  { value: "customer", label: "Khách hàng" },
  { value: "manager", label: "Quản lý" },
  { value: "admin", label: "Quản trị viên" },
];

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");

    if (form.password !== form.confirm_password) {
      setError("Mật khẩu xác nhận không khớp");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        username: form.username.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        role: form.role,
        registration_code: form.role === "customer" ? null : form.registration_code,
      };
      await authService.register(payload);
      navigate("/login", {
        replace: true,
        state: { message: "Đăng ký thành công. Bạn có thể đăng nhập ngay." },
      });
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Không thể đăng ký tài khoản");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", bgcolor: "#f5f7fb", py: 4 }}>
      <Container maxWidth="sm">
        <Paper elevation={3} sx={{ p: { xs: 3, sm: 4 }, borderRadius: 2 }}>
          <Typography variant="h5" fontWeight={700} textAlign="center" gutterBottom>
            Đăng ký tài khoản ParkingAI
          </Typography>
          <Typography color="text.secondary" textAlign="center" sx={{ mb: 2 }}>
            Tài khoản quản lý và quản trị viên cần mã đăng ký do hệ thống cấp.
          </Typography>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <Box component="form" onSubmit={handleSubmit}>
            <TextField
              fullWidth required margin="normal" name="full_name" label="Họ và tên"
              value={form.full_name} onChange={handleChange} inputProps={{ minLength: 2, maxLength: 100 }}
            />
            <TextField
              fullWidth required margin="normal" name="username" label="Tên đăng nhập"
              value={form.username} onChange={handleChange} inputProps={{ minLength: 3, maxLength: 50 }}
              helperText="Chỉ dùng chữ cái không dấu, số và các ký tự . _ -"
            />
            <TextField
              fullWidth select required margin="normal" name="role" label="Loại tài khoản"
              value={form.role} onChange={handleChange}
            >
              {roleOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
              ))}
            </TextField>
            {form.role !== "customer" && (
              <PasswordField
                fullWidth required margin="normal" name="registration_code"
                label="Mã đăng ký dành cho vai trò" value={form.registration_code} onChange={handleChange}
              />
            )}
            <PasswordField
              fullWidth required margin="normal" name="password" label="Mật khẩu"
              value={form.password} onChange={handleChange} inputProps={{ minLength: 8, maxLength: 72 }}
              helperText="Từ 8 đến 72 ký tự"
            />
            <PasswordField
              fullWidth required margin="normal" name="confirm_password" label="Xác nhận mật khẩu"
              value={form.confirm_password} onChange={handleChange}
            />
            <Button type="submit" fullWidth variant="contained" disabled={loading} sx={{ mt: 3, py: 1.4 }}>
              {loading ? <CircularProgress size={24} color="inherit" /> : "Đăng ký"}
            </Button>
            <Button component={RouterLink} to="/login" fullWidth sx={{ mt: 1 }}>
              Đã có tài khoản? Đăng nhập
            </Button>
          </Box>
        </Paper>
      </Container>
    </Box>
  );
}
