import { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  MenuItem
} from "@mui/material";

export default function CustomerDialog({ open, onClose, onSave, customer }) {
  // Khởi tạo state cho form
  const [formData, setFormData] = useState({
    fullName: "",
    phone: "",
    email: "",
    status: "Active"
  });

  // Theo dõi props 'customer' để nạp dữ liệu khi ở chế độ "Sửa"
  useEffect(() => {
    if (customer) {
      setFormData(customer);
    } else {
      // Reset form khi ở chế độ "Thêm mới"
      setFormData({ fullName: "", phone: "", email: "", status: "Active" });
    }
  }, [customer, open]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    // Gọi hàm onSave được truyền từ CustomerPage xuống
    onSave(formData);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight="bold">
        {customer ? "Cập nhật Khách hàng" : "Thêm Khách hàng mới"}
      </DialogTitle>
      
      <form onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <TextField
              label="Họ và Tên"
              name="fullName"
              value={formData.fullName}
              onChange={handleChange}
              required
              fullWidth
            />
            <TextField
              label="Số điện thoại"
              name="phone"
              value={formData.phone}
              onChange={handleChange}
              required
              fullWidth
            />
            <TextField
              label="Email"
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              fullWidth
            />
            <TextField
              select
              label="Trạng thái"
              name="status"
              value={formData.status}
              onChange={handleChange}
              fullWidth
            >
              <MenuItem value="Active">Hoạt động (Active)</MenuItem>
              <MenuItem value="Inactive">Tạm khóa (Inactive)</MenuItem>
            </TextField>
          </Box>
        </DialogContent>
        
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} color="inherit">
            Hủy bỏ
          </Button>
          <Button type="submit" variant="contained" color="primary">
            {customer ? "Cập nhật" : "Lưu dữ liệu"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}