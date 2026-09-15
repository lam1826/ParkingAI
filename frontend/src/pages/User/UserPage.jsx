import { Box, Typography, Stack, Snackbar, Alert, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

import UserTable from "./components/UserTable";
import UserDialog from "./components/UserDialog";
import useUser from "./hooks/useUser";

export default function UsersPage() {
  const {
    users, roles, loading, submitting, canManage, canDeleteUsers, canEditUser,
    dialogOpen, deleteDialogOpen, selectedUser, notify,
    handleOpenCreate, handleOpenEdit, handleOpenDelete,
    closeDialogs, handleSave, handleDelete, fetchUsers, closeNotify
  } = useUser();

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5" fontWeight="bold" color="text.primary">
          Quản lý Người dùng
        </Typography>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={fetchUsers} disabled={loading}>
          Làm mới
        </Button>
      </Stack>

      {/* Warning Banner */}
      {!canManage && (
        <Alert severity="warning" sx={{ mb: 3, borderRadius: 2 }}>
          Lưu ý: Bạn đang đăng nhập với quyền hạn hạn chế. Các chức năng Thêm/Sửa/Xóa đã bị vô hiệu hóa.
        </Alert>
      )}
      {canManage && !canDeleteUsers && <Alert severity="info" sx={{ mb: 3 }}>Bạn có thể tạo, cập nhật và khóa tài khoản nhân viên. Tài khoản quản lý và quản trị viên do quản trị viên phụ trách.</Alert>}

      {/* Table */}
      <UserTable
        users={users}
        loading={loading}
        canManage={canManage}
        canDelete={canDeleteUsers}
        canEditUser={canEditUser}
        onAdd={handleOpenCreate}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
      />

      {/* Modals */}
      {canManage && (
        <>
          <UserDialog
            isOpen={dialogOpen}
            onClose={closeDialogs}
            onSave={handleSave}
            user={selectedUser}
            roles={roles}
            submitting={submitting}
          />

          <Dialog open={deleteDialogOpen && canDeleteUsers} onClose={closeDialogs}>
            <DialogTitle fontWeight="bold">Xác nhận xóa tài khoản</DialogTitle>
            <DialogContent>
              <DialogContentText>
                Bạn có chắc chắn muốn xóa tài khoản <strong>{selectedUser?.username}</strong>? Hành động này không thể hoàn tác.
              </DialogContentText>
            </DialogContent>
            <DialogActions sx={{ p: 2 }}>
              <Button onClick={closeDialogs} variant="outlined">Quay lại</Button>
              <Button onClick={handleDelete} color="error" variant="contained">Xác nhận Xóa</Button>
            </DialogActions>
          </Dialog>
        </>
      )}

      {/* Notifications */}
      <Snackbar open={notify.open} autoHideDuration={4000} onClose={closeNotify} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
        <Alert severity={notify.severity} variant="filled" onClose={closeNotify} sx={{ width: "100%" }}>
          {notify.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
