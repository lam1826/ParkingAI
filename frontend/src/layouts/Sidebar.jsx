import { useLocation, useNavigate, Link } from "react-router-dom";
import {
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
  Box,
  Divider,
} from "@mui/material";

// Import Icons
import DashboardIcon from "@mui/icons-material/Dashboard";
import DomainIcon from "@mui/icons-material/Domain";
import LocalParkingIcon from "@mui/icons-material/LocalParking";
import DirectionsCarIcon from "@mui/icons-material/DirectionsCar";
import PeopleIcon from "@mui/icons-material/People";
import ConfirmationNumberIcon from "@mui/icons-material/ConfirmationNumber";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import AssessmentIcon from "@mui/icons-material/Assessment";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import LogoutIcon from "@mui/icons-material/Logout";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import BadgeIcon from "@mui/icons-material/Badge";
import TwoWheelerIcon from "@mui/icons-material/TwoWheeler";
import PriceChangeIcon from "@mui/icons-material/PriceChange";

// Import authService để xử lý logic đăng xuất
import authService from "../services/authService"; 

const drawerWidth = 280;

const menuItems = [
  { title: "Dashboard", path: "/dashboard", icon: <DashboardIcon /> },
  { title: "Quản lý khu vực", path: "/zones", icon: <DomainIcon /> },
  { title: "Vị trí đỗ", path: "/parking-slots", icon: <LocalParkingIcon /> },
  { title: "Loại xe", path: "/vehicle-types", icon: <DirectionsCarIcon /> },
  { title: "Khách hàng", path: "/customers", icon: <PeopleIcon /> },
  { title: "Vé tháng", path: "/monthly-passes", icon: <ConfirmationNumberIcon /> },
  { title: "Xe vào/ra", path: "/parking-sessions", icon: <SwapHorizIcon /> },
  { title: "Báo cáo", path: "/reports", icon: <AssessmentIcon /> },
  { title: "AI Assistant", path: "/ai", icon: <AutoAwesomeIcon /> },
  { title: "Phương tiện", path: "/vehicles", icon: <TwoWheelerIcon /> },
  { title: "Bảng giá", path: "/price-configs", icon: <PriceChangeIcon /> },
  { title: "Người dùng", path: "/users", icon: <BadgeIcon /> },
  { title: "Vai trò", path: "/roles", icon: <AdminPanelSettingsIcon /> },
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  // Hàm xử lý Đăng xuất
  const handleLogout = () => {
    authService.logout();
    navigate("/login", { replace: true });
  };

  return (
    <Drawer
      variant="permanent"
      anchor="left"
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          width: drawerWidth,
          boxSizing: "border-box",
          backgroundColor: "#f8f9fa",
          borderRight: "1px solid #e0e0e0",
        },
      }}
    >
      {/* Sidebar Header / Tên hệ thống */}
      <Box sx={{ p: 3, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Typography
          variant="h6"
          component="div"
          sx={{
            fontWeight: "bold",
            color: "#1976d2",
            textAlign: "center",
            lineHeight: 1.3,
          }}
        >
          Parking Management <br /> System
        </Typography>
      </Box>

      <Divider />

      {/* Danh sách Menu */}
      <Box sx={{ overflow: "auto", flexGrow: 1 }}>
        <List sx={{ px: 2 }}>
          {menuItems.map((item) => {
            const isActive = location.pathname === item.path;

            return (
              <ListItem key={item.title} disablePadding sx={{ mb: 1 }}>
                <ListItemButton
                  component={Link}
                  to={item.path}
                  selected={isActive}
                  sx={{
                    borderRadius: 2,
                    "&.Mui-selected": {
                      backgroundColor: "primary.main",
                      color: "primary.contrastText",
                      "&:hover": {
                        backgroundColor: "primary.dark",
                      },
                      "& .MuiListItemIcon-root": {
                        color: "primary.contrastText",
                      },
                    },
                  }}
                >
                  <ListItemIcon
                    sx={{
                      minWidth: 40,
                      color: isActive ? "inherit" : "text.secondary",
                    }}
                  >
                    {item.icon}
                  </ListItemIcon>
                  <ListItemText 
                    disableTypography
                    primary={
                      <Typography sx={{ fontWeight: isActive ? 600 : 400 }}>
                        {item.title}
                      </Typography>
                    }
                  />
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      </Box>

      <Divider />

      {/* Menu Đăng xuất đặt ở dưới cùng */}
      <List sx={{ px: 2, pb: 2 }}>
        <ListItem disablePadding>
          <ListItemButton
            onClick={handleLogout}
            sx={{
              borderRadius: 2,
              color: "error.main",
              "&:hover": {
                backgroundColor: "error.light",
                color: "error.contrastText",
                "& .MuiListItemIcon-root": {
                  color: "error.contrastText",
                },
              },
            }}
          >
            <ListItemIcon sx={{ minWidth: 40, color: "error.main" }}>
              <LogoutIcon />
            </ListItemIcon>
            <ListItemText 
              disableTypography
              primary={
                <Typography sx={{ fontWeight: 500 }}>
                  Đăng xuất
                </Typography>
              }
            />
          </ListItemButton>
        </ListItem>
      </List>
    </Drawer>
  );
}