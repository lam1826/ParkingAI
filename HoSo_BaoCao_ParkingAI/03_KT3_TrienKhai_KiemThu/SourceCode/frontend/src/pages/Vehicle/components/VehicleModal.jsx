import { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Grid,
  MenuItem,
  CircularProgress,
} from "@mui/material";

const initialForm = {
  license_plate: "",
  vehicle_type: "CAR",
  color: "",
  customer_id: "",
};

const VehicleModal = ({ open, mode, data, onClose, onSubmit, submitting }) => {
  const [form, setForm] = useState(initialForm);

  useEffect(() => {
    if (data && mode === "edit") {
      setForm({
        license_plate: data.license_plate || "",
        vehicle_type: data.vehicle_type || "CAR",
        color: data.color || "",
        customer_id: data.customer_id || "",
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
        {mode === "create" ? "Thêm mới Phương tiện" : "Chỉnh sửa Phương tiện"}
      </DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                required
                size="small"
                label="Biển số xe"
                name="license_plate"
                value={form.license_plate}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                select
                required
                size="small"
                label="Loại xe"
                name="vehicle_type"
                value={form.vehicle_type}
                onChange={handleChange}
              >
                <MenuItem value="CAR">Ô tô</MenuItem>
                <MenuItem value="MOTORBIKE">Xe máy</MenuItem>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                size="small"
                label="Màu sắc"
                name="color"
                value={form.color}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                size="small"
                label="Mã khách hàng (Chủ sở hữu)"
                name="customer_id"
                placeholder="Để trống nếu là khách vãng lai"
                value={form.customer_id}
                onChange={handleChange}
                helperText="Nhập ID của khách hàng để liên kết phương tiện"
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

export default VehicleModal;