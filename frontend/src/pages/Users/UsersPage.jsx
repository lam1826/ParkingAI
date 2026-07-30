import React, { useState, useEffect } from 'react';
import userService from '../../services/userService';
import UserTable from './components/UserTable';
import UserDialog from './components/UserDialog';
import DeleteDialog from './components/DeleteDialog';

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);

  const currentUser = JSON.parse(localStorage.getItem('user')) || { role: 'staff' };
  const canManage = currentUser.role === 'admin' || currentUser.is_superuser;

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await userService.getAll();
      
      // Lấy dữ liệu và kiểm tra xem có phải là mảng không
      const data = res.data || res;
      setUsers(Array.isArray(data) ? data : []); 
      
    } catch (err) {
      console.error(err);
      setUsers([]); // Đảm bảo lỗi API cũng trả về mảng rỗng
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleActionRestricted = () => {
    alert('Bạn không có quyền thực hiện thao tác này! Yêu cầu quyền Admin.');
  };

  const handleOpenCreate = () => {
    if (!canManage) return handleActionRestricted();
    setSelectedUser(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (user) => {
    if (!canManage) return handleActionRestricted();
    setSelectedUser(user);
    setIsDialogOpen(true);
  };

  const handleOpenDelete = (user) => {
    if (!canManage) return handleActionRestricted();
    setSelectedUser(user);
    setIsDeleteDialogOpen(true);
  };

  const handleSave = async (formData) => {
    try {
      if (selectedUser) {
        await userService.update(selectedUser.id, formData);
      } else {
        await userService.create(formData);
      }
      setIsDialogOpen(false);
      fetchUsers();
    } catch (err) {
      alert('Lưu người dùng thất bại!');
    }
  };

  const handleDelete = async () => {
    try {
      await userService.delete(selectedUser.id);
      setIsDeleteDialogOpen(false);
      fetchUsers();
    } catch (err) {
      alert('Xóa người dùng thất bại!');
    }
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Quản lý Người dùng</h1>
        {canManage && (
          <button
            onClick={handleOpenCreate}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            + Thêm người dùng
          </button>
        )}
      </div>

      {!canManage && (
        <div className="mb-4 p-3 bg-yellow-100 text-yellow-800 rounded-lg">
          Lưu ý: Bạn đang đăng nhập với quyền hạn hạn chế. Các chức năng Thêm/Sửa/Xóa bị vô hiệu hóa.
        </div>
      )}

      <UserTable
        users={users}
        loading={loading}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
        canManage={canManage}
      />

      {isDialogOpen && (
        <UserDialog
          isOpen={isDialogOpen}
          onClose={() => setIsDialogOpen(false)}
          onSave={handleSave}
          user={selectedUser}
        />
      )}

      {isDeleteDialogOpen && (
        <DeleteDialog
          isOpen={isDeleteDialogOpen}
          onClose={() => setIsDeleteDialogOpen(false)}
          onConfirm={handleDelete}
          title="Xóa người dùng"
          message={`Bạn có chắc muốn xóa tài khoản ${selectedUser?.username}?`}
        />
      )}
    </div>
  );
}