import { useContext } from "react";
import { Alert, Box, Button, Card, CardContent, Chip, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { AuthContext } from "../../context/AuthContext";

const roleLabels = {
  customer: "Khách hàng",
  staff: "Nhân viên",
  manager: "Quản lý",
  admin: "Quản trị viên",
};

export default function AccountPage() {
  const { user } = useContext(AuthContext);

  return (
    <Box sx={{ maxWidth: 640, mx: "auto", mt: 4 }}>
      <Card>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={2}>
            <Typography variant="h5" fontWeight={700}>Tài khoản của tôi</Typography>
            <Typography><strong>Họ và tên:</strong> {user?.full_name || "Chưa cập nhật"}</Typography>
            <Typography><strong>Tên đăng nhập:</strong> {user?.username}</Typography>
            <Typography component="div">
              <strong>Vai trò:</strong>{" "}
              <Chip size="small" color="primary" label={roleLabels[user?.role] || user?.role} />
            </Typography>
            {user?.role === "customer" && (
              <Alert severity="success">
                Tài khoản khách hàng đã hoạt động. Các chức năng vận hành và quản trị được giới hạn cho nhân viên có thẩm quyền.
              </Alert>
            )}
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ pt: 1 }}>
              <Button component={RouterLink} to="/profile" variant="contained">Sửa hồ sơ</Button>
              <Button component={RouterLink} to="/settings" variant="outlined">Cài đặt</Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
