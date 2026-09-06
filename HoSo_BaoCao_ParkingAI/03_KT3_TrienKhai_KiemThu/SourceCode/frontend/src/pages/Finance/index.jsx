import { useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, MenuItem, Paper, Stack, Tab, Tabs,
  TextField, Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { DataGrid } from "@mui/x-data-grid";
import { AuthContext } from "../../context/AuthContext";
import { hasMinimumRole } from "../../constants/roles";
import financeService from "../../services/financeService";
import formatCurrency from "../../utils/formatCurrency";
import { formatBusinessTimestamp } from "../../utils/formatDate";
import { getErrorMessage } from "../../utils/errorMessage";
import { createLatestRequestGate } from "../../utils/latestRequestGate";
import { buildRefundPayload, parseCashAmount, paymentMethodLabels } from "./financeForm";

const money = (value) => `${formatCurrency(value)} ₫`;

export default function FinancePage() {
  const { user } = useContext(AuthContext);
  const isManager = hasMinimumRole(user?.role, "manager");
  const gate = useRef(null);
  if (gate.current === null) gate.current = createLatestRequestGate();
  const submitting = useRef(false);
  const [payments, setPayments] = useState({ items: [], total: 0 });
  const [shifts, setShifts] = useState({ items: [], total: 0 });
  const [currentShift, setCurrentShift] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState(0);
  const [filters, setFilters] = useState({ source_type: "", kind: "", date_from: "", date_to: "" });
  const [pagination, setPagination] = useState({ page: 0, pageSize: 25 });
  const [shiftPagination, setShiftPagination] = useState({ page: 0, pageSize: 10 });
  const [openingCash, setOpeningCash] = useState("0");
  const [countedCash, setCountedCash] = useState("");
  const [closeDialog, setCloseDialog] = useState(false);
  const [selectedShift, setSelectedShift] = useState(null);
  const [refund, setRefund] = useState(null);
  const [formError, setFormError] = useState("");
  const [mutating, setMutating] = useState(false);

  const load = useCallback(async () => {
    const generation = gate.current.begin();
    setLoading(true);
    setError("");
    try {
      if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
        throw new Error("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.");
      }
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
      const [paymentData, shiftData, ownOpen] = await Promise.all([
        financeService.getPayments({ ...params, page: pagination.page + 1, size: pagination.pageSize }),
        financeService.getShifts({ page: shiftPagination.page + 1, size: shiftPagination.pageSize }),
        financeService.getShifts({ status: "open", staff_id: user.id, size: 1 }),
      ]);
      if (!gate.current.isCurrent(generation)) return;
      setPayments(paymentData);
      setShifts(shiftData);
      setCurrentShift(ownOpen.items[0] || null);
    } catch (requestError) {
      if (gate.current.isCurrent(generation)) {
        setError(getErrorMessage(requestError, "Không tải được dữ liệu thu ngân. Hãy thử làm mới."));
      }
    } finally {
      if (gate.current.isCurrent(generation)) setLoading(false);
    }
  }, [filters, pagination, shiftPagination, user.id]);

  useEffect(() => {
    load();
    return () => gate.current.invalidate();
  }, [load]);

  const changeFilter = (field) => (event) => {
    setFilters((previous) => ({ ...previous, [field]: event.target.value }));
    setPagination((previous) => ({ ...previous, page: 0 }));
  };

  const runMutation = async (operation, message, onSuccess) => {
    if (submitting.current) return;
    submitting.current = true;
    setMutating(true);
    setFormError("");
    setNotice("");
    try {
      await operation();
      onSuccess?.();
      setNotice(message);
      await load();
    } catch (requestError) {
      setFormError(getErrorMessage(requestError, "Chưa xác nhận được kết quả. Giữ nguyên nội dung khi thử lại, hoặc làm mới để kiểm tra giao dịch."));
    } finally {
      submitting.current = false;
      setMutating(false);
    }
  };

  const startRefund = (payment) => {
    setFormError("");
    setRefund({ payment, amount: String(payment.refundable_amount), method: payment.method === "transfer" ? "transfer" : "cash", reason: "", idempotencyKey: crypto.randomUUID() });
  };

  const paymentColumns = [
    { field: "created_at", headerName: "Thời gian", width: 195, valueFormatter: formatBusinessTimestamp },
    { field: "kind", headerName: "Giao dịch", width: 115, renderCell: ({ value }) => <Chip size="small" variant="outlined" color={value === "receipt" ? "success" : "warning"} label={value === "receipt" ? "Thu tiền" : "Hoàn tiền"} /> },
    { field: "source_type", headerName: "Nguồn", width: 140, valueFormatter: (value) => value === "monthly_pass" ? "Vé tháng" : "Lượt gửi xe" },
    { field: "amount", headerName: "Số tiền", width: 155, align: "right", headerAlign: "right", valueFormatter: money },
    { field: "method", headerName: "Phương thức", minWidth: 160, flex: 1, valueFormatter: (value) => paymentMethodLabels[value] || value },
    { field: "source_id", headerName: "Mã vé / lượt gửi", minWidth: 140, flex: 1 },
    { field: "shift_id", headerName: "Ghi nhận ca", width: 140, renderCell: ({ value }) => <Typography variant="body2" sx={{ lineHeight: "inherit" }}>{value ? "Trong ca" : "Ngoài ca"}</Typography> },
    ...(isManager ? [{ field: "refund_action", headerName: "Thao tác", width: 125, sortable: false, filterable: false, renderCell: ({ row }) => row.kind === "receipt" && row.refundable_amount > 0 ? <Button size="small" disabled={loading || mutating || Boolean(error)} onClick={() => startRefund(row)}>Hoàn tiền</Button> : "—" }] : []),
  ];
  const shiftColumns = [
    { field: "staff_name", headerName: "Nhân viên", minWidth: 170, flex: 1 },
    { field: "opened_at", headerName: "Mở ca", width: 195, valueFormatter: formatBusinessTimestamp },
    { field: "closed_at", headerName: "Chốt ca", width: 195, valueFormatter: (value) => value ? formatBusinessTimestamp(value) : "Chưa chốt" },
    { field: "status", headerName: "Trạng thái", width: 125, renderCell: ({ value }) => <Chip size="small" color={value === "open" ? "success" : "default"} label={value === "open" ? "Đang mở" : "Đã chốt"} /> },
    { field: "expected_cash", headerName: "Tiền mặt phải có", width: 170, align: "right", headerAlign: "right", valueFormatter: money },
    { field: "difference", headerName: "Chênh lệch", width: 155, align: "right", headerAlign: "right", valueFormatter: (value) => value === null ? "—" : money(value) },
    { field: "detail", headerName: "Chi tiết", width: 100, sortable: false, filterable: false, renderCell: ({ row }) => <Button size="small" onClick={() => setSelectedShift(row)}>Xem ca</Button> },
  ];

  return <Stack spacing={3} sx={{ minWidth: 0 }}>
    <Stack direction={{ xs: "column", sm: "row" }} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" } }} spacing={1}>
      <Box><Typography variant="h5" fontWeight="bold">Thu tiền và chốt ca</Typography><Typography color="text.secondary">Theo dõi phiếu thu, hoàn tiền và đối chiếu tiền mặt cuối ca.</Typography></Box>
      <Button variant="outlined" startIcon={<RefreshIcon />} onClick={load} disabled={loading || mutating}>Làm mới</Button>
    </Stack>
    {notice && <Alert severity="success" onClose={() => setNotice("")}>{notice}</Alert>}
    {error && <Alert severity="error">{error}</Alert>}
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack spacing={2}>
        <Typography variant="h6">Ca của bạn</Typography>
        {loading && !currentShift ? <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><CircularProgress size={20} /><Typography>Đang tải ca làm việc…</Typography></Stack> : currentShift ? <>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
            <Typography color="text.secondary">Đang mở từ {formatBusinessTimestamp(currentShift.opened_at)}</Typography>
            <Chip size="small" color="success" label={`${currentShift.payment_count} giao dịch`} sx={{ alignSelf: "flex-start" }} />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={{ xs: 1.5, md: 4 }} divider={<Divider orientation="vertical" flexItem />}>
            {[["Tiền đầu ca", currentShift.opening_cash], ["Tiền mặt đã thu", currentShift.cash_receipts], ["Tiền mặt đã hoàn", currentShift.cash_refunds], ["Tiền mặt phải có", currentShift.expected_cash]].map(([label, value]) => <Box key={label}><Typography variant="body2" color="text.secondary">{label}</Typography><Typography variant="h6" sx={{ fontVariantNumeric: "tabular-nums" }}>{money(value)}</Typography></Box>)}
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ alignItems: { xs: "stretch", sm: "center" }, justifyContent: "space-between" }}>
            <Typography variant="body2" color="text.secondary">Tiền mặt phải có = đầu ca + thu tiền mặt − hoàn tiền mặt. Chuyển khoản được theo dõi riêng.</Typography>
            <Button variant="contained" disabled={loading || mutating || Boolean(error)} sx={{ flexShrink: 0 }} onClick={() => { setCountedCash(""); setFormError(""); setCloseDialog(true); }}>Kiểm đếm và chốt ca</Button>
          </Stack>
        </> : <>
          <Typography color="text.secondary">Chưa có ca đang mở. Mở ca trước khi thu tiền để đối soát cuối ca; giao dịch phát sinh trước đó được ghi ngoài ca.</Typography>
          <Box component="form" onSubmit={(event) => { event.preventDefault(); runMutation(() => financeService.openShift(parseCashAmount(openingCash)), "Đã mở ca. Các giao dịch tiếp theo của bạn sẽ được ghi vào ca này."); }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ alignItems: { xs: "stretch", sm: "flex-start" } }}>
              <TextField label="Tiền mặt đầu ca (đồng)" value={openingCash} onChange={(event) => setOpeningCash(event.target.value)} size="small" slotProps={{ htmlInput: { inputMode: "numeric", pattern: "[0-9]+" } }} helperText="Nhập số nguyên, ví dụ 100000" disabled={mutating} />
              <Button variant="contained" type="submit" disabled={loading || mutating || Boolean(error)}>Mở ca</Button>
            </Stack>
          </Box>
          {formError && !refund && !closeDialog && <Alert severity="error">{formError}</Alert>}
        </>}
      </Stack>
    </Paper>
    <Paper sx={{ minWidth: 0, overflow: "hidden" }}>
      <Tabs value={tab} onChange={(_, value) => setTab(value)} aria-label="Dữ liệu thu ngân" sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Tab label="Sổ giao dịch" id="finance-tab-payments" aria-controls="finance-panel-payments" />
        <Tab label="Lịch sử ca" id="finance-tab-shifts" aria-controls="finance-panel-shifts" />
      </Tabs>
      {tab === 0 ? <Box role="tabpanel" id="finance-panel-payments" aria-labelledby="finance-tab-payments" sx={{ p: { xs: 1.5, sm: 2.5 } }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 2 }}>
          <TextField select size="small" label="Nguồn thu" value={filters.source_type} onChange={changeFilter("source_type")} sx={{ minWidth: 150 }}><MenuItem value="">Tất cả nguồn</MenuItem><MenuItem value="parking_session">Lượt gửi xe</MenuItem><MenuItem value="monthly_pass">Vé tháng</MenuItem></TextField>
          <TextField select size="small" label="Giao dịch" value={filters.kind} onChange={changeFilter("kind")} sx={{ minWidth: 150 }}><MenuItem value="">Thu và hoàn</MenuItem><MenuItem value="receipt">Thu tiền</MenuItem><MenuItem value="refund">Hoàn tiền</MenuItem></TextField>
          <TextField type="date" size="small" label="Từ ngày" value={filters.date_from} onChange={changeFilter("date_from")} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField type="date" size="small" label="Đến ngày" value={filters.date_to} onChange={changeFilter("date_to")} slotProps={{ inputLabel: { shrink: true } }} />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{isManager ? "Hiển thị giao dịch của toàn bộ nhân viên." : "Hiển thị các giao dịch do bạn thực hiện."} Hoàn tiền được ghi nhận tại ngày thực hoàn.</Typography>
        <Box sx={{ height: 470, width: "100%" }}><DataGrid rows={payments.items} columns={paymentColumns} rowCount={payments.total} loading={loading} disableRowSelectionOnClick disableColumnFilter disableColumnSorting paginationMode="server" paginationModel={pagination} onPaginationModelChange={setPagination} pageSizeOptions={[10, 25, 50]} localeText={{ noRowsLabel: "Chưa có giao dịch trong khoảng đã chọn.", footerRowSelected: (count) => `${count} dòng đã chọn` }} sx={{ fontVariantNumeric: "tabular-nums" }} /></Box>
      </Box> : <Box role="tabpanel" id="finance-panel-shifts" aria-labelledby="finance-tab-shifts" sx={{ p: { xs: 1.5, sm: 2.5 } }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Ca đã chốt giữ nguyên số tiền kiểm đếm. {isManager ? "Bạn có thể xem ca của toàn bộ nhân viên." : "Danh sách chỉ gồm các ca của bạn."}</Typography>
        <Box sx={{ height: 470, width: "100%" }}><DataGrid rows={shifts.items} columns={shiftColumns} rowCount={shifts.total} loading={loading} disableRowSelectionOnClick disableColumnFilter disableColumnSorting paginationMode="server" paginationModel={shiftPagination} onPaginationModelChange={setShiftPagination} pageSizeOptions={[10, 25, 50]} localeText={{ noRowsLabel: "Chưa có ca làm việc." }} sx={{ fontVariantNumeric: "tabular-nums" }} /></Box>
      </Box>}
    </Paper>
    <Dialog open={closeDialog} onClose={() => { if (!mutating) setCloseDialog(false); }} fullWidth maxWidth="sm" aria-labelledby="close-shift-title">
      <DialogTitle id="close-shift-title">Kiểm đếm và chốt ca</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt: 1 }}><Typography>Kiểm đếm số tiền mặt thực tế trước khi chốt. Sau khi chốt, số tiền kiểm đếm của ca được giữ nguyên.</Typography><Typography>Tiền mặt phải có hiện tại: <strong>{money(currentShift?.expected_cash ?? 0)}</strong></Typography><TextField autoFocus label="Tiền mặt thực đếm (đồng)" value={countedCash} onChange={(event) => setCountedCash(event.target.value)} disabled={mutating} slotProps={{ htmlInput: { inputMode: "numeric" } }} helperText="Không tính số tiền chuyển khoản." />{formError && <Alert severity="error">{formError}</Alert>}</Stack></DialogContent>
      <DialogActions><Button disabled={mutating} onClick={() => setCloseDialog(false)}>Quay lại</Button><Button variant="contained" disabled={mutating || !countedCash.trim()} onClick={() => runMutation(() => financeService.closeShift(currentShift.id, parseCashAmount(countedCash)), "Đã chốt ca và lưu kết quả đối soát.", () => setCloseDialog(false))}>Xác nhận chốt ca</Button></DialogActions>
    </Dialog>
    <Dialog open={Boolean(refund)} onClose={() => { if (!mutating) setRefund(null); }} fullWidth maxWidth="sm" aria-labelledby="refund-title">
      <DialogTitle id="refund-title">Hoàn tiền từ phiếu thu</DialogTitle>
      {refund && <><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><Typography>Phiếu thu còn được hoàn: <strong>{money(refund.payment.refundable_amount)}</strong>. Tiền hoàn ghi vào ca đang mở của bạn; nếu chưa mở ca, giao dịch được ghi ngoài ca.</Typography><TextField autoFocus label="Số tiền hoàn (đồng)" value={refund.amount} onChange={(event) => setRefund({ ...refund, amount: event.target.value })} disabled={mutating} slotProps={{ htmlInput: { inputMode: "numeric" } }} /><TextField select label="Phương thức hoàn tiền" value={refund.method} onChange={(event) => setRefund({ ...refund, method: event.target.value })} disabled={mutating}><MenuItem value="cash">Tiền mặt</MenuItem><MenuItem value="transfer">Chuyển khoản</MenuItem></TextField><TextField label="Lý do hoàn tiền" multiline minRows={2} value={refund.reason} onChange={(event) => setRefund({ ...refund, reason: event.target.value })} disabled={mutating} slotProps={{ htmlInput: { maxLength: 500 } }} /><Typography variant="body2" color="text.secondary">Hoàn tiền không tự hủy hiệu lực vé tháng. Nếu khách ngừng sử dụng, cập nhật trạng thái vé trong mục Vé tháng.</Typography>{formError && <Alert severity="error">{formError}</Alert>}</Stack></DialogContent><DialogActions><Button disabled={mutating} onClick={() => setRefund(null)}>Quay lại</Button><Button variant="contained" color="warning" disabled={mutating || !refund.reason.trim()} onClick={() => runMutation(() => financeService.refund(refund.payment.id, buildRefundPayload({ ...refund, refundableAmount: refund.payment.refundable_amount })), "Đã ghi nhận hoàn tiền. Phiếu thu gốc được giữ nguyên.", () => setRefund(null))}>Xác nhận hoàn tiền</Button></DialogActions></>}
    </Dialog>
    <Dialog open={Boolean(selectedShift)} onClose={() => setSelectedShift(null)} fullWidth maxWidth="sm" aria-labelledby="shift-detail-title"><DialogTitle id="shift-detail-title">Đối soát ca làm việc</DialogTitle><DialogContent>{selectedShift && <Stack spacing={1.5}><Typography fontWeight="bold">{selectedShift.staff_name}</Typography><Typography color="text.secondary">{formatBusinessTimestamp(selectedShift.opened_at)} · {selectedShift.status === "closed" ? "Đã chốt" : "Đang mở"}</Typography>{[["Tiền đầu ca", selectedShift.opening_cash], ["Thu tiền mặt", selectedShift.cash_receipts], ["Hoàn tiền mặt", selectedShift.cash_refunds], ["Thu chuyển khoản", selectedShift.transfer_receipts], ["Hoàn chuyển khoản", selectedShift.transfer_refunds], ["Tiền mặt phải có", selectedShift.expected_cash], ["Tiền mặt thực đếm", selectedShift.counted_cash], ["Chênh lệch", selectedShift.difference]].map(([label, value]) => <Stack direction="row" sx={{ justifyContent: "space-between" }} spacing={2} key={label}><Typography>{label}</Typography><Typography fontWeight={label === "Chênh lệch" ? "bold" : "normal"} sx={{ fontVariantNumeric: "tabular-nums" }}>{value === null ? "Chưa chốt" : money(value)}</Typography></Stack>)}</Stack>}</DialogContent><DialogActions><Button onClick={() => setSelectedShift(null)}>Đóng</Button></DialogActions></Dialog>
  </Stack>;
}
