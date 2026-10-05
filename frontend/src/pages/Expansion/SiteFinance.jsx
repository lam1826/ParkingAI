import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { combineRemotes, dateTime, endpoint, formLayout, money, PageControls, read, Records, refreshAll, RemoteSection, requestKey, Section, send, useAction, usePage, useRemote } from "./shared";
import { beginRefundAttempt, directRefundAction, loadPendingRefunds, onRefundSettled, PENDING_REFUND_NOTICE, REFUND_ANSWERED_NOTICE, refundDialogState, refundFailure, refundOutcomeUncertain, refundRetryAnswered, settleRefundAttempt } from "./siteFinanceRefund";

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
  const reloadAll = refreshAll(shifts, payments, revenue);
  // Keys this instance is sending: it reports their outcome itself.
  const sending = useRef(new Set());
  const { reload: reloadShifts } = shifts, { reload: reloadPayments } = payments, { reload: reloadRevenue } = revenue;
  useEffect(() => onRefundSettled(({ key }) => {
    // A refund sent by an instance replaced meanwhile (header "Làm mới" #73, navigation) settled late:
    // the receipt rows and totals on screen are stale.
    if (!sending.current.has(key)) void Promise.all([reloadShifts(), reloadPayments(), reloadRevenue()]);
  }), [reloadShifts, reloadPayments, reloadRevenue]);
  const action = useAction(reloadAll);
  const downloads = useAction();
  const openDialog = (kind, row) => {
    if (kind !== "refund") { setDialog({ kind, row, key: requestKey() }); setAmount(""); setReason(""); setMethod("cash"); return; }
    // Read the shared store on every open, never a copy taken at mount: an attempt sent by a replaced
    // instance may have settled since (review INT2-MONEY).
    const pendingRefunds = loadPendingRefunds();
    const state = refundDialogState(pendingRefunds, row.id, requestKey);
    setDialog({ kind, row, key: state.key, uncertain: state.uncertain }); setAmount(state.amount); setReason(state.reason); setMethod(state.method);
  };
  const submitRefund = (row, attempt) => async () => {
    const body = { amount: attempt.amount, reason: attempt.reason, method: attempt.method, idempotency_key: attempt.key };
    // A retry of an attempt whose outcome is unknown: its key is still stored.
    const retry = loadPendingRefunds()[row.id]?.key === attempt.key;
    // Stored before sending and settled in the shared store: a remount (header "Làm mới" #73,
    // navigation) or a reload while the request is in flight cannot drop the key, and an outcome
    // that arrives after this instance unmounted reaches the visible instance (onRefundSettled).
    sending.current.add(attempt.key);
    beginRefundAttempt(loadPendingRefunds(), row.id, attempt);
    const finish = (failure) => {
      const old = loadPendingRefunds();
      settleRefundAttempt(old, row.id, attempt, failure);
    };
    try {
      const result = await send(`${prefix}/payments/${row.id}/refund`, body);
      finish();
      return result;
    } catch (failure) {
      finish(failure);
      // A refused retry: the earlier attempt may have consumed the key, so the dialog closes (the
      // refusal stays on the page) and a reopened one starts from the reloaded row with a fresh key.
      if (retry && !refundOutcomeUncertain(failure)) setDialog(null);
      // The row may already be refunded: never leave its stale balance on screen.
      void reloadAll();
      throw refundFailure(failure);
    } finally {
      sending.current.delete(attempt.key);
    }
  };
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
    </Box><Typography variant="body2" color="text.secondary">Để trống cả hai ngày: xem mọi chứng từ; tổng thu bên dưới hiển thị hôm nay. Chỉ nhập một ngày: tổng thu tính cùng khoảng mở như danh sách chứng từ.</Typography></Section>
    <RemoteSection remote={revenue} title="Tổng thu sau hoàn">{(data) => <>
      <Typography>{data.date_from || "Từ đầu"} → {data.date_to || "nay"}: <strong>{money(data.total_revenue)}</strong></Typography>
      <Typography>Chưa thuộc ca: <strong>{money(data.unassigned_revenue)}</strong></Typography><Typography variant="body2" color="text.secondary">{data.note}</Typography>
    </>}</RemoteSection>
    <RemoteSection remote={payments} title="Chứng từ thu / hoàn">{(data) => <>
      <Records rows={data.items} columns={[
        { key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) },
        { key: "kind", label: "Loại", render: (row) => row.kind === "refund" ? "Hoàn" : "Thu" },
        { key: "amount", label: "Số tiền", render: (row) => money(row.amount) },
        { key: "method", label: "Phương thức", render: (row) => methods[row.method] || row.method },
        { key: "shift_id", label: "Ca", render: (row) => row.shift_id ? row.shift_id.slice(0, 8) : "Chưa thuộc ca" },
        { key: "actions", label: "Thao tác", render: (row) => { const refundChoice = directRefundAction(row, manager); return <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}><Button disabled={downloads.busy} onClick={() => void download(row)}>PDF</Button>
          {refundChoice.kind === "refund" && <Button disabled={action.busy} onClick={() => openDialog("refund", row)}>{refundChoice.label}</Button>}
          {refundChoice.kind === "blocked" && <Typography variant="body2" color="text.secondary">{refundChoice.label}</Typography>}</Stack>; } },
      ]} /><PageControls page={paymentsPage.page} count={data.items.length} busy={payments.loading || action.busy} size={25} onChange={paymentsPage.setPage} />
    </>}</RemoteSection>
    <Dialog open={!!dialog} onClose={() => { if (!action.busy) setDialog(null); }} fullWidth maxWidth="sm">
      <Box component="form" onSubmit={(event) => {
        event.preventDefault(); if (!valid || !dialog) return;
        if (refund) {
          if (refundRetryAnswered(dialog, loadPendingRefunds())) {
            // The unconfirmed attempt this dialog retries was answered meanwhile (late reply to a replaced
            // instance, whose lists were reloaded then): its key must not carry this content.
            setDialog(null); action.notify(REFUND_ANSWERED_NOTICE); return;
          }
          const attempt = { key: dialog.key, amount: Number(amount), reason: reason.trim(), method };
          void action.run(submitRefund(dialog.row, attempt), "Đã ghi nhận chứng từ hoàn tiền.", () => setDialog(null));
          return;
        }
        void action.run(() => send(`${prefix}/cash-shifts/${dialog.row.id}/close`, { counted_cash: Number(amount) }), "Đã chốt ca.", () => setDialog(null));
      }}>
        <DialogTitle>{refund ? "Xác nhận hoàn tiền" : "Kiểm đếm và chốt ca"}</DialogTitle>
        <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
          <Typography>{refund ? `Có thể hoàn tối đa ${money(dialog?.row.refundable_amount)}. Chứng từ thu gốc được giữ nguyên.` : `Tiền mặt theo sổ: ${money(dialog?.row.expected_cash)}. Nhập số đã kiểm đếm thực tế; ca đã chốt không sửa lại.`}</Typography>
          {refund && dialog?.row.direct_refund_revokes_ticket && <Alert severity="warning">Vé giờ/ngày chưa sử dụng sẽ bị thu hồi và chỗ giữ sẽ bị hủy, kể cả khi chỉ hoàn một phần.</Alert>}
          {refund && dialog?.uncertain && <Alert severity="warning">{PENDING_REFUND_NOTICE}</Alert>}
          {action.error && <Alert severity="error">{action.error}</Alert>}
          <TextField autoFocus label={refund ? "Số tiền hoàn (₫)" : "Tiền mặt thực đếm (₫)"} value={amount} onChange={(event) => setAmount(event.target.value)} required slotProps={{ htmlInput: { inputMode: "numeric", pattern: "[0-9]+", maxLength: 15 } }} disabled={action.busy} />
          {refund && <><TextField select label="Phương thức hoàn" value={method} onChange={(event) => setMethod(event.target.value)} disabled={action.busy}><MenuItem value="cash">Tiền mặt</MenuItem><MenuItem value="transfer">Chuyển khoản</MenuItem></TextField><TextField label="Lý do hoàn" value={reason} onChange={(event) => setReason(event.target.value)} required slotProps={{ htmlInput: { maxLength: 500 } }} disabled={action.busy} /></>}
        </Stack></DialogContent>
        <DialogActions><Button disabled={action.busy} onClick={() => setDialog(null)}>Quay lại</Button><Button type="submit" variant="contained" disabled={action.busy || !valid}>{action.busy ? "Đang xác nhận…" : refund ? "Xác nhận đã hoàn tiền" : "Xác nhận chốt ca"}</Button></DialogActions>
      </Box>
    </Dialog>
  </Stack>;
}
