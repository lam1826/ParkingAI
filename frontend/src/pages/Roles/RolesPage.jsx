import React, { useState, useEffect } from 'react';
import roleService from '../../services/roleService';
import RoleTable from './components/RoleTable';
import RoleDialog from './components/RoleDialog';
import DeleteDialog from './components/DeleteDialog';

export default function RolesPage() {
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState(null);

  const currentUser = JSON.parse(localStorage.getItem('user')) || { role: 'staff' };
  const canManage = currentUser.role === 'admin' || currentUser.is_superuser;

  const fetchRoles = async () => {
    setLoading(true);
    try {
      const res = await roleService.getAll();
      setRoles(res.data || res);
    } catch (err) {
      console.error('Lỗi khi tải vai trò:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRoles();
  }, []);

  const handleActionRestricted = () => {
    alert('Bạn không có quyền thực hiện thao tác này! Yêu cầu quyền Admin.');
  };

  const handleOpenCreate = () => {
    if (!canManage) return handleActionRestricted();
    setSelectedRole(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (role) => {
    if (!canManage) return handleActionRestricted();
    setSelectedRole(role);
    setIsDialogOpen(true);
  };

  const handleOpenDelete = (role) => {
    if (!canManage) return handleActionRestricted();
    setSelectedRole(role);
    setIsDeleteDialogOpen(true);
  };

  const handleSave = async (formData) => {
    try {
      if (selectedRole) {
        await roleService.update(selectedRole.id, formData);
      } else {
        await roleService.create(formData);
      }
      setIsDialogOpen(false);
      fetchRoles();
    } catch (err) {
      alert('Lưu vai trò thất bại!');
    }
  };

  const handleDelete = async () => {
    try {
      await roleService.delete(selectedRole.id);
      setIsDeleteDialogOpen(false);
      fetchRoles();
    } catch (err) {
      alert('Xóa vai trò thất bại!');
    }
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Quản lý Vai trò</h1>
        {canManage && (
          <button
            onClick={handleOpenCreate}
            className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 transition"
          >
            + Thêm Vai trò
          </button>
        )}
      </div>

      {!canManage && (
        <div className="mb-4 p-3 bg-yellow-100 text-yellow-800 rounded-lg">
          Lưu ý: Chức năng chỉnh sửa vai trò đã bị khóa do bạn không có quyền Admin.
        </div>
      )}

      <RoleTable
        roles={roles}
        loading={loading}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
        canManage={canManage}
      />

      {isDialogOpen && (
        <RoleDialog
          isOpen={isDialogOpen}
          onClose={() => setIsDialogOpen(false)}
          onSave={handleSave}
          role={selectedRole}
        />
      )}

      {isDeleteDialogOpen && (
        <DeleteDialog
          isOpen={isDeleteDialogOpen}
          onClose={() => setIsDeleteDialogOpen(false)}
          onConfirm={handleDelete}
          title="Xóa Vai trò"
          message={`Bạn có chắc muốn xóa vai trò ${selectedRole?.name}?`}
        />
      )}
    </div>
  );
}