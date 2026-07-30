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
  FormControlLabel,
  Switch,
} from "@mui/material";

const TICKET_TYPES = [
  { value: "HOURLY", label: "Theo giờ" },
  { value: "DAILY", label: "Theo ngày" },
  { value: "MONTHLY", label: "Theo tháng" },
];

const today = () => new Date().toISOString().slice(0, 10);

const PriceConfigDialog = ({ open, onClose, onSave, priceConfig, vehicleTypes }) => {
  const [formData, setFormData] = useState({
    vehicle_type_id: "",
    ticket_type: "HOURLY",
    price: "",
    effective_date: today(),
    is_active: true,
  });

  useEffect(() => {
    if (priceConfig) {
      setFormData({
        vehicle_type_id: priceConfig.vehicle_type_id ?? "",
        ticket_type: priceConfig.ticket_type || "HOURLY",
        price: priceConfig.price ?? "",
        effective_date: priceConfig.effective_date || today(),
        is_active: priceConfig.is_active ?? true,
      });
    } else {
      setFormData({
        vehicle_type_id: "",
        ticket_type: "HOURLY",
        price: "",
        effective_date: today(),
        is_active: true,
      });
    }
  }, [priceConfig, open]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      ...formData,
      vehicle_type_id: Number(formData.vehicle_type_id),
      price: Number(formData.price),
    });
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle sx={{ fontWeight: "bold" }}>
          {priceConfig ? "Chỉnh sửa bảng giá" : "Thêm bảng giá mới"}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              select
              label="Loại xe"
              name="vehicle_type_id"
              value={formData.vehicle_type_id}
              onChange={handleChange}
              required
              fullWidth
              autoFocus
            >
              {vehicleTypes.map((vt) => (
                <MenuItem key={vt.id} value={vt.id}>
                  {vt.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Hình thức tính phí"
              name="ticket_type"
              value={formData.ticket_type}
              onChange={handleChange}
              required
              fullWidth
            >
              {TICKET_TYPES.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Đơn giá (VNĐ)"
              name="price"
              type="number"
              value={formData.price}
              onChange={handleChange}
              required
              fullWidth
              slotProps={{ htmlInput: { min: 0, step: 1000 } }}
            />
            <TextField
              label="Ngày áp dụng"
              name="effective_date"
              type="date"
              value={formData.effective_date}
              onChange={handleChange}
              required
              fullWidth
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={formData.is_active}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, is_active: e.target.checked }))
                  }
                  name="is_active"
                />
              }
              label="Đang áp dụng"
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} color="inherit">
            Hủy
          </Button>
          <Button type="submit" variant="contained">
            {priceConfig ? "Cập nhật" : "Thêm mới"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default PriceConfigDialog;
