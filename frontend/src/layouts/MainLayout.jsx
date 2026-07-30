import { Box, Toolbar } from "@mui/material";
import { Outlet } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import Header from "../components/Header";

// Giữ nguyên kích thước 280px để đồng bộ với Sidebar và Header
const drawerWidth = 280;

export default function MainLayout() {
  return (
    <Box sx={{ display: "flex", minHeight: "100vh", backgroundColor: "#f4f6f8" }}>
      {/* Header cố định ở trên cùng */}
      <Header />

      {/* Sidebar cố định bên trái */}
      <Sidebar />

      {/* Phần nội dung chính (bên phải Sidebar, dưới Header) */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3, // Padding cho nội dung
          width: { sm: `calc(100% - ${drawerWidth}px)` }, // Responsive width
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Spacer: Đẩy nội dung xuống một khoảng bằng chính chiều cao của Header */}
        <Toolbar /> 
        
        {/* React Router sẽ render các Page (Dashboard, Zone, v.v.) tại đây */}
        <Box sx={{ flexGrow: 1 }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}