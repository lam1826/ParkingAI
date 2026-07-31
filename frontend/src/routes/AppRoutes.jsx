import { Routes, Route, Navigate } from "react-router-dom";

import MainLayout from "../layouts/MainLayout";
import PrivateRoute from "./PrivateRoute";
import PermissionRoute from "./PermissionRoute";

// --- Pages ---
import Dashboard from "../pages/Dashboard/DashboardPage";
import LoginPage from "../pages/Login/LoginPage";
import NotFoundPage from "../pages/NotFound/NotFoundPage";

// Các module quản lý (Sprints 3-7)
import CustomerPage from "../pages/Customer/CustomerPage";
import VehiclePage from "../pages/Vehicle/VehiclePage";
import SessionPage from "../pages/ParkingSession/ParkingSessionPage";
import MonthlyPassPage from "../pages/MonthlyPass/MonthlyPassPage";
import UserPage from "../pages/User/UserPage";

const AppRoutes = () => {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />

      {/* Private (Yêu cầu đăng nhập & bọc MainLayout) */}
      <Route
        element={
          <PrivateRoute>
            <MainLayout />
          </PrivateRoute>
        }
      >
        {/* Dashboard */}
        <Route index element={<Dashboard />} />

        {/* Parking Sessions (Phiên đỗ xe) */}
        <Route
          path="sessions"
          element={
            <PermissionRoute permission="session:view">
              <SessionPage />
            </PermissionRoute>
          }
        />

        {/* Customer (Khách hàng) */}
        <Route
          path="customers"
          element={
            <PermissionRoute permission="customer:view">
              <CustomerPage />
            </PermissionRoute>
          }
        />

        {/* Vehicle (Phương tiện) */}
        <Route
          path="vehicles"
          element={
            <PermissionRoute permission="vehicle:view">
              <VehiclePage />
            </PermissionRoute>
          }
        />

        {/* Monthly Passes (Vé tháng) */}
        <Route
          path="monthly-passes"
          element={
            <PermissionRoute permission="monthlypass:view">
              <MonthlyPassPage />
            </PermissionRoute>
          }
        />

        {/* Users (Quản lý tài khoản) */}
        <Route
          path="users"
          element={
            <PermissionRoute permission="user:view">
              <UserPage />
            </PermissionRoute>
          }
        />
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
  );
};

export default AppRoutes;