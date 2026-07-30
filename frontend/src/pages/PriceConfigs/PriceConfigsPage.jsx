import React, { useState, useEffect } from "react";
import { Box, Typography, Snackbar, Alert } from "@mui/material";
import priceConfigService from "../../services/priceConfigService";
import vehicleTypeService from "../../services/vehicleTypeService";
import PriceConfigTable from "./components/PriceConfigTable";
import PriceConfigDialog from "./components/PriceConfigDialog";
import DeleteDialog from "./components/DeleteDialog";

// Hàm hỗ trợ bóc tách thông báo lỗi an toàn từ FastAPI (đặc biệt lỗi 422 validation)
const getErrorMessage = (err, defaultMessage) => {
  const detail = err.response?.data?.detail;
  if (!detail) return defaultMessage;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
  }
  if (typeof detail === "object") {
    return detail.msg || JSON.stringify(detail);
  }
  return defaultMessage;
};

export default function PriceConfigsPage() {
  const [priceConfigs, setPriceConfigs] = useState([]);
  const [vehicleTypes, setVehicleTypes] = useState([]);
  const [loading, setLoading] = useState(true);

  const [openFormDialog, setOpenFormDialog] = useState(false);
  const [selectedPriceConfig, setSelectedPriceConfig] = useState(null);

  const [openDeleteDialog, setOpenDeleteDialog] = useState(false);
  const [priceConfigToDelete, setPriceConfigToDelete] = useState(null);

  const [snackbar, setSnackbar] = useState({
    open: false,
    message: "",
    severity: "success",
  });

  const fetchData = async () => {
    try {
      setLoading(true);
      const [pricesRes, typesRes] = await Promise.all([
        priceConfigService.getAll(),
        vehicleTypeService.getAll(),
      ]);
      
      // Bóc tách .data an toàn nếu service trả về axios response
      setPriceConfigs(pricesRes.data || pricesRes);
      setVehicleTypes(typesRes.data || typesRes);
      
    } catch (err) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, "Không thể tải danh sách bảng giá từ hệ thống."),
        severity: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleOpenAdd = () => {
    setSelectedPriceConfig(null);
    setOpenFormDialog(true);
  };

  const handleOpenEdit = (priceConfig) => {
    setSelectedPriceConfig(priceConfig);
    setOpenFormDialog(true);
  };

  const handleSavePriceConfig = async (formData) => {
    try {
      if (selectedPriceConfig) {
        await priceConfigService.update(selectedPriceConfig.id, formData);
        setSnackbar({
          open: true,
          message: "Cập nhật bảng giá thành công!",
          severity: "success",
        });
      } else {
        await priceConfigService.create(formData);
        setSnackbar({
          open: true,
          message: "Thêm bảng giá mới thành công!",
          severity: "success",
        });
      }
      setOpenFormDialog(false);
      fetchData();
    } catch (err) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, "Có lỗi xảy ra khi lưu bảng giá."),
        severity: "error",
      });
    }
  };

  const handleOpenDelete = (priceConfig) => {
    setPriceConfigToDelete(priceConfig);
    setOpenDeleteDialog(true);
  };

  const handleConfirmDelete = async () => {
    try {
      await priceConfigService.delete(priceConfigToDelete.id);
      setSnackbar({
        open: true,
        message: "Xóa bảng giá thành công!",
        severity: "success",
      });
      setOpenDeleteDialog(false);
      fetchData();
    } catch (err) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, "Không thể xóa bảng giá này."),
        severity: "error",
      });
    }
  };

  const handleCloseSnackbar = (event, reason) => {
    if (reason === "clickaway") return;
    setSnackbar((prev) => ({ ...prev, open: false }));
  };

  return (
    <Box sx={{ p: 3, flexGrow: 1 }}>
      <Typography variant="h4" fontWeight="bold" gutterBottom sx={{ mb: 3 }}>
        Quản lý bảng giá
      </Typography>

      <PriceConfigTable
        data={priceConfigs}
        vehicleTypes={vehicleTypes}
        loading={loading}
        onAdd={handleOpenAdd}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
      />

      <PriceConfigDialog
        open={openFormDialog}
        onClose={() => setOpenFormDialog(false)}
        onSave={handleSavePriceConfig}
        priceConfig={selectedPriceConfig}
        vehicleTypes={vehicleTypes}
      />

      <DeleteDialog
        open={openDeleteDialog}
        onClose={() => setOpenDeleteDialog(false)}
        onConfirm={handleConfirmDelete}
        label={priceConfigToDelete?.ticket_type}
      />

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert onClose={handleCloseSnackbar} severity={snackbar.severity} variant="filled" sx={{ width: "100%" }}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
