import {
  AppBar,
  Toolbar,
  Typography,
  Box,
  Avatar,
  IconButton,
  Tooltip,
  useTheme,
  useMediaQuery,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import LogoutIcon from "@mui/icons-material/Logout";
import { useNavigate } from "react-router-dom";

// Khớp với kích thước Sidebar đã tạo trước đó
const drawerWidth = 280;

export default function Header() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const navigate = useNavigate();

  // Mock data (Không gọi API theo yêu cầu)
  const currentUser = {
    name: "Quản trị viên",
    role: "Admin System",
    avatar: "https://i.pravatar.cc/150?u=admin",
  };

  const handleLogout = () => {
    // Xử lý logic clear token/session ở đây nếu cần trong tương lai
    navigate("/login");
  };

  return (
    <AppBar
      position="fixed"
      sx={{
        width: { sm: `calc(100% - ${drawerWidth}px)` },
        ml: { sm: `${drawerWidth}px` },
        backgroundColor: "background.paper", // Màu nền trắng sáng từ Theme
        color: "text.primary",
        boxShadow: 1, // Shadow nhẹ cho Header
      }}
    >
      <Toolbar>
        {/* Nút Menu Hamburger chỉ hiển thị trên màn hình nhỏ (Mobile/Tablet) */}
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          sx={{ mr: 2, display: { sm: "none" } }}
        >
          <MenuIcon />
        </IconButton>

        {/* Spacer để đẩy các phần tử về phía bên phải */}
        <Box sx={{ flexGrow: 1 }} />

        {/* Thông tin User & Nút Logout */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          {/* Ẩn Tên & Role trên Mobile để tiết kiệm diện tích */}
          {!isMobile && (
            <Box sx={{ textAlign: "right" }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                {currentUser.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {currentUser.role}
              </Typography>
            </Box>
          )}

          <Avatar 
            alt={currentUser.name} 
            src={currentUser.avatar} 
            sx={{ width: 40, height: 40, border: '1px solid #e0e0e0' }}
          />

          <Tooltip title="Đăng xuất">
            <IconButton 
              onClick={handleLogout} 
              sx={{ 
                color: "error.main",
                "&:hover": { backgroundColor: "error.light", color: "white" } 
              }}
            >
              <LogoutIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Toolbar>
    </AppBar>
  );
}