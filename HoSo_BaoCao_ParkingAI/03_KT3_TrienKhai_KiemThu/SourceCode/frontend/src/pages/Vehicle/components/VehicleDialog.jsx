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
  vehicle_type_id: "",
  customer_id: "",
};

const VehicleDialog = ({ isOpen, onClose, onSave, vehicle, vehicleTypes, customers, submitting }) => {
  const [form, setForm] = useState(initialForm);

  useEffect(() => {
    if (vehicle) {
      setForm({
        license_plate: vehicle.license_plate || "",
        vehicle_type_id: vehicle.vehicle_type_id || vehicle.vehicle_type?.id || "",
        customer_id: vehicle.customer_id || vehicle.customer?.id || "",
      });
    } else {
      setForm(initialForm);
    }
  }, [vehicle, isOpen]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      license_plate: form.license_plate.trim().toUpperCase(),
      vehicle_type_id: Number(form.vehicle_type_id),
      customer_id: form.customer_id === "" ? null : Number(form.customer_id),
    });
  };

  return (
    <Dialog open={isOpen} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight="bold">
        {vehicle ? "Chỉnh sửa Phương tiện" : "Thêm mới Phương tiện"}
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
                name="vehicle_type_id"
                value={form.vehicle_type_id}
                onChange={handleChange}
              >
                {vehicleTypes.map((type) => (
                  <MenuItem key={type.id} value={type.id}>
                    {type.name || type.type_name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                select
                size="small"
                label="Khách hàng (Chủ sở hữu)"
                name="customer_id"
                value={form.customer_id}
                onChange={handleChange}
              >
                <MenuItem value="">
                  <em>-- Khách vãng lai --</em>
                </MenuItem>
                {customers.map((cus) => (
                  <MenuItem key={cus.id} value={cus.id}>
                    {cus.full_name} - {cus.phone_number}
                  </MenuItem>
                ))}
              </TextField>
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
            {vehicle ? "Lưu thay đổi" : "Thêm mới"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default VehicleDialog;
