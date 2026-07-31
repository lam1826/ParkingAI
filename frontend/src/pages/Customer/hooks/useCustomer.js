import { useState, useEffect, useCallback } from "react";
import customerService from "../services/customerService";

const initialFilters = {
  keyword: "", // Tìm theo tên, SĐT hoặc email
};

const useCustomer = () => {
  const [customers, setCustomers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Phân trang & bộ lọc
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [filters, setFilters] = useState(initialFilters);

  // Trạng thái Modal (Thêm / Sửa)
  const [modal, setModal] = useState({
    open: false,
    mode: "create", // 'create' | 'edit'
    data: null,
  });

  // Trạng thái Snackbar
  const [notify, setNotify] = useState({ open: false, message: "", severity: "info" });

  const fetchCustomers = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page: page + 1,
        limit: pageSize,
        keyword: filters.keyword || undefined,
      };

      const res = await customerService.getCustomers(params);
      setCustomers(res.data || res.items || res || []);
      setTotal(res.total || res.totalItems || (res.data ? res.data.length : 0));
    } catch (err) {
      console.error("Lỗi khi lấy danh sách khách hàng:", err);
      showNotify("Không thể tải danh sách khách hàng", "error");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filters]);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

  // Quản lý Modal
  const openCreateModal = () => {
    setModal({ open: true, mode: "create", data: null });
  };

  const openEditModal = (customer) => {
    setModal({ open: true, mode: "edit", data: customer });
  };

  const closeModal = () => {
    setModal({ open: false, mode: "create", data: null });
  };

  // Submit Form (Thêm mới hoặc Cập nhật)
  const handleSubmit = async (formData) => {
    setSubmitting(true);
    try {
      if (modal.mode === "create") {
        await customerService.createCustomer(formData);
        showNotify("Thêm khách hàng thành công!", "success");
      } else {
        await customerService.updateCustomer(modal.data.id, formData);
        showNotify("Cập nhật thông tin thành công!", "success");
      }
      closeModal();
      fetchCustomers();
    } catch (err) {
      showNotify(err.response?.data?.detail || "Lưu thông tin thất bại", "error");
    } finally {
      setSubmitting(false);
    }
  };

  // Xóa Khách hàng
  const handleDelete = async (id) => {
    try {
      await customerService.deleteCustomer(id);
      showNotify("Xóa khách hàng thành công!", "success");
      fetchCustomers();
    } catch (err) {
      showNotify(err.response?.data?.detail || "Lỗi khi xóa khách hàng", "error");
    }
  };

  // Notification Helpers
  const showNotify = (message, severity = "info") => {
    setNotify({ open: true, message, severity });
  };

  const closeNotify = () => {
    setNotify((prev) => ({ ...prev, open: false }));
  };

  return {
    customers,
    total,
    loading,
    submitting,
    page,
    pageSize,
    filters,
    modal,
    notify,
    setPage,
    setPageSize,
    setFilters,
    openCreateModal,
    openEditModal,
    closeModal,
    handleSubmit,
    handleDelete,
    fetchCustomers,
    closeNotify,
  };
};

export default useCustomer;