import { useState, useEffect, useCallback } from "react";
import monthlyPassService from "../services/monthlyPassService";
import vehicleService from "../../Vehicle/services/vehicleService";
import customerService from "../../Customer/services/customerService";

const useMonthlyPass = () => {
  const [passes, setPasses] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [customers, setCustomers] = useState([]);
  
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [deactivateDialogOpen, setDeactivateDialogOpen] = useState(false);
  const [selectedPass, setSelectedPass] = useState(null);

  const [notify, setNotify] = useState({ open: false, message: "", severity: "info" });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // Tải song song danh sách vé tháng, xe và khách hàng để làm dữ liệu cho Form
      const [pRes, vRes, cRes] = await Promise.all([
        monthlyPassService.getAll(),
        vehicleService.getAllVehicles(),
        customerService.getAllCustomers()
      ]);
      
      setPasses(pRes.data || pRes || []);
      setVehicles(vRes.data || vRes || []);
      
      // customerService.getCustomers trả về phân trang ở Sprint 4, ta lấy data.items hoặc tương đương
      setCustomers(cRes.data || cRes.items || cRes || []); 
    } catch {
      showNotify("Lỗi tải dữ liệu vé tháng!", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleOpenCreate = () => {
    setSelectedPass(null);
    setDialogOpen(true);
  };

  const handleOpenEdit = (pass) => {
    setSelectedPass(pass);
    setDialogOpen(true);
  };

  const handleOpenDeactivate = (pass) => {
    setSelectedPass(pass);
    setDeactivateDialogOpen(true);
  };

  const closeDialogs = () => {
    setDialogOpen(false);
    setDeactivateDialogOpen(false);
    setSelectedPass(null);
  };

  const handleSave = async (formData) => {
    setSubmitting(true);
    try {
      if (selectedPass) {
        await monthlyPassService.update(selectedPass.id, formData);
        showNotify("Cập nhật vé tháng thành công!", "success");
      } else {
        await monthlyPassService.create(formData);
        showNotify("Đăng ký vé tháng thành công!", "success");
      }
      closeDialogs();
      fetchData();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || "Lưu vé tháng thất bại!";
      showNotify(`Lỗi: ${typeof errorMsg === 'object' ? JSON.stringify(errorMsg) : errorMsg}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    try {
      await monthlyPassService.deactivate(selectedPass.id);
      showNotify("Hủy vé tháng thành công!", "success");
      closeDialogs();
      fetchData();
    } catch {
      showNotify("Lỗi khi hủy vé tháng", "error");
    }
  };

  const showNotify = (message, severity = "info") => setNotify({ open: true, message, severity });
  const closeNotify = () => setNotify((prev) => ({ ...prev, open: false }));

  return {
    passes, vehicles, customers, loading, submitting,
    dialogOpen, deactivateDialogOpen, selectedPass, notify,
    handleOpenCreate, handleOpenEdit, handleOpenDeactivate,
    closeDialogs, handleSave, handleDeactivate, fetchData, closeNotify
  };
};

export default useMonthlyPass;
