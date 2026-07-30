import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Avatar,
  Snackbar,
  Alert,
} from "@mui/material";
import LocalParkingIcon from "@mui/icons-material/LocalParking";
import authService from "../services/authService";

export default function LoginPage() {
  const navigate = useNavigate();

  // Form State
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  // UI State
  const [loading, setLoading] = useState(false);
  
  // Snackbar State
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const handleCloseSnackbar = (event, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setOpenSnackbar(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault(); 

    // Basic validate tránh gọi API thừa
    if (!username.trim() || !password) {
      setErrorMessage("Vui lòng nhập đầy đủ Username và Password!");
      setOpenSnackbar(true);
      return;
    }

    setLoading(true);
    setOpenSnackbar(false); // Ẩn lỗi cũ nếu có

    try {
      await authService.login(username, password);
      // Đăng nhập thành công -> Điều hướng về dashboard
      navigate("/dashboard", { replace: true });
    } catch (error) {
      // Đăng nhập thất bại -> Hiển thị Snackbar đỏ
      const errorMsg =
        error.response?.data?.detail ||
        "Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin!";
      setErrorMessage(errorMsg);
      setOpenSnackbar(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "#f4f6f8",
        p: 2,
      }}
    >
      <Card sx={{ maxWidth: 420, width: "100%", boxShadow: 3, borderRadius: 2 }}>
        <CardContent sx={{ p: 4, display: "flex", flexDirection: "column", alignItems: "center" }}>
          
          <Avatar sx={{ m: 1, bgcolor: "primary.main", width: 56, height: 56 }}>
            <LocalParkingIcon fontSize="large" />
          </Avatar>

          <Typography component="h1" variant="h5" sx={{ fontWeight: 600, mb: 3 }}>
            Parking Management System
          </Typography>

          <Box component="form" onSubmit={handleSubmit} sx={{ width: "100%" }}>
            <TextField
              margin="normal"
              required
              fullWidth
              id="username"
              label="Username"
              name="username"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading} // Disable khi đang login
            />
            
            <TextField
              margin="normal"
              required
              fullWidth
              name="password"
              label="Password"
              type="password"
              id="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading} // Disable khi đang login
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={loading} // Disable nút khi đang login
              sx={{ mt: 3, mb: 2, py: 1.5 }}
            >
              {loading ? "Loading..." : "Đăng nhập"}
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* Snackbar hiển thị lỗi */}
      <Snackbar 
        open={openSnackbar} 
        autoHideDuration={6000} 
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }} // Hiển thị ở góc trên bên phải
      >
        <Alert 
          onClose={handleCloseSnackbar} 
          severity="error" 
          variant="filled" // Dùng variant filled để Alert có màu đỏ rực (chuẩn Material Design)
          sx={{ width: '100%' }}
        >
          {errorMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
}