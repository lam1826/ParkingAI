import { Box, Typography, Stack, Snackbar, Alert, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

import VehicleTable from "./components/VehicleTable";
import VehicleDialog from "./components/VehicleDialog";
import useVehicle from "./hooks/useVehicle";

export default function VehiclesPage() {
  const {
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
  } = useVehicle();

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5" fontWeight="bold" color="text.primary">
          Quản lý Phương tiện
        </Typography>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={fetchData}
          disabled={loading}
        >
          Làm mới
        </Button>
      </Stack>

      {/* Bảng Dữ liệu */}
      <VehicleTable
        vehicles={vehicles}
        loading={loading}
        onAdd={handleOpenCreate}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
      />

      {/* Modal Thêm/Sửa */}
      <VehicleDialog
        isOpen={dialogOpen}
        onClose={closeDialogs}
        onSave={handleSave}
        vehicle={selectedVehicle}
        vehicleTypes={vehicleTypes}
        customers={customers}
        submitting={submitting}
      />

      {/* Modal Xóa */}
      <Dialog open={deleteDialogOpen} onClose={closeDialogs}>
        <DialogTitle fontWeight="bold">Xóa phương tiện</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Bạn có chắc muốn xóa phương tiện <strong>{selectedVehicle?.license_plate}</strong>? Thao tác này không thể hoàn tác.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={closeDialogs} variant="outlined">
            Hủy
          </Button>
          <Button onClick={handleDelete} color="error" variant="contained">
            Xác nhận Xóa
          </Button>
        </DialogActions>
      </Dialog>

      {/* Thông báo Snackbar */}
      <Snackbar
        open={notify.open}
        autoHideDuration={5000}
        onClose={closeNotify}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert severity={notify.severity} variant="filled" onClose={closeNotify} sx={{ width: "100%" }}>
          {notify.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}