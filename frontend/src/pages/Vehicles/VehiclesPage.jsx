import React, { useState, useEffect } from 'react';
import vehicleService from '../../services/vehicleService';
import vehicleTypeService from '../../services/vehicleTypeService';
import customerService from '../../services/customerService';
import VehicleTable from './components/VehicleTable';
import VehicleDialog from './components/VehicleDialog';
import DeleteDialog from './components/DeleteDialog';

export default function VehiclesPage() {
  const [vehicles, setVehicles] = useState([]);
  const [vehicleTypes, setVehicleTypes] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [vRes, vtRes, cRes] = await Promise.all([
        vehicleService.getAll(),
        vehicleTypeService.getAll(),
        customerService.getAll()
      ]);
      setVehicles(vRes.data || vRes);
      setVehicleTypes(vtRes.data || vtRes);
      setCustomers(cRes.data || cRes);
    } catch (err) {
      setError('Không thể tải dữ liệu phương tiện.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleOpenCreate = () => {
    setSelectedVehicle(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (vehicle) => {
    setSelectedVehicle(vehicle);
    setIsDialogOpen(true);
  };

  const handleOpenDelete = (vehicle) => {
    setSelectedVehicle(vehicle);
    setIsDeleteDialogOpen(true);
  };

  const handleSave = async (formData) => {
    try {
      if (selectedVehicle) {
        await vehicleService.update(selectedVehicle.id, formData);
      } else {
        await vehicleService.create(formData);
      }
      setIsDialogOpen(false);
      fetchData();
    } catch (err) {
      // In chi tiết lỗi từ backend ra thông báo để dễ dàng kiểm tra nếu có lỗi dữ liệu 422
      const errorDetail = err.response?.data?.detail;
      const errorMsg = typeof errorDetail === 'object' 
        ? JSON.stringify(errorDetail) 
        : (errorDetail || err.message || 'Lưu phương tiện thất bại!');
      alert(`Lỗi: ${errorMsg}`);
    }
  };

  const handleDelete = async () => {
    try {
      await vehicleService.delete(selectedVehicle.id);
      setIsDeleteDialogOpen(false);
      fetchData();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Xóa phương tiện thất bại!';
      alert(`Lỗi: ${errorMsg}`);
    }
  };

  return (
    <div className="p-6">
      {/* Đã xóa nút thừa ở header, chỉ giữ lại tiêu đề sạch sẽ */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Quản lý Phương tiện</h1>
      </div>

      {error && <div className="mb-4 text-red-500">{error}</div>}

      <VehicleTable
        vehicles={vehicles}
        loading={loading}
        onAdd={handleOpenCreate}     //{/* Truyền hàm mở modal thêm mới vào bảng */}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
      />

      {isDialogOpen && (
        <VehicleDialog
          isOpen={isDialogOpen}
          onClose={() => setIsDialogOpen(false)}
          onSave={handleSave}
          vehicle={selectedVehicle}
          vehicleTypes={vehicleTypes}
          customers={customers}
        />
      )}

      {isDeleteDialogOpen && (
        <DeleteDialog
          isOpen={isDeleteDialogOpen}
          onClose={() => setIsDeleteDialogOpen(false)}
          onConfirm={handleDelete}
          title="Xóa phương tiện"
          message={`Bạn có chắc muốn xóa phương tiện ${selectedVehicle?.license_plate}?`}
        />
      )}
    </div>
  );
}