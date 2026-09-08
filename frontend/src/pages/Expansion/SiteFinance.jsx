import { useCallback, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { combineRemotes, dateTime, endpoint, formLayout, money, PageControls, read, Records, refreshAll, RemoteSection, requestKey, Section, send, useAction, usePage, useRemote } from "./shared";

const methods = { cash: "Tiền mặt", transfer: "Chuyển khoản", demo: "QR mô phỏng", legacy_unknown: "Lịch sử" };
const amountValid = (value, positive = false) => /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) >= (positive ? 1 : 0);

export default function SiteFinance({ site }) {
  const prefix = `/sites/${site.id}`;
  const manager = ["admin", "manager"].includes(site.role);
  const [opening, setOpening] = useState("0");
  const [dialog, setDialog] = useState(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [method, setMethod] = useState("cash");
  const [dates, setDates] = useState({ from: "", to: "" });
  const paymentsPage = usePage({ from: "", to: "" });
  const shiftsPage = usePage();
  const from = paymentsPage.filters.from, to = paymentsPage.filters.to;
  const loadShifts = useCallback(() => read(`${prefix}/cash-shifts`, { page: shiftsPage.page + 1, size: 25 }), [prefix, shiftsPage.page]);
  const loadPayments = useCallback(() => read(`${prefix}/payments`, { page: paymentsPage.page + 1, size: 25, date_from: from || undefined, date_to: to || undefined }), [prefix, paymentsPage.page, from, to]);
  const loadRevenue = useCallback(() => read(`${prefix}/revenue`, { date_from: from || undefined, date_to: to || undefined }), [prefix, from, to]);
  const shifts = useRemote(loadShifts), payments = useRemote(loadPayments), revenue = useRemote(loadRevenue);
  const remote = combineRemotes(shifts, payments, revenue);
  const action = useAction(refreshAll(shifts, payments, revenue));
  const downloads = useAction();
  const openDialog = (kind, row) => { setDialog({ kind, row, key: requestKey() }); setAmount(""); setReason(""); setMethod("cash"); };
  const download = (row) => downloads.run(async () => {
    const response = await api.get(endpoint(`${prefix}/payments/${row.id}/pdf`), { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `ParkingAI-${row.method === "demo" ? "DEMO-" : ""}${row.id}.pdf`;
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, "Đã tải chứng từ.");
  const refund = dialog?.kind === "refund";
  const valid = amountValid(amount, refund) && (!refund || (Number(amount) <= dialog.row.refundable_amount && !!reason.trim()));
  return <Stack spacing={3}>
    <Alert severity="info">{manager ? "Thu và hoàn tiền trong bãi đang chọn." : "Bạn xem và chốt ca của mình, cùng các khoản do bạn thu hoặc hoàn."} Mỗi nhân viên có tối đa một ca mở trên toàn hệ thống.</Alert>
    {[action, downloads].map((item, index) => (item.error || item.notice) && <Box key={index}>{item.error && <Alert severity="error">{item.error}</Alert>}{item.notice && <Alert severity="success" role="status">{item.notice}</Alert>}</Box>)}
    <Section title="Mở ca thu tiền"><Box component="form" sx={formLayout} onSubmit={(event) => {
      event.preventDefault(); if (!amountValid(opening)) return;
      void action.run(() => send(`${prefix}/cash-shifts`, { opening_cash: Number(opening) }), "Đã mở ca tại bãi này.");
    }}><TextField label="Tiền mặt đầu ca (₫)" value={opening} onChange={(event) => setOpening(event.target.value)} required slotProps={{ htmlInput: { inputMode: "numeric", pattern: "[0-9]+", maxLength: 15 } }} /><Button type="submit" variant="contained" disabled={action.busy || !amountValid(opening)}>Mở ca tại bãi này</Button></Box></Section>
    <RemoteSection remote={shifts} title="Ca thu tiền" actions={<Button disabled={remote.loading || action.busy} onClick={remote.reload}>Làm mới</Button>}>{(data) => <>
      <Records rows={data.items} columns={[
        { key: "staff_name", label: "Nhân viên" }, { key: "opened_at", label: "Mở ca", render: (row) => dateTime(row.opened_at) },
        { key: "status", label: "Trạng thái", render: (row) => row.status === "open" ? "Đang mở" : "Đã chốt" },
        { key: "expected_cash", label: "Tiền mặt theo sổ", render: (row) => money(row.expected_cash) },
        { key: "difference", label: "Chênh lệch", render: (row) => row.difference == null ? "Chưa chốt" : money(row.difference) },
        { key: "close", label: "Thao tác", render: (row) => row.status === "open" && <Button disabled={action.busy} onClick={() => openDialog("close", row)}>Kiểm đếm / chốt ca</Button> },
      ]} /><PageControls page={shiftsPage.page} count={data.items.length} busy={shifts.loading || action.busy} size={25} onChange={shiftsPage.setPage} />
    </>}</RemoteSection>
    <Section title="Khoảng tra cứu chứng từ"><Box component="form" sx={formLayout} onSubmit={(event) => { event.preventDefault(); paymentsPage.setFilters(dates); }}>
      <TextField label="Từ ngày" type="date" value={dates.from} onChange={(event) => setDates({ ...dates, from: event.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
      <TextField label="Đến ngày" type="date" value={dates.to} onChange={(event) => setDates({ ...dates, to: event.target.value })} slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: dates.from || undefined } }} />
      <Button type="submit" variant="outlined" disabled={action.busy}>Tra cứu</Button>
    </Box><Typography variant="body2" color="text.secondary">Để trống ngày: xem mọi chứng từ; tổng thu bên dưới hiển thị hôm nay.</Typography></Section>
    <RemoteSection remote={revenue} title="Tổng thu sau hoàn">{(data) => <>
      <Typography>{data.date_from} → {data.date_to}: <strong>{money(data.total_revenue)}</strong></Typography>
      <Typography>Chưa thuộc ca: <strong>{money(data.unassigned_revenue)}</strong></Typography><Typography variant="body2" color="text.secondary">{data.note}</Typography>
    </>}</RemoteSection>
    <RemoteSection remote={payments} title="Chứng từ thu / hoàn">{(data) => <>
      <Records rows={data.items} columns={[
        { key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) },
        { key: "kind", label: "Loại", render: (row) => row.kind === "refund" ? "Hoàn" : "Thu" },
        { key: "amount", label: "Số tiền", render: (row) => money(row.amount) },
        { key: "method", label: "Phương thức", render: (row) => methods[row.method] || row.method },
        { key: "shift_id", label: "Ca", render: (row) => row.shift_id ? row.shift_id.slice(0, 8) : "Chưa thuộc ca" },
        { key: "actions", label: "Thao tác", render: (row) => <Stack direction="row"><Button disabled={downloads.busy} onClick={() => void download(row)}>PDF</Button>
          {manager && row.kind === "receipt" && row.method !== "demo" && row.refundable_amount > 0 && <Button disabled={action.busy} onClick={() => openDialog("refund", row)}>Hoàn tiền</Button>}</Stack> },
      ]} /><PageControls page={paymentsPage.page} count={data.items.length} busy={payments.loading || action.busy} size={25} onChange={paymentsPage.setPage} />
    </>}</RemoteSection>
    <Dialog open={!!dialog} onClose={() => { if (!action.busy) setDialog(null); }} fullWidth maxWidth="sm">
      <Box component="form" onSubmit={(event) => {
        event.preventDefault(); if (!valid || !dialog) return;
        const path = refund ? `/payments/${dialog.row.id}/refund` : `/cash-shifts/${dialog.row.id}/close`;
        const body = refund ? { amount: Number(amount), reason: reason.trim(), method, idempotency_key: dialog.key } : { counted_cash: Number(amount) };
        void action.run(() => send(prefix + path, body), refund ? "Đã ghi nhận chứng từ hoàn tiền." : "Đã chốt ca.", () => setDialog(null));
      }}>
        <DialogTitle>{refund ? "Xác nhận hoàn tiền" : "Kiểm đếm và chốt ca"}</DialogTitle>
        <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
          <Typography>{refund ? `Có thể hoàn tối đa ${money(dialog?.row.refundable_amount)}. Chứng từ thu gốc được giữ nguyên.` : `Tiền mặt theo sổ: ${money(dialog?.row.expected_cash)}. Nhập số đã kiểm đếm thực tế; ca đã chốt không sửa lại.`}</Typography>
          {action.error && <Alert severity="error">{action.error}</Alert>}
          <TextField autoFocus label={refund ? "Số tiền hoàn (₫)" : "Tiền mặt thực đếm (₫)"} value={amount} onChange={(event) => setAmount(event.target.value)} required slotProps={{ htmlInput: { inputMode: "numeric", pattern: "[0-9]+", maxLength: 15 } }} disabled={action.busy} />
          {refund && <><TextField select label="Phương thức hoàn" value={method} onChange={(event) => setMethod(event.target.value)} disabled={action.busy}><MenuItem value="cash">Tiền mặt</MenuItem><MenuItem value="transfer">Chuyển khoản</MenuItem></TextField><TextField label="Lý do hoàn" value={reason} onChange={(event) => setReason(event.target.value)} required slotProps={{ htmlInput: { maxLength: 500 } }} disabled={action.busy} /></>}
        </Stack></DialogContent>
        <DialogActions><Button disabled={action.busy} onClick={() => setDialog(null)}>Quay lại</Button><Button type="submit" variant="contained" disabled={action.busy || !valid}>{action.busy ? "Đang xác nhận…" : refund ? "Xác nhận đã hoàn tiền" : "Xác nhận chốt ca"}</Button></DialogActions>
      </Box>
    </Dialog>
  </Stack>;
}
