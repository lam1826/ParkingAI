import { useState, useContext } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  List,
  Typography,
  Divider,
  IconButton,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
} from "@mui/material";

// Import Icons
import MenuIcon from "@mui/icons-material/Menu";
import DashboardIcon from "@mui/icons-material/Dashboard";
import LocalParkingIcon from "@mui/icons-material/LocalParking";
import DirectionsCarIcon from "@mui/icons-material/DirectionsCar";
import CardMembershipIcon from "@mui/icons-material/CardMembership";
import PeopleIcon from "@mui/icons-material/People";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import DomainIcon from "@mui/icons-material/Domain";
import CategoryIcon from "@mui/icons-material/Category";
import PriceChangeIcon from "@mui/icons-material/PriceChange";
import AssessmentIcon from "@mui/icons-material/Assessment";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import HistoryIcon from "@mui/icons-material/History";
import SmartToyIcon from "@mui/icons-material/SmartToy";

import { AuthContext } from "../context/AuthContext";
import AIChatbot from "../components/ai/AIChatbot";

const drawerWidth = 260; // Độ rộng của Sidebar

export default function MainLayout() {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();
  
  // State quản lý Menu User góc phải trên
  const [anchorEl, setAnchorEl] = useState(null);

  // Danh sách các menu trong Sidebar
  const menuItems = [
    { text: "Tài khoản của tôi", icon: <AccountCircleIcon />, path: "/account" },
    { text: "Dashboard", icon: <DashboardIcon />, path: "/", role: "staff" },
    { text: "Phiên Đỗ Xe", icon: <LocalParkingIcon />, path: "/sessions", role: "staff" },
    { text: "Khu vực", icon: <DomainIcon />, path: "/zones", role: "staff" },
    { text: "Vị trí đỗ", icon: <LocalParkingIcon />, path: "/parking-slots", role: "staff" },
    { text: "Loại xe", icon: <CategoryIcon />, path: "/vehicle-types", role: "staff" },
    { text: "Phương tiện", icon: <DirectionsCarIcon />, path: "/vehicles", role: "staff" },
    { text: "Khách hàng", icon: <PeopleIcon />, path: "/customers", role: "staff" },
    { text: "Vé Tháng", icon: <CardMembershipIcon />, path: "/monthly-passes", role: "staff" },
    { text: "Bảng giá", icon: <PriceChangeIcon />, path: "/price-configs", role: "staff" },
    { text: "Báo cáo", icon: <AssessmentIcon />, path: "/reports", role: "staff" },
    { text: "AI Analytics", icon: <SmartToyIcon />, path: "/ai", role: "staff" },
    { text: "Tài Khoản", icon: <PeopleIcon />, path: "/users", role: "manager" },
    { text: "Nhật ký hoạt động", icon: <HistoryIcon />, path: "/audit-logs", role: "manager" },
    { text: "Vai trò", icon: <AdminPanelSettingsIcon />, path: "/roles", role: "admin" },
  ];

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = () => {
    handleMenuClose();
    logout();
  };

  const handleNavigate = (path) => {
    handleMenuClose();
    navigate(path);
  };

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", backgroundColor: "#f5f7fb" }}>
      {/* 1. HEADER (AppBar) */}
      <AppBar 
        position="fixed" 
        sx={{ 
          zIndex: (theme) => theme.zIndex.drawer + 1,
          backgroundColor: "#1976d2" // Màu xanh chủ đạo của MUI, có thể đổi theo theme
        }}
      >
        <Toolbar>
          <IconButton color="inherit" edge="start" sx={{ mr: 2 }}>
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
            ParkingAI Enterprise
          </Typography>

          {/* Góc phải User Profile */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body1">
              Xin chào, {user?.username || "Admin"}
            </Typography>
            <IconButton color="inherit" onClick={handleMenuOpen}>
              <AccountCircleIcon fontSize="large" />
            </IconButton>
            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={handleMenuClose}
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            >
              <MenuItem onClick={() => handleNavigate("/profile")}>Hồ sơ cá nhân</MenuItem>
              <MenuItem onClick={() => handleNavigate("/settings")}>Cài đặt</MenuItem>
              <Divider />
              <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
                Đăng xuất
              </MenuItem>
            </Menu>
          </Box>
        </Toolbar>
      </AppBar>

      {/* 2. SIDEBAR (Drawer) */}
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: "border-box" },
        }}
      >
        <Toolbar /> {/* Khối Toolbar trống này để đẩy danh sách menu xuống dưới Header */}
        <Box sx={{ overflow: "auto", mt: 2 }}>
          <List>
            {menuItems.map((item) => {
              // Ẩn menu nếu có yêu cầu role mà user không thỏa mãn (ví dụ giả lập)
              const roleLevel = { customer: 0, staff: 1, manager: 2, admin: 3 };
              if (item.role && (roleLevel[String(user?.role).toLowerCase()] || 0) < roleLevel[item.role]) return null;

              const isSelected = location.pathname === item.path || (location.pathname.startsWith(item.path) && item.path !== '/');

              return (
                <ListItem key={item.text} disablePadding sx={{ mb: 1, px: 2 }}>
                  <ListItemButton
                    selected={isSelected}
                    onClick={() => navigate(item.path)}
                    sx={{
                      borderRadius: 2,
                      "&.Mui-selected": {
                        backgroundColor: "primary.main",
                        color: "white",
                        "&:hover": { backgroundColor: "primary.dark" },
                        "& .MuiListItemIcon-root": { color: "white" }
                      }
                    }}
                  >
                    <ListItemIcon sx={{ color: isSelected ? "white" : "inherit", minWidth: 40 }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.text}
                      slotProps={{ primary: { fontWeight: isSelected ? 'bold' : 'normal' } }}
                    />
                  </ListItemButton>
                </ListItem>
              );
            })}
          </List>
        </Box>
      </Drawer>

      {/* 3. MAIN CONTENT (Nội dung chính) */}
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar /> {/* Để đẩy nội dung xuống dưới Header */}
        
        {/* ĐÂY LÀ NƠI CÁC TRANG (Dashboard, Users,...) SẼ ĐƯỢC RENDER VÀO */}
        <Outlet /> 
      </Box>
      {(["staff", "manager", "admin"].includes(String(user?.role).toLowerCase())) && <AIChatbot />}
    </Box>
  );
}
