import { useState, useEffect } from "react";
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField, Grid, MenuItem, CircularProgress } from "@mui/material";

const initialForm = {
  pass_code: "",
  vehicle_id: "",
  customer_id: "",
  start_date: "",
  end_date: "",
  price: 0,
};

const MonthlyPassDialog = ({ isOpen, onClose, onSave, pass, vehicles, customers, submitting }) => {
  const [form, setForm] = useState(initialForm);

  useEffect(() => {
    if (pass) {
      setForm({
        pass_code: pass.pass_code || "",
        vehicle_id: pass.vehicle_id || pass.vehicle?.id || "",
        customer_id: pass.customer_id || pass.customer?.id || "",
        // Xử lý cắt chuỗi ngày tháng để bind vào input type="date"
        start_date: pass.start_date ? pass.start_date.split("T")[0] : "",
        end_date: pass.end_date ? pass.end_date.split("T")[0] : "",
        price: pass.price || 0,
      });
    } else {
      setForm(initialForm);
    }
  }, [pass, isOpen]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  // Validation tối thiểu phía client; backend vẫn là biên bảo vệ cuối cùng
  const dateRangeInvalid =
    Boolean(form.start_date && form.end_date) && form.end_date < form.start_date;
  // Giá vé: số nguyên VND không âm. KHÔNG tự làm tròn — nhập 123.5 phải bị
  // chặn kèm thông báo, không âm thầm đổi thành 124.
  const priceNumber = Number(form.price);
  const priceInvalid =
    form.price === "" || form.price === null ||
    !Number.isFinite(priceNumber) ||
    !Number.isInteger(priceNumber) ||
    priceNumber < 0;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (dateRangeInvalid || priceInvalid) return;
    // Contract backend: price là số nguyên VND, pass_code được trim
    onSave({
      ...form,
      pass_code: form.pass_code.trim(),
      price: priceNumber,
    });
  };

  return (
    <Dialog open={isOpen} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight="bold">
        {pass ? "Cập nhật / Gia hạn Vé tháng" : "Đăng ký Vé tháng mới"}
      </DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth required size="small"
                label="Mã thẻ (NFC/RFID)"
                name="pass_code"
                value={form.pass_code}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth required size="small" type="number"
                label="Số tiền thu (VND)"
                name="price"
                value={form.price}
                onChange={handleChange}
                error={priceInvalid}
                helperText={priceInvalid ? "Số tiền phải là số nguyên VND không âm (không nhập số lẻ thập phân)" : undefined}
                slotProps={{ htmlInput: { min: 0, step: 1000 } }}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth select required size="small"
                label="Chọn Phương tiện"
                name="vehicle_id"
                value={form.vehicle_id}
                onChange={handleChange}
              >
                {vehicles.map((v) => (
                  <MenuItem key={v.id} value={v.id}>{v.license_plate}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth select required size="small"
                label="Chọn Khách hàng"
                name="customer_id"
                value={form.customer_id}
                onChange={handleChange}
              >
                {customers.map((c) => (
                  <MenuItem key={c.id} value={c.id}>{c.full_name} - {c.phone_number}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth required size="small" type="date"
                label="Ngày bắt đầu"
                name="start_date"
                slotProps={{ inputLabel: { shrink: true } }}
                value={form.start_date}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth required size="small" type="date"
                label="Ngày hết hạn"
                name="end_date"
                slotProps={{ inputLabel: { shrink: true } }}
                value={form.end_date}
                onChange={handleChange}
                error={dateRangeInvalid}
                helperText={dateRangeInvalid ? "Ngày hết hạn phải từ ngày bắt đầu trở đi" : undefined}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} variant="outlined" disabled={submitting}>Hủy</Button>
          <Button
            type="submit" variant="contained" disabled={submitting}
            startIcon={submitting && <CircularProgress size={18} color="inherit" />}
          >
            {pass ? "Lưu thay đổi" : "Đăng ký"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default MonthlyPassDialog;