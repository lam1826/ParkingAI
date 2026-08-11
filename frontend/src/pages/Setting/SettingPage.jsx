import { useContext, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import LockIcon from "@mui/icons-material/Lock";
import LogoutIcon from "@mui/icons-material/Logout";
import { AuthContext } from "../../context/AuthContext";
import authService from "../../services/authService";
import PasswordField from "../../components/common/PasswordField";

const initialPasswords = {
  current_password: "",
  new_password: "",
  confirm_password: "",
};

export default function SettingPage() {
  const { logout } = useContext(AuthContext);
  const [passwords, setPasswords] = useState(initialPasswords);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);
  const [localNotice, setLocalNotice] = useState("");

  const handleChange = (event) => {
    const { name, value } = event.target;
    setPasswords((current) => ({ ...current, [name]: value }));
  };

  const handlePasswordSubmit = async (event) => {
    event.preventDefault();
    setNotice(null);
    if (passwords.new_password !== passwords.confirm_password) {
      setNotice({ severity: "error", message: "Mật khẩu xác nhận không khớp." });
      return;
    }

    setSaving(true);
    try {
      const result = await authService.changePassword({
        current_password: passwords.current_password,
        new_password: passwords.new_password,
      });
      setPasswords(initialPasswords);
      setNotice({ severity: "success", message: result.message || "Đổi mật khẩu thành công." });
    } catch (error) {
      const detail = error.response?.data?.detail;
      setNotice({ severity: "error", message: typeof detail === "string" ? detail : "Không thể đổi mật khẩu." });
    } finally {
      setSaving(false);
    }
  };

  const clearAIHistory = () => {
    sessionStorage.removeItem("parking_ai_chat_messages");
    window.dispatchEvent(new Event("parking-ai-clear-chat"));
    setLocalNotice("Đã xóa lịch sử chatbot trong phiên này.");
  };

  return (
    <Box sx={{ maxWidth: 760, mx: "auto", py: 3 }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Cài đặt</Typography>
          <Typography color="text.secondary">Quản lý bảo mật và dữ liệu được lưu trên thiết bị này.</Typography>
        </Box>

        <Card sx={{ borderRadius: 3 }}>
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 3 }}>
              <LockIcon color="primary" />
              <Box>
                <Typography variant="h6" fontWeight={700}>Đổi mật khẩu</Typography>
                <Typography variant="body2" color="text.secondary">Mật khẩu mới phải có ít nhất 8 ký tự.</Typography>
              </Box>
            </Stack>

            {notice && <Alert severity={notice.severity} sx={{ mb: 2 }}>{notice.message}</Alert>}

            <Box component="form" onSubmit={handlePasswordSubmit}>
              <Stack spacing={2.5}>
                <PasswordField
                  required fullWidth label="Mật khẩu hiện tại" name="current_password"
                  value={passwords.current_password} onChange={handleChange} autoComplete="current-password"
                />
                <PasswordField
                  required fullWidth label="Mật khẩu mới" name="new_password"
                  value={passwords.new_password} onChange={handleChange} autoComplete="new-password"
                  inputProps={{ minLength: 8, maxLength: 72 }}
                />
                <PasswordField
                  required fullWidth label="Xác nhận mật khẩu mới" name="confirm_password"
                  value={passwords.confirm_password} onChange={handleChange} autoComplete="new-password"
                />
                <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
                  <Button type="submit" variant="contained" disabled={saving} sx={{ minWidth: 150 }}>
                    {saving ? <CircularProgress size={22} color="inherit" /> : "Đổi mật khẩu"}
                  </Button>
                </Box>
              </Stack>
            </Box>
          </CardContent>
        </Card>

        <Card sx={{ borderRadius: 3 }}>
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Typography variant="h6" fontWeight={700}>Dữ liệu trên thiết bị</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Lịch sử chatbot chỉ được lưu trong phiên trình duyệt hiện tại.
            </Typography>
            {localNotice && <Alert severity="success" sx={{ mb: 2 }}>{localNotice}</Alert>}
            <Button variant="outlined" color="error" startIcon={<DeleteIcon />} onClick={clearAIHistory}>
              Xóa lịch sử chatbot
            </Button>

            <Divider sx={{ my: 3 }} />

            <Typography variant="h6" fontWeight={700}>Phiên đăng nhập</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Đăng xuất và xóa thông tin đăng nhập khỏi thiết bị này.
            </Typography>
            <Button variant="outlined" color="error" startIcon={<LogoutIcon />} onClick={logout}>
              Đăng xuất
            </Button>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
