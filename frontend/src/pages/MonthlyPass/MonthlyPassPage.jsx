import { Box, Typography, Stack, Snackbar, Alert, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

import MonthlyPassTable from "./components/MonthlyPassTable";
import MonthlyPassDialog from "./components/MonthlyPassDialog";
import useMonthlyPass from "./hooks/useMonthlyPass";

const MonthlyPassPage = () => {
  const {
    passes, vehicles, customers, loading, submitting,
    dialogOpen, deleteDialogOpen, selectedPass, notify,
    handleOpenCreate, handleOpenEdit, handleOpenDelete,
    closeDialogs, handleSave, handleDelete, fetchData, closeNotify
  } = useMonthlyPass();

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5" fontWeight="bold" color="text.primary">
          Quản lý Vé tháng
        </Typography>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={fetchData} disabled={loading}>
          Làm mới
        </Button>
      </Stack>

      <MonthlyPassTable
        passes={passes}
        loading={loading}
        onAdd={handleOpenCreate}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
      />

      <MonthlyPassDialog
        isOpen={dialogOpen}
        onClose={closeDialogs}
        onSave={handleSave}
        pass={selectedPass}
        vehicles={vehicles}
        customers={customers}
        submitting={submitting}
      />

      <Dialog open={deleteDialogOpen} onClose={closeDialogs}>
        <DialogTitle fontWeight="bold">Xác nhận hủy vé</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Bạn có chắc chắn muốn hủy vé tháng có mã thẻ <strong>{selectedPass?.pass_code}</strong> không?
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={closeDialogs} variant="outlined">Quay lại</Button>
          <Button onClick={handleDelete} color="error" variant="contained">Xác nhận Hủy</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={notify.open} autoHideDuration={5000} onClose={closeNotify} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
        <Alert severity={notify.severity} variant="filled" onClose={closeNotify} sx={{ width: "100%" }}>
          {notify.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default MonthlyPassPage;