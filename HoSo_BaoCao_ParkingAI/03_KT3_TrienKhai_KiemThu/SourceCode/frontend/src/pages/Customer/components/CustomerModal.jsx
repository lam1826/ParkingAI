import { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Grid,
  CircularProgress,
} from "@mui/material";

const initialForm = {
  full_name: "",
  phone_number: "",
  email: "",
  address: "",
};

const CustomerModal = ({ open, mode, data, onClose, onSubmit, submitting }) => {
  const [form, setForm] = useState(initialForm);

  useEffect(() => {
    if (data && mode === "edit") {
      setForm({
        full_name: data.full_name || "",
        phone_number: data.phone_number || "",
        email: data.email || "",
        address: data.address || "",
      });
    } else {
      setForm(initialForm);
    }
  }, [data, mode, open]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(form);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight="bold">
        {mode === "create" ? "Thêm mới Khách hàng" : "Chỉnh sửa Khách hàng"}
      </DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                required
                size="small"
                label="Họ và tên"
                name="full_name"
                value={form.full_name}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                required
                size="small"
                label="Số điện thoại"
                name="phone_number"
                value={form.phone_number}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                size="small"
                type="email"
                label="Email"
                name="email"
                value={form.email}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                multiline
                rows={2}
                size="small"
                label="Địa chỉ"
                name="address"
                value={form.address}
                onChange={handleChange}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} variant="outlined" disabled={submitting}>
            Hủy
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={submitting}
            startIcon={submitting && <CircularProgress size={18} color="inherit" />}
          >
            {mode === "create" ? "Thêm mới" : "Lưu thay đổi"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default CustomerModal;