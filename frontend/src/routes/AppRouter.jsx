import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from '../layouts/MainLayout';
import LoginPage from '../pages/LoginPage';
import RegisterPage from '../pages/RegisterPage';
import DashboardPage from '../pages/DashboardPage';
import ParkingSlotPage from '../pages/ParkingSlotPage';
import VehicleTypePage from '../pages/VehicleTypePage';
import VehiclesPage from '../pages/Vehicles/VehiclesPage';
import CustomerPage from '../pages/CustomerPage';
import MonthlyPassPage from '../pages/MonthlyPassPage';
import ParkingSessionPage from '../pages/ParkingSessionPage';
import ReportsPage from '../pages/ReportsPage';
import AIAssistantPage from '../pages/AIAssistantPage';
import UsersPage from '../pages/Users/UsersPage';
import RolesPage from '../pages/Roles/RolesPage';

// Import thêm các trang bị thiếu
import ZonesPage from '../pages/Zones/ZonesPage';
import PriceConfigsPage from '../pages/PriceConfigs/PriceConfigsPage';

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        
        {/* Đã sửa lại tên path cho khớp với link trong Sidebar */}
        <Route path="zones" element={<ZonesPage />} />
        <Route path="parking-slots" element={<ParkingSlotPage />} />
        <Route path="parking-sessions" element={<ParkingSessionPage />} />
        <Route path="price-configs" element={<PriceConfigsPage />} />
        
        <Route path="vehicle-types" element={<VehicleTypePage />} />
        <Route path="vehicles" element={<VehiclesPage />} />
        <Route path="customers" element={<CustomerPage />} />
        <Route path="monthly-passes" element={<MonthlyPassPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="ai" element={<AIAssistantPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="roles" element={<RolesPage />} />
      </Route>
    </Routes>
  );
}