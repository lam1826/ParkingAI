import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  MenuItem,
} from "@mui/material";

const VehicleDialog = ({ open, onClose, onSave, vehicle, vehicleTypes, customers }) => {
  const [formData, setFormData] = useState({
    license_plate: "",
    vehicle_type_id: "",
    customer_id: "",
  });

  useEffect(() => {
    if (vehicle) {
      setFormData({
        license_plate: vehicle.license_plate || "",
        vehicle_type_id: vehicle.vehicle_type_id ?? "",
        customer_id: vehicle.customer_id ?? "",
      });
    } else {
      setFormData({
        license_plate: "",
        vehicle_type_id: "",
        customer_id: "",
      });
    }
  }, [vehicle, open]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      ...formData,
      vehicle_type_id: Number(formData.vehicle_type_id),
      customer_id: formData.customer_id ? Number(formData.customer_id) : null,
    });
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle sx={{ fontWeight: "bold" }}>
          {vehicle ? "Chỉnh sửa phương tiện" : "Thêm phương tiện mới"}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label="Biển số xe"
              name="license_plate"
              value={formData.license_plate}
              onChange={handleChange}
              required
              fullWidth
              autoFocus
            />
            <TextField
              select
              label="Loại xe"
              name="vehicle_type_id"
              value={formData.vehicle_type_id}
              onChange={handleChange}
              required
              fullWidth
            >
              {vehicleTypes.map((vt) => (
                <MenuItem key={vt.id} value={vt.id}>
                  {vt.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Chủ xe (tùy chọn)"
              name="customer_id"
              value={formData.customer_id}
              onChange={handleChange}
              fullWidth
            >
              <MenuItem value="">
                <em>Khách vãng lai</em>
              </MenuItem>
              {customers.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.full_name} ({c.phone_number})
                </MenuItem>
              ))}
            </TextField>
          </Box>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} color="inherit">
            Hủy
          </Button>
          <Button type="submit" variant="contained">
            {vehicle ? "Cập nhật" : "Thêm mới"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default VehicleDialog;
