import { Routes, Route, Navigate } from "react-router-dom";
import { lazy, Suspense } from "react";
import { Box, CircularProgress } from "@mui/material";

import MainLayout from "../layouts/MainLayout";
import PrivateRoute from "./PrivateRoute";
import PermissionRoute from "./PermissionRoute";

// --- Pages ---
const Dashboard = lazy(() => import("../pages/Dashboard/DashboardPage"));
const LoginPage = lazy(() => import("../pages/Login/LoginPage"));
const RegisterPage = lazy(() => import("../pages/Register/RegisterPage"));
const AccountPage = lazy(() => import("../pages/Account/AccountPage"));
const ProfilePage = lazy(() => import("../pages/Profile/ProfilePage"));
const SettingsPage = lazy(() => import("../pages/Setting/SettingPage"));
const NotFoundPage = lazy(() => import("../pages/NotFound/NotFoundPage"));

// Các module quản lý (Sprints 3-7)
const CustomerPage = lazy(() => import("../pages/Customer/CustomerPage"));
const VehiclePage = lazy(() => import("../pages/Vehicle/VehiclePage"));
const SessionPage = lazy(() => import("../pages/ParkingSession/ParkingSessionPage"));
const MonthlyPassPage = lazy(() => import("../pages/MonthlyPass/MonthlyPassPage"));
const UserPage = lazy(() => import("../pages/User/UserPage"));
const ZonePage = lazy(() => import("../pages/Zone/ZonePage"));
const ParkingSlotPage = lazy(() => import("../pages/ParkingSlot/ParkingSlotPage"));
const VehicleTypePage = lazy(() => import("../pages/VehicleType/VehicleTypePage"));
const PriceConfigPage = lazy(() => import("../pages/PriceConfig/PriceConfigPage"));
const RolePage = lazy(() => import("../pages/Role/RolePage"));
const ReportPage = lazy(() => import("../pages/Report/ReportPage"));
const AuditLogPage = lazy(() => import("../pages/AuditLog/AuditLogPage"));

const AppRoutes = () => {
  return (
    <Suspense fallback={<Box sx={{ display: "flex", justifyContent: "center", p: 6 }}><CircularProgress /></Box>}>
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Private (Yêu cầu đăng nhập & bọc MainLayout) */}
      <Route
        element={
          <PrivateRoute>
            <MainLayout />
          </PrivateRoute>
        }
      >
        {/* Dashboard */}
        <Route index element={<PermissionRoute minimumRole="staff"><Dashboard /></PermissionRoute>} />
        <Route path="account" element={<AccountPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />

        {/* Parking Sessions (Phiên đỗ xe) */}
        <Route
          path="sessions"
          element={
            <PermissionRoute minimumRole="staff">
              <SessionPage />
            </PermissionRoute>
          }
        />
        <Route path="parking-sessions" element={<Navigate to="/sessions" replace />} />

        {/* Customer (Khách hàng) */}
        <Route
          path="customers"
          element={
            <PermissionRoute minimumRole="staff">
              <CustomerPage />
            </PermissionRoute>
          }
        />

        {/* Vehicle (Phương tiện) */}
        <Route
          path="vehicles"
          element={
            <PermissionRoute minimumRole="staff">
              <VehiclePage />
            </PermissionRoute>
          }
        />

        {/* Monthly Passes (Vé tháng) */}
        <Route
          path="monthly-passes"
          element={
            <PermissionRoute minimumRole="staff">
              <MonthlyPassPage />
            </PermissionRoute>
          }
        />

        {/* Users (Quản lý tài khoản) */}
        <Route
          path="users"
          element={
            <PermissionRoute minimumRole="manager">
              <UserPage />
            </PermissionRoute>
          }
        />
        <Route path="zones" element={<PermissionRoute minimumRole="staff"><ZonePage /></PermissionRoute>} />
        <Route path="parking-slots" element={<PermissionRoute minimumRole="staff"><ParkingSlotPage /></PermissionRoute>} />
        <Route path="vehicle-types" element={<PermissionRoute minimumRole="staff"><VehicleTypePage /></PermissionRoute>} />
        <Route path="price-configs" element={<PermissionRoute minimumRole="staff"><PriceConfigPage /></PermissionRoute>} />
        <Route path="reports" element={<PermissionRoute minimumRole="staff"><ReportPage /></PermissionRoute>} />
        <Route path="audit-logs" element={<PermissionRoute minimumRole="manager"><AuditLogPage /></PermissionRoute>} />
        <Route path="ai" element={<Navigate to="/" replace />} />
        <Route path="roles" element={<PermissionRoute minimumRole="admin"><RolePage /></PermissionRoute>} />
      </Route>

      {/* Redirect */}
      <Route
        path="/home"
        element={<Navigate to="/" replace />}
      />

      {/* 404 */}
      <Route
        path="*"
        element={<NotFoundPage />}
      />
    </Routes>
    </Suspense>
  );
};

export default AppRoutes;
