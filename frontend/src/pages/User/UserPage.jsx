import { Box, Snackbar, Alert, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from "@mui/material";
import { PageHeader, PrototypeIcon, WorkspaceTabs } from "../../components/common/PrototypeUI";

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
    <Box>
      <PageHeader title="Tài khoản & phân quyền" description="Quản lý tài khoản nhân sự và tra cứu quyền sử dụng hệ thống." actions={<>
        <button className="button quiet small" onClick={fetchUsers} disabled={loading || submitting}>Làm mới</button>
        {canManage && <button className="button primary" onClick={handleOpenCreate} disabled={loading || submitting}><PrototypeIcon name="plus" />Thêm tài khoản</button>}
      </>} />
      <WorkspaceTabs />

      {/* Warning Banner */}
      {!canManage && (
        <Alert severity="warning" sx={{ mb: 3, borderRadius: 2 }}>
          Lưu ý: Bạn đang đăng nhập với quyền hạn hạn chế. Các chức năng Thêm/Sửa/Xóa đã bị vô hiệu hóa.
        </Alert>
      )}
      {canManage && !canDeleteUsers && <Alert severity="info" sx={{ mb: 3 }}>Bạn có thể tạo, cập nhật và khóa tài khoản nhân viên. Tài khoản quản lý và quản trị viên do quản trị viên phụ trách.</Alert>}

      {canManage && <UserDialog inline
        isOpen={dialogOpen}
        onClose={closeDialogs}
        onSave={handleSave}
        user={selectedUser}
        roles={roles}
        submitting={submitting}
      />}

      <UserTable
        users={users}
        loading={loading}
        canManage={canManage}
        canDelete={canDeleteUsers}
        canEditUser={canEditUser}
        onEdit={handleOpenEdit}
        onDelete={handleOpenDelete}
        busy={submitting}
      />

      {/* Modals */}
      {canManage && (
        <>
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
