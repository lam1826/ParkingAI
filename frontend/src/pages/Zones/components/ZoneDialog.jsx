import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  FormControlLabel,
  Switch,
} from "@mui/material";

const ZoneDialog = ({ open, onClose, onSave, zone }) => {
  const [formData, setFormData] = useState({
    name: "",
    capacity: "",
    is_active: true,
  });

  useEffect(() => {
    if (zone) {
      setFormData({
        name: zone.name || "",
        capacity: zone.capacity ?? "",
        is_active: zone.is_active ?? true,
      });
    } else {
      setFormData({
        name: "",
        capacity: "",
        is_active: true,
      });
    }
  }, [zone, open]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({ ...formData, capacity: Number(formData.capacity) });
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle sx={{ fontWeight: "bold" }}>
          {zone ? "Chỉnh sửa khu vực" : "Thêm khu vực mới"}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label="Tên khu vực"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
              fullWidth
              autoFocus
            />
            <TextField
              label="Sức chứa"
              name="capacity"
              type="number"
              value={formData.capacity}
              onChange={handleChange}
              required
              fullWidth
              slotProps={{ htmlInput: { min: 0 } }}
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
              label="Đang hoạt động"
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} color="inherit">
            Hủy
          </Button>
          <Button type="submit" variant="contained">
            {zone ? "Cập nhật" : "Thêm mới"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default ZoneDialog;