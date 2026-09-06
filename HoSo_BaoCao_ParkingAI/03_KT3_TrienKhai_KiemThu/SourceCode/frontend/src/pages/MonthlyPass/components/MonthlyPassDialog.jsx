import { useState, useEffect } from "react";
import { Alert, Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField, Grid, MenuItem, CircularProgress } from "@mui/material";

const initialForm = {
  pass_code: "",
  vehicle_id: "",
  customer_id: "",
  start_date: "",
  end_date: "",
  price: 0,
  payment_method: "cash",
};

const MonthlyPassDialog = ({ isOpen, onClose, onSave, pass, vehicles, customers, submitting }) => {
  const [form, setForm] = useState(initialForm);
  const [requestId, setRequestId] = useState("");

  useEffect(() => {
    setRequestId(crypto.randomUUID());
    if (pass) {
      const nextStart = new Date(`${pass.end_date}T12:00:00Z`);
      nextStart.setUTCDate(nextStart.getUTCDate() + 1);
      const nextEnd = new Date(nextStart);
      nextEnd.setUTCDate(nextEnd.getUTCDate() + 29);
      setForm({
        pass_code: pass.card_code || pass.pass_code || "",
        vehicle_id: pass.vehicle_id || pass.vehicle?.id || "",
        customer_id: pass.customer_id || pass.customer?.id || "",
        // Xử lý cắt chuỗi ngày tháng để bind vào input type="date"
        start_date: nextStart.toISOString().slice(0, 10),
        end_date: nextEnd.toISOString().slice(0, 10),
        price: pass.price || 0,
        payment_method: "cash",
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
    !Number.isSafeInteger(priceNumber) ||
    priceNumber < 0;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (dateRangeInvalid || priceInvalid) return;
    // Contract backend: price là số nguyên VND, pass_code được trim
    onSave(pass ? {
      start_date: form.start_date, end_date: form.end_date, price: priceNumber,
      payment_method: form.payment_method, request_id: requestId,
    } : {
      ...form,
      pass_code: form.pass_code.trim(),
      price: priceNumber,
    });
  };

  return (
    <Dialog open={isOpen} onClose={submitting ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight="bold">
        {pass ? "Gia hạn vé tháng" : "Đăng ký vé tháng mới"}
      </DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Alert severity="info" sx={{ mb: 2 }}>
            {pass ? "Gia hạn tạo kỳ vé mới trên cùng mã thẻ. Lịch sử và khoản thu của kỳ cũ được giữ nguyên. Mặc định kỳ mới là 30 ngày; có thể chỉnh ngày." : "Xác nhận sẽ cấp vé và ghi nhận khoản thu vào sổ thu tiền."}
          </Alert>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth required size="small"
                label="Mã thẻ (NFC/RFID)"
                name="pass_code"
                disabled={Boolean(pass)}
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
                slotProps={{ htmlInput: { min: 0, step: 1, max: Number.MAX_SAFE_INTEGER } }}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth select required size="small"
                label="Chọn Phương tiện"
                name="vehicle_id"
                disabled={Boolean(pass)}
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
                disabled={Boolean(pass)}
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
          <TextField select fullWidth label="Hình thức thu tiền" name="payment_method" value={form.payment_method} onChange={handleChange} sx={{ mt: 2 }}>
            <MenuItem value="cash">Tiền mặt</MenuItem><MenuItem value="transfer">Chuyển khoản</MenuItem>
          </TextField>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={onClose} variant="outlined" disabled={submitting}>Hủy</Button>
          <Button
            type="submit" variant="contained" disabled={submitting || dateRangeInvalid || priceInvalid}
            startIcon={submitting && <CircularProgress size={18} color="inherit" />}
          >
            {pass ? "Gia hạn và ghi nhận thu" : "Đăng ký và ghi nhận thu"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default MonthlyPassDialog;
