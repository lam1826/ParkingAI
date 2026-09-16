import { useCallback, useState } from "react";
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { dateTime, money, read, Records, RemoteSection, send, StateChip, useAction, useRemote } from "./shared";
import { channelLabel, REFUND_STATUS, refundDecisions, refundStatusLabel } from "./supportState";

const FILTERS = [["", "Đang chờ & đã xử lý"], ...Object.entries(REFUND_STATUS)];

/** Manager side: review, approve (amount ≤ server refundable), reject, and record an external refund with a reference. */
export default function RefundAdminPanel({ siteId, onChanged }) {
  const [status, setStatus] = useState("");
  const [dialog, setDialog] = useState(null);
  const [note, setNote] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("transfer");
  const [reference, setReference] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const load = useCallback(() => siteId ? read(`/sites/${siteId}/refund-requests`, status ? { status } : undefined).then((data) => Array.isArray(data) ? data : data.items) : Promise.resolve([]), [siteId, status]);
  const remote = useRemote(load);
  const dialogRow = dialog ? dialog.row : null;
  const detailLoad = useCallback(() => dialogRow && !dialogRow.legacy ? read(`/sites/${siteId}/refund-requests/${dialogRow.id}`) : Promise.resolve(null), [siteId, dialogRow]);
  const detail = useRemote(detailLoad);
  const action = useAction(async () => { await remote.reload(); await onChanged?.(); });
  const open = (kind, row) => { setDialog({ kind, row }); setNote(""); setAmount(""); setMethod("transfer"); setReference(""); setConfirmed(false); };
  const submit = (event) => {
    event.preventDefault();
    const { kind, row } = dialog;
    const base = row.legacy ? `/portal/admin/refund-requests/${row.id}` : `/sites/${siteId}/refund-requests/${row.id}`;
    let path, body;
    if (row.legacy) { path = `${base}/resolve`; body = { approve: kind === "approve", note }; }
    else if (kind === "record") { path = `${base}/record-refund`; body = { method, external_reference: reference.trim() || null, confirmed: true }; }
    else { path = `${base}/${kind}`; body = { note, ...(kind === "approve" && amount !== "" ? { amount: Number(amount) } : {}) }; }
    void action.run(() => send(path, body), "Đã ghi nhận quyết định.", () => setDialog(null));
  };
  const state = detail.data?.refund_state;
  const titles = { review: "Bắt đầu xem xét", approve: "Duyệt yêu cầu hoàn", reject: "Từ chối yêu cầu hoàn", record: "Ghi nhận đã hoàn tiền ngoài hệ thống" };
  return <Stack spacing={2}>
    <Alert severity="info">Số tiền có thể hoàn do máy chủ tính từ phiếu thu gốc trừ các khoản đã hoàn. Duyệt là quyết định; tiền chỉ được ghi vào sổ khi ghi nhận hoàn (khoản DEMO được hoàn mô phỏng ngay khi duyệt).</Alert>
    {action.error && <Alert severity="error">{action.error}</Alert>}
    {action.notice && <Alert severity="success" role="status">{action.notice}</Alert>}
    <TextField select size="small" label="Trạng thái" value={status} onChange={(event) => setStatus(event.target.value)} sx={{ maxWidth: 260 }}>{FILTERS.map(([key, label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}</TextField>
    <RemoteSection remote={remote} title="Yêu cầu hoàn tiền" description="Hàng có nhãn Lịch sử là yêu cầu DEMO của phiên bản trước; chỉ duyệt/từ chối được.">
      {(rows) => <Records rows={rows} columns={[
        { key: "created_at", label: "Ngày gửi", render: (row) => dateTime(row.created_at) },
        { key: "customer_name", label: "Khách" },
        { key: "payment_channel", label: "Kênh", render: (row) => <>{channelLabel(row.payment_channel)}{row.legacy ? " · Lịch sử" : ""}</> },
        { key: "requested_amount", label: "Có thể hoàn", render: (row) => row.requested_amount == null ? "—" : money(row.requested_amount) },
        { key: "approved_amount", label: "Đã duyệt", render: (row) => row.approved_amount == null ? "—" : money(row.approved_amount) },
        { key: "reason", label: "Lý do của khách" },
        { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={refundStatusLabel(row)} /> },
        { key: "action", label: "Xử lý", render: (row) => {
          const can = row.legacy ? { review: false, approve: row.status === "pending", reject: row.status === "pending", record: false } : refundDecisions(row);
          return <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            {can.review && <Button size="small" disabled={action.busy} onClick={() => open("review", row)}>Xem xét</Button>}
            {can.approve && <Button size="small" disabled={action.busy} onClick={() => open("approve", row)}>Duyệt</Button>}
            {can.record && <Button size="small" variant="contained" disabled={action.busy} onClick={() => open("record", row)}>Ghi nhận đã hoàn</Button>}
            {can.reject && <Button size="small" color="error" disabled={action.busy} onClick={() => open("reject", row)}>Từ chối</Button>}
            {!can.review && !can.approve && !can.record && !can.reject && "—"}
          </Stack>;
        } },
      ]} empty="Không có yêu cầu hoàn ở trạng thái này." />}
    </RemoteSection>
    <Dialog open={Boolean(dialog)} onClose={() => { if (!action.busy) setDialog(null); }} fullWidth maxWidth="sm" aria-labelledby="refund-decision-title">
      {dialog && <Box component="form" onSubmit={submit}>
        <DialogTitle id="refund-decision-title">{titles[dialog.kind]}</DialogTitle>
        <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
          <Typography>{dialog.row.customer_name} · {channelLabel(dialog.row.payment_channel)} · Lý do: {dialog.row.reason}</Typography>
          {detail.loading && <Typography role="status" color="text.secondary">Đang tải phiếu thu…</Typography>}
          {state && <Typography>Phiếu thu {money(state.amount)} · đã hoàn {money(state.refunded_amount)} · <strong>còn có thể hoàn {money(state.refundable_amount)}</strong>{state.blocked_label ? ` · ${state.blocked_label}` : ""}</Typography>}
          {dialog.kind === "approve" && !dialog.row.legacy && <TextField label="Số tiền duyệt hoàn (đồng)" type="number" value={amount} onChange={(event) => setAmount(event.target.value)} helperText={`Để trống để duyệt toàn bộ ${money(state?.refundable_amount ?? dialog.row.requested_amount)}. Không được vượt số còn có thể hoàn.`} slotProps={{ htmlInput: { min: 1, max: state?.refundable_amount ?? dialog.row.requested_amount, step: 1 } }} />}
          {dialog.kind === "record" && <>
            <Typography>Số tiền đã duyệt: <strong>{money(dialog.row.approved_amount)}</strong>. Ghi nhận này tạo phiếu hoàn trong sổ thu; hệ thống không tự chuyển tiền qua ngân hàng.</Typography>
            <TextField select label="Hình thức đã hoàn" value={method} onChange={(event) => setMethod(event.target.value)}><MenuItem value="transfer">Chuyển khoản</MenuItem><MenuItem value="cash">Tiền mặt</MenuItem></TextField>
            <TextField label={method === "transfer" ? "Mã tham chiếu giao dịch ngân hàng" : "Tham chiếu / ghi chú (tuỳ chọn)"} required={method === "transfer"} value={reference} onChange={(event) => setReference(event.target.value)} slotProps={{ htmlInput: { maxLength: 120 } }} />
          </>}
          {dialog.kind !== "record" && <TextField label={dialog.kind === "reject" ? "Lý do từ chối (khách sẽ thấy)" : "Ghi chú xử lý"} required={dialog.kind === "reject"} value={note} onChange={(event) => setNote(event.target.value)} multiline minRows={2} slotProps={{ htmlInput: { maxLength: 500 } }} />}
          <FormControlLabel control={<Checkbox checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />} label={dialog.kind === "record" ? "Tôi xác nhận đã hoàn tiền cho khách theo hình thức trên" : "Tôi đã kiểm tra phiếu thu và quyền sử dụng liên quan"} />
          {action.error && <Alert severity="error">{action.error}</Alert>}
        </Stack></DialogContent>
        <DialogActions><Button disabled={action.busy} onClick={() => setDialog(null)}>Quay lại</Button><Button type="submit" variant="contained" disabled={action.busy || !confirmed || (dialog.kind === "reject" && note.trim().length < 3)}>Xác nhận</Button></DialogActions>
      </Box>}
    </Dialog>
  </Stack>;
}
