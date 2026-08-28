import { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, MenuItem, Snackbar, Stack, TextField,
  Typography,
} from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import RefreshIcon from "@mui/icons-material/Refresh";

// Chuẩn hóa lỗi API thành chuỗi đọc được: FastAPI 422 trả detail dạng mảng object,
// nếu render thẳng vào Alert sẽ hỏng. Ưu tiên msg của từng lỗi, kèm tên field nếu có.
export function extractErrorMessage(error, fallback = "Đã xảy ra lỗi.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : null;
        const msg = item?.msg || "";
        return field && msg ? `${field}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

export default function CrudPage({ title, fields, service, canEdit = true }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [notice, setNotice] = useState({ open: false, severity: "success", message: "" });

  const notify = (message, severity = "success") => setNotice({ open: true, message, severity });
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await service.getAll();
      setRows(Array.isArray(data) ? data : data.items || data.data || []);
    } catch (error) {
      notify(extractErrorMessage(error, "Không thể tải dữ liệu."), "error");
    } finally {
      setLoading(false);
    }
  }, [service]);

  useEffect(() => { load(); }, [load]);

  const startCreate = () => {
    setEditing(null);
    setForm(Object.fromEntries(fields.map((field) => [field.name, field.defaultValue ?? (field.type === "boolean" ? true : "")])));
    setOpen(true);
  };
  const startEdit = (row) => {
    setEditing(row);
    setForm(Object.fromEntries(fields.map((field) => [field.name, row[field.name] ?? ""])));
    setOpen(true);
  };
  const save = async () => {
    // Nút Lưu không chạy qua native <form onSubmit> nên thuộc tính required của
    // TextField không tự chặn — phải kiểm tra required tường minh trước khi gọi API.
    const missing = fields.filter(
      (field) => field.required && field.type !== "boolean"
        && (form[field.name] === "" || form[field.name] == null)
    );
    if (missing.length) {
      notify(`Vui lòng nhập: ${missing.map((field) => field.label).join(", ")}.`, "error");
      return;
    }
    try {
      const payload = {};
      fields.forEach((field) => {
        let value = form[field.name];
        if (field.type === "number" || field.valueType === "number" || field.name.endsWith("_id")) value = Number(value);
        payload[field.name] = value === "" && !field.required ? null : value;
      });
      if (editing) await service.update(editing.id, payload);
      else await service.create(payload);
      setOpen(false);
      notify(editing ? "Cập nhật thành công." : "Thêm mới thành công.");
      await load();
    } catch (error) {
      notify(extractErrorMessage(error, "Không thể lưu dữ liệu."), "error");
    }
  };
  const remove = async (row) => {
    if (!window.confirm(`Xóa bản ghi #${row.id}?`)) return;
    try {
      await service.delete(row.id);
      notify("Xóa thành công.");
      await load();
    } catch (error) {
      const message = error.response?.status === 409
        ? "Không thể xóa: bản ghi đang được dữ liệu khác tham chiếu. Hãy xóa/chuyển dữ liệu con trước, hoặc tắt 'Đang hoạt động' thay vì xóa."
        : extractErrorMessage(error, "Không thể xóa dữ liệu đang được sử dụng.");
      notify(message, "error");
    }
  };

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    ...fields.filter((field) => !field.hideInTable).map((field) => ({
      field: field.name,
      headerName: field.label,
      flex: field.flex ?? 1,
      minWidth: field.minWidth ?? 130,
      valueFormatter: field.formatter,
    })),
    ...(canEdit ? [{
      field: "actions", headerName: "Thao tác", width: 160, sortable: false,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", height: "100%" }}>
          <Button size="small" startIcon={<EditIcon />} onClick={() => startEdit(row)}>Sửa</Button>
          <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={() => remove(row)}>Xóa</Button>
        </Stack>
      ),
    }] : []),
  ];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        sx={{
          justifyContent: "space-between",
          alignItems: { xs: "flex-start", sm: "center" },
        }}
      >
        <Typography variant="h5" fontWeight="bold">{title}</Typography>
        <Stack direction="row" spacing={1}>
          <Button startIcon={<RefreshIcon />} onClick={load}>Làm mới</Button>
          {canEdit && <Button variant="contained" startIcon={<AddIcon />} onClick={startCreate}>Thêm mới</Button>}
        </Stack>
      </Stack>
      <Box sx={{ height: { xs: 460, md: 560 }, width: "100%" }}>
        <DataGrid rows={rows} columns={columns} loading={loading} disableRowSelectionOnClick
          pageSizeOptions={[10, 25, 50, 100]} slots={{ toolbar: GridToolbar }} />
      </Box>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? "Cập nhật" : "Thêm mới"}</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: "16px !important" }}>
          {fields.map((field) => field.type === "boolean" ? (
            <FormControlLabel key={field.name} control={<Checkbox checked={Boolean(form[field.name])}
              onChange={(event) => setForm({ ...form, [field.name]: event.target.checked })} />} label={field.label} />
          ) : (
            // Input date native luôn vẽ sẵn khung dd/mm/yyyy nên label phải shrink cố định
            <TextField key={field.name} select={field.type === "select"} type={field.type || "text"}
              label={field.label} required={field.required} value={form[field.name] ?? ""}
              slotProps={field.type === "date" ? { inputLabel: { shrink: true } } : undefined}
              onChange={(event) => setForm({ ...form, [field.name]: event.target.value })}>
              {(field.options || []).map((option) => <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>)}
            </TextField>
          ))}
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>Hủy</Button><Button variant="contained" onClick={save}>Lưu</Button></DialogActions>
      </Dialog>
      <Snackbar open={notice.open} autoHideDuration={4000} onClose={() => setNotice({ ...notice, open: false })}>
        <Alert severity={notice.severity}>{notice.message}</Alert>
      </Snackbar>
    </Box>
  );
}
