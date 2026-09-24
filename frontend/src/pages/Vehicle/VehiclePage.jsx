import { Box, Snackbar, Alert, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { PageHeader, WorkspaceTabs } from "../../components/common/PrototypeUI";

import VehicleTable from "./components/VehicleTable";
import VehicleDialog from "./components/VehicleDialog";
import useVehicle from "./hooks/useVehicle";
import useCorePermissions from "../../hooks/useCorePermissions";

export default function VehiclesPage() {
  const { canDeleteCustomerRecords } = useCorePermissions();
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
    <Box>
      <PageHeader title="Khách & vé" description="Hồ sơ khách, phương tiện liên kết và các kỳ vé tháng." actions={<button className="button primary" disabled={loading || submitting} onClick={handleOpenCreate}><AddIcon fontSize="small" /> Thêm phương tiện</button>} />
      <WorkspaceTabs />
      <div className="toolbar" style={{ justifyContent: "flex-end", marginBottom: 12 }}><button className="button quiet small" onClick={fetchData} disabled={loading || submitting}>Làm mới</button></div>

      {/* Bảng Dữ liệu */}
      <VehicleDialog inline
        isOpen={dialogOpen}
        onClose={closeDialogs}
        onSave={handleSave}
        vehicle={selectedVehicle}
        vehicleTypes={vehicleTypes}
        customers={customers}
        submitting={submitting}
      />

      <VehicleTable
        vehicles={vehicles}
        loading={loading}
        onEdit={handleOpenEdit}
        onDelete={canDeleteCustomerRecords ? handleOpenDelete : undefined}
      />

      {/* Modal Thêm/Sửa */}


      {/* Modal Xóa */}
      <Dialog open={deleteDialogOpen && canDeleteCustomerRecords} onClose={closeDialogs}>
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
