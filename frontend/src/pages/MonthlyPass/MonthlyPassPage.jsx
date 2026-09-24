import { Box, Snackbar, Alert, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { PageHeader, WorkspaceTabs } from "../../components/common/PrototypeUI";

import MonthlyPassTable from "./components/MonthlyPassTable";
import MonthlyPassDialog from "./components/MonthlyPassDialog";
import useMonthlyPass from "./hooks/useMonthlyPass";
import useCorePermissions from "../../hooks/useCorePermissions";

const MonthlyPassPage = () => {
  const { canManageMonthlyPasses } = useCorePermissions();
  const {
    passes, vehicles, customers, loading, submitting,
    dialogOpen, deactivateDialogOpen, selectedPass, notify,
    handleOpenCreate, handleOpenEdit, handleOpenDeactivate,
    closeDialogs, handleSave, handleDeactivate, fetchData, closeNotify
  } = useMonthlyPass();

  return (
    <Box>
      <PageHeader title="Khách & vé" description="Hồ sơ khách, phương tiện liên kết và các kỳ vé tháng." actions={canManageMonthlyPasses && <button className="button primary" disabled={loading || submitting} onClick={handleOpenCreate}><AddIcon fontSize="small" /> Thêm vé tháng</button>} />
      <WorkspaceTabs />
      <div className="toolbar" style={{ justifyContent: "flex-end", marginBottom: 12 }}><button className="button quiet small" onClick={fetchData} disabled={loading || submitting}>Làm mới</button></div>

      {!canManageMonthlyPasses && <Alert severity="info" sx={{ mb: 2 }}>Bạn có thể kiểm tra hiệu lực vé. Quản lý phụ trách cấp, gia hạn và ngừng vé tháng.</Alert>}

      <MonthlyPassDialog inline
        isOpen={dialogOpen && canManageMonthlyPasses}
        onClose={closeDialogs}
        onSave={handleSave}
        pass={selectedPass}
        vehicles={vehicles}
        customers={customers}
        submitting={submitting}
      />

      <MonthlyPassTable
        passes={passes}
        loading={loading}
        canManage={canManageMonthlyPasses}
        onEdit={handleOpenEdit}
        onDeactivate={handleOpenDeactivate}
      />



      <Dialog open={deactivateDialogOpen && canManageMonthlyPasses} onClose={closeDialogs}>
        <DialogTitle fontWeight="bold">Xác nhận hủy vé</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Ngừng hiệu lực kỳ vé của thẻ <strong>{selectedPass?.card_code || selectedPass?.pass_code}</strong>? Thao tác này không hoàn tiền. Quản lý có thể ghi nhận hoàn tiền tại mục Thu tiền &amp; Chốt ca.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={closeDialogs} variant="outlined">Quay lại</Button>
          <Button onClick={handleDeactivate} color="error" variant="contained">Xác nhận Hủy</Button>
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
