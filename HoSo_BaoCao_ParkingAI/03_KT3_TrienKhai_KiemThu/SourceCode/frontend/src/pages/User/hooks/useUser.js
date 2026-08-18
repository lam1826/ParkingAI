import { useState, useEffect, useCallback } from "react";
import userService from "../services/userService";

const useUser = () => {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [notify, setNotify] = useState({ open: false, message: "", severity: "info" });

  // Đọc thông tin user hiện tại & phân quyền
  const currentUser = JSON.parse(localStorage.getItem("user")) || { role: "staff" };
  const canManage = currentUser.role === "admin" || currentUser.is_superuser;

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const [uRes, rRes] = await Promise.all([
        userService.getAllUsers(),
        userService.getRoles ? userService.getRoles() : Promise.resolve({ data: [] }) // Dự phòng nếu chưa có API getRoles
      ]);
      
      const userData = uRes.data || uRes;
      setUsers(Array.isArray(userData) ? userData : []);
      
      const roleData = rRes.data || rRes;
      setRoles(Array.isArray(roleData) ? roleData : []);
    } catch (err) {
      console.error(err);
      setUsers([]);
      showNotify("Không thể tải danh sách người dùng", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleActionRestricted = () => {
    showNotify("Bạn không có quyền thực hiện thao tác này! Yêu cầu quyền Admin.", "warning");
  };

  const handleOpenCreate = () => {
    if (!canManage) return handleActionRestricted();
    setSelectedUser(null);
    setDialogOpen(true);
  };

  const handleOpenEdit = (user) => {
    if (!canManage) return handleActionRestricted();
    setSelectedUser(user);
    setDialogOpen(true);
  };

  const handleOpenDelete = (user) => {
    if (!canManage) return handleActionRestricted();
    setSelectedUser(user);
    setDeleteDialogOpen(true);
  };

  const closeDialogs = () => {
    setDialogOpen(false);
    setDeleteDialogOpen(false);
    setSelectedUser(null);
  };

  const handleSave = async (formData) => {
    setSubmitting(true);
    try {
      if (selectedUser) {
        await userService.update(selectedUser.id, formData);
        showNotify("Cập nhật thông tin thành công!", "success");
      } else {
        await userService.create(formData);
        showNotify("Tạo tài khoản thành công!", "success");
      }
      closeDialogs();
      fetchUsers();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || "Lưu người dùng thất bại!";
      showNotify(`Lỗi: ${typeof errorMsg === 'object' ? JSON.stringify(errorMsg) : errorMsg}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    try {
      await userService.delete(selectedUser.id);
      showNotify("Xóa người dùng thành công!", "success");
      closeDialogs();
      fetchUsers();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || "Xóa người dùng thất bại!";
      showNotify(`Lỗi: ${typeof errorMsg === 'object' ? JSON.stringify(errorMsg) : errorMsg}`, "error");
    }
  };

  const showNotify = (message, severity = "info") => setNotify({ open: true, message, severity });
  const closeNotify = () => setNotify((prev) => ({ ...prev, open: false }));

  return {
    users, roles, loading, submitting, canManage,
    dialogOpen, deleteDialogOpen, selectedUser, notify,
    handleOpenCreate, handleOpenEdit, handleOpenDelete,
    closeDialogs, handleSave, handleDelete, fetchUsers, closeNotify
  };
};

export default useUser;