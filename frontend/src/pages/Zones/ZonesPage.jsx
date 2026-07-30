import React, { useState, useEffect } from "react";
import { Box, Typography, Snackbar, Alert } from "@mui/material";
import zoneService from "../../services/zoneService";
import ZoneTable from "./components/ZoneTable";
import ZoneDialog from "./components/ZoneDialog";
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

export default function ZonesPage() {
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(true);

  // Dialog states
  const [openFormDialog, setOpenFormDialog] = useState(false);
  const [selectedZone, setSelectedZone] = useState(null);

  const [openDeleteDialog, setOpenDeleteDialog] = useState(false);
  const [zoneToDelete, setZoneToDelete] = useState(null);

  // Snackbar state
  const [snackbar, setSnackbar] = useState({
    open: false,
    message: "",
    severity: "success",
  });

  const fetchZones = async () => {
    try {
      setLoading(true);
      const data = await zoneService.getAll();
      setZones(data);
    } catch (err) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, "Không thể tải danh sách khu vực từ hệ thống."),
        severity: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchZones();
  }, []);

  const handleOpenAdd = () => {
    setSelectedZone(null);
    setOpenFormDialog(true);
  };

  const handleOpenEdit = (zone) => {
    setSelectedZone(zone);
    setOpenFormDialog(true);
  };

  const handleSaveZone = async (formData) => {
    try {
      if (selectedZone) {
        await zoneService.update(selectedZone.id, formData);
        setSnackbar({
          open: true,
          message: "Cập nhật khu vực thành công!",
          severity: "success",
        });
      } else {
        await zoneService.create(formData);
        setSnackbar({
          open: true,
          message: "Thêm khu vực mới thành công!",
          severity: "success",
        });
      }
      setOpenFormDialog(false);
      fetchZones();
    } catch (err) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, "Có lỗi xảy ra khi lưu khu vực."),
        severity: "error",
      });
    }
  };

  const handleOpenDelete = (zone) => {
    setZoneToDelete(zone);
    setOpenDeleteDialog(true);
  };

  const handleConfirmDelete = async () => {
    try {
      await zoneService.delete(zoneToDelete.id);
      setSnackbar({
        open: true,
        message: "Xóa khu vực thành công!",
        severity: "success",
      });
      setOpenDeleteDialog(false);
      fetchZones();
    } catch (err) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, "Không thể xóa khu vực này."),
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
        Quản lý khu vực bãi đỗ
      </Typography>

      <ZoneTable
        data={zones}
        loading={loading}
        onAdd={handleOpenAdd}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
      />

      <ZoneDialog
        open={openFormDialog}
        onClose={() => setOpenFormDialog(false)}
        onSave={handleSaveZone}
        zone={selectedZone}
      />

      <DeleteDialog
        open={openDeleteDialog}
        onClose={() => setOpenDeleteDialog(false)}
        onConfirm={handleConfirmDelete}
        zoneName={zoneToDelete?.name}
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