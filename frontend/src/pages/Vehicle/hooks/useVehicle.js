import { useState, useEffect, useCallback } from "react";
import vehicleService from "../services/vehicleService";

const useVehicle = () => {
  const [vehicles, setVehicles] = useState([]);
  const [vehicleTypes, setVehicleTypes] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Modal States
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState(null);

  // Snackbar Notification
  const [notify, setNotify] = useState({ open: false, message: "", severity: "info" });

  const showNotify = (message, severity = "info") => {
    setNotify({ open: true, message, severity });
  };

  const closeNotify = () => {
    setNotify((prev) => ({ ...prev, open: false }));
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [vRes, vtRes, cRes] = await Promise.all([
        vehicleService.getAllVehicles(),
        vehicleService.getVehicleTypes(),
        vehicleService.getCustomers(),
      ]);
      setVehicles(vRes.data || vRes || []);
      setVehicleTypes(vtRes.data || vtRes || []);
      setCustomers(cRes.data || cRes || []);
    } catch {
      showNotify("Không thể tải dữ liệu. Vui lòng kiểm tra kết nối!", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handlers mở modal
  const handleOpenCreate = () => {
    setSelectedVehicle(null);
    setDialogOpen(true);
  };

  const handleOpenEdit = (vehicle) => {
    setSelectedVehicle(vehicle);
    setDialogOpen(true);
  };

  const handleOpenDelete = (vehicle) => {
    setSelectedVehicle(vehicle);
    setDeleteDialogOpen(true);
  };

  const closeDialogs = () => {
    setDialogOpen(false);
    setDeleteDialogOpen(false);
    setSelectedVehicle(null);
  };

  // Logic Lưu (Create / Update)
  const handleSave = async (formData) => {
    setSubmitting(true);
    try {
      if (selectedVehicle) {
        await vehicleService.update(selectedVehicle.id, formData);
        showNotify("Cập nhật phương tiện thành công!", "success");
      } else {
        await vehicleService.create(formData);
        showNotify("Thêm phương tiện thành công!", "success");
      }
      closeDialogs();
      fetchData();
    } catch (err) {
      // Giữ nguyên logic parse lỗi 422 chi tiết của bạn
      const errorDetail = err.response?.data?.detail;
      const errorMsg =
        typeof errorDetail === "object"
          ? JSON.stringify(errorDetail)
          : errorDetail || err.message || "Lưu phương tiện thất bại!";
      showNotify(`Lỗi: ${errorMsg}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  // Logic Xóa
  const handleDelete = async () => {
    try {
      await vehicleService.delete(selectedVehicle.id);
      showNotify("Xóa phương tiện thành công!", "success");
      closeDialogs();
      fetchData();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || "Xóa phương tiện thất bại!";
      showNotify(`Lỗi: ${errorMsg}`, "error");
    }
  };

  return {
    vehicles,
    vehicleTypes,
    customers,
    loading,
    submitting,
    dialogOpen,
    deleteDialogOpen,
    selectedVehicle,
    notify,
    handleOpenCreate,
    handleOpenEdit,
    handleOpenDelete,
    closeDialogs,
    handleSave,
    handleDelete,
    fetchData,
    closeNotify,
  };
};

export default useVehicle;
