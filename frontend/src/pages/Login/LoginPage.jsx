import { useState, useContext } from "react";
import { 
  Box, 
  Container, 
  TextField, 
  Button, 
  Paper, 
  Alert, 
  CircularProgress 
} from "@mui/material";
import { AuthContext } from "../../context/AuthContext";
import { Link as RouterLink } from "react-router-dom";
import { useLocation } from "react-router-dom";
import PasswordField from "../../components/common/PasswordField";
import BrandLogo from "../../components/brand/BrandLogo";

export default function LoginPage() {
  const { login } = useContext(AuthContext);
  const location = useLocation();
  const [formData, setFormData] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (!formData.username || !formData.password) {
      setError("Vui lòng nhập đầy đủ Tên đăng nhập và Mật khẩu");
      setLoading(false);
      return;
    }

    const result = await login(formData);
    
    if (!result.success) {
      setError(result.message);
      setLoading(false);
    }
  };

  return (
    <Box 
      sx={{ 
        height: "100vh", 
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center",
        backgroundColor: "background.default"
      }}
    >
      <Container maxWidth="xs">
        <Paper
          elevation={3}
          sx={{
            p: { xs: 3, sm: 4 },
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            borderRadius: 2,
          }}
        >
          <Box sx={{ mb: 2.5 }}>
            <BrandLogo
              size={56}
              orientation="vertical"
              headingComponent="h1"
              tagline="Đăng nhập hệ thống quản lý bãi đỗ xe"
            />
          </Box>

          {error && (
            <Alert severity="error" sx={{ width: "100%", mb: 2 }}>
              {error}
            </Alert>
          )}
          {location.state?.message && (
            <Alert severity="success" sx={{ width: "100%", mb: 2 }}>
              {location.state.message}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit} sx={{ width: '100%' }}>
            <TextField
              margin="normal"
              required
              fullWidth
              id="username"
              label="Tên đăng nhập"
              name="username"
              autoComplete="username"
              autoFocus
              value={formData.username}
              onChange={handleChange}
            />
            <PasswordField
              margin="normal"
              required
              fullWidth
              name="password"
              label="Mật khẩu"
              id="password"
              autoComplete="current-password"
              value={formData.password}
              onChange={handleChange}
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3, mb: 2, py: 1.5, fontSize: "1rem" }}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : "Đăng Nhập"}
            </Button>
            <Button component={RouterLink} to="/register" fullWidth>
              Chưa có tài khoản? Đăng ký
            </Button>
          </Box>
        </Paper>
      </Container>
    </Box>
  );
}
