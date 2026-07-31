import { useState, useContext } from "react";
import { 
  Box, 
  Container, 
  Typography, 
  TextField, 
  Button, 
  Paper, 
  Alert, 
  CircularProgress 
} from "@mui/material";
import { AuthContext } from "../../context/AuthContext";

export default function LoginPage() {
  const { login } = useContext(AuthContext);
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
        backgroundColor: "#f5f7fb" // Màu nền nhạt, đồng bộ với App
      }}
    >
      <Container maxWidth="xs">
        <Paper elevation={3} sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center', borderRadius: 2 }}>
          <Typography component="h1" variant="h5" fontWeight="bold" sx={{ mb: 3 }}>
            ParkingAI - Đăng Nhập
          </Typography>

          {error && (
            <Alert severity="error" sx={{ width: "100%", mb: 2 }}>
              {error}
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
            <TextField
              margin="normal"
              required
              fullWidth
              name="password"
              label="Mật khẩu"
              type="password"
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
          </Box>
        </Paper>
      </Container>
    </Box>
  );
}