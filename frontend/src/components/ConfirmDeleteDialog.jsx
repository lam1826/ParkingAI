import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
} from "@mui/material";

export default function ConfirmDeleteDialog({
  open,
  onClose,
  onConfirm,
  title = "Xác nhận xóa",
  message = "Bạn có chắc chắn muốn xóa mục này? Hành động này không thể hoàn tác.",
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle fontWeight="bold" color="error.main">
        {title}
      </DialogTitle>
      <DialogContent dividers>
        <DialogContentText>{message}</DialogContentText>
      </DialogContent>
      <DialogActions sx={{ p: 2 }}>
        <Button onClick={onClose} variant="outlined" color="inherit">
          Hủy bỏ
        </Button>
        <Button onClick={onConfirm} variant="contained" color="error">
          Xác nhận Xóa
        </Button>
      </DialogActions>
    </Dialog>
  );
}