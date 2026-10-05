import { requestId as newRequestId } from "../../../utils/requestId";
import { toBusinessDateString } from "../../../utils/businessDate";
import { customerForVehicle, ownerChoices, renewalDefaults, renewalEndsBeforeToday } from "../monthlyPassForm";
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

const MonthlyPassDialog = ({ inline = false, isOpen, onClose, onSave, pass, vehicles, customers, submitting }) => {
  const [form, setForm] = useState(initialForm);
  const [requestId, setRequestId] = useState("");

  useEffect(() => {
    setRequestId(newRequestId());
    if (pass) {
      // Kỳ mới bắt đầu sau kỳ đã chọn, nhưng không sớm hơn hôm nay: kỳ đã trôi
      // qua không phủ được lượt gửi nào (phạm vi vé chốt lúc xe vào).
      const period = renewalDefaults(pass.end_date, toBusinessDateString());
      setForm({
        pass_code: pass.card_code || pass.pass_code || "",
        vehicle_id: pass.vehicle_id || pass.vehicle?.id || "",
        customer_id: pass.customer_id || pass.customer?.id || "",
        start_date: period.start_date,
        end_date: period.end_date,
        price: pass.price || 0,
        payment_method: "cash",
      });
    } else {
      setForm(initialForm);
    }
  }, [pass, isOpen]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev, [name]: value,
      // Vé tháng thuộc chủ xe: chọn xe có chủ thì tự chọn đúng chủ đó.
      ...(name === "vehicle_id" ? { customer_id: customerForVehicle(vehicles, customers, value, prev.customer_id) } : {}),
    }));
  };
  const customerChoices = pass ? customers : ownerChoices(vehicles, customers, form.vehicle_id);

  // Validation tối thiểu phía client; backend vẫn là biên bảo vệ cuối cùng
  const dateRangeInvalid =
    Boolean(form.start_date && form.end_date) && form.end_date < form.start_date;
  const renewalElapsed = Boolean(pass) && renewalEndsBeforeToday(form, toBusinessDateString());
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
    if (dateRangeInvalid || priceInvalid || renewalElapsed) return;
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

  if (inline && !isOpen) return null;
  const Container = inline ? "section" : Dialog;
  return (
    <Container {...(inline ? { className: "surface core-editor" } : { open: isOpen, onClose: submitting ? undefined : onClose, maxWidth: "sm", fullWidth: true })}>
      <DialogTitle component="h2" fontWeight="bold" sx={inline ? { p: 0, mb: "22px", fontSize: "18px" } : undefined}>
        {pass ? "Gia hạn vé tháng" : "Đăng ký vé tháng mới"}
      </DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent dividers={!inline} sx={inline ? { p: 0, overflow: "visible" } : undefined}>
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
                {customerChoices.map((c) => (
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
                error={dateRangeInvalid || renewalElapsed}
                helperText={dateRangeInvalid ? "Ngày hết hạn phải từ ngày bắt đầu trở đi" : renewalElapsed ? "Kỳ gia hạn đã kết thúc trước hôm nay; hãy chọn kỳ từ hôm nay trở đi" : undefined}
              />
            </Grid>
          </Grid>
          <TextField select fullWidth label="Hình thức thu tiền" name="payment_method" value={form.payment_method} onChange={handleChange} sx={{ mt: 2 }}>
            <MenuItem value="cash">Tiền mặt</MenuItem><MenuItem value="transfer">Chuyển khoản</MenuItem>
          </TextField>
        </DialogContent>
        <DialogActions sx={inline ? { p: 0, mt: "20px", justifyContent: "flex-start", flexWrap: "wrap", gap: 1 } : { p: 2 }}>
          <Button onClick={onClose} variant="outlined" disabled={submitting}>Hủy</Button>
          <Button
            type="submit" variant="contained" disabled={submitting || dateRangeInvalid || priceInvalid || renewalElapsed}
            startIcon={submitting && <CircularProgress size={18} color="inherit" />}
          >
            {pass ? "Gia hạn và ghi nhận thu" : "Đăng ký và ghi nhận thu"}
          </Button>
        </DialogActions>
      </form>
    </Container>
  );
};

export default MonthlyPassDialog;
