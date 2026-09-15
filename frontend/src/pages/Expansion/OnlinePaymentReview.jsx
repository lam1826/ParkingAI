import { useCallback, useState, useSyncExternalStore } from "react";
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { createPortalOrderFlow } from "./portalOrderFlow";
import { dateTime, money, PageControls, read, Records, RemoteSection, requestKey, send, useRemote } from "./shared";

const reasonLabel = (reason) => ({ unknown_order: "Chưa tìm thấy đơn", late_or_closed_order: "Tiền đến khi đơn đã đóng hoặc hết hạn", capacity_hold_expired: "Chỗ giữ đã hết hạn", additional_payment: "Có khoản chuyển thêm", payment_identity_mismatch: "Thông tin hoặc số tiền chưa khớp", provider_identity_mismatch: "Thông tin cổng thanh toán chưa khớp", account_mismatch: "Tài khoản nhận chưa khớp", partial_payment: "Chưa đủ số tiền", reference_conflict: "Mã giao dịch có thông tin khác nhau", payment_total_requires_review: "Cần kiểm tra các khoản chuyển", channel_changed: "Cấu hình nhận tiền đã thay đổi", session_no_longer_active: "Lượt gửi đã kết thúc", late_or_closed_quote: "Tiền đến khi đề nghị đã đóng hoặc hết hạn", session_identity_changed: "Thông tin lượt gửi đã thay đổi", session_owner_changed: "Quyền sở hữu lượt gửi đã thay đổi", session_credit_changed: "Khoản đã trả của lượt gửi đã thay đổi" })[reason] || "Cần kiểm tra giao dịch";
const evidenceAmount = (row) => row.currency === "VND" ? money(row.amount) : `${row.amount} ${row.currency || "(chưa xác định tiền tệ)"}`;
const sourceLabel = (row) => row.session_id ? `Lượt gửi ${row.session_id}` : row.order_id ? `Đơn vé ${row.order_id}` : "Chưa khớp nguồn thanh toán";

function DecisionDialog({ row, siteId, onClose, onSaved }) {
  const [form, setForm] = useState({ action: "note", reason: "", external_reference: "", confirmed: false });
  const [flow] = useState(() => {
    const token = localStorage.getItem("token");
    return createPortalOrderFlow({ createKey: requestKey, isAuthorized: () => Boolean(token) && localStorage.getItem("token") === token,
      createOrder: async (body) => { const decision = await send(`/sites/${siteId}/online-payments/review/${row.id}/decisions`, body); return { id: decision.id, status: "recorded", decision }; },
      onCreated: onSaved });
  });
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const busy = state.phase === "submitting", locked = busy || state.phase === "uncertain", complete = state.phase === "completed";
  const refund = form.action === "confirmed_external_refund";
  const submit = (event) => {
    event.preventDefault();
    void flow.submit((key) => {
      if (form.reason.trim().length < 3) throw new Error("Ghi lý do đối soát với ít nhất 3 ký tự.");
      if (refund && (!form.confirmed || form.external_reference.trim().length < 3)) throw new Error("Nhập mã chứng từ và xác nhận đã hoàn tiền ngoài hệ thống.");
      return { action: form.action, request_id: key, reason: form.reason.trim(), confirmed: refund && form.confirmed,
        ...(refund ? { refund_amount: row.amount, external_reference: form.external_reference.trim() } : {}) };
    });
  };
  const edit = (name) => (event) => setForm((old) => ({ ...old, [name]: event.target.value }));
  return <Dialog open onClose={() => { if (!locked) onClose(); }} fullWidth maxWidth="sm" aria-labelledby="online-review-title">
    <Box component="form" onSubmit={submit}><DialogTitle id="online-review-title">Ghi nhận đối soát chuyển khoản</DialogTitle><DialogContent>
      <Stack spacing={2} sx={{ pt: 1 }}>
        <Typography sx={{ overflowWrap: "anywhere" }}>Giao dịch {row.reference} · <strong>{evidenceAmount(row)}</strong></Typography>
        <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{sourceLabel(row)}</Typography>
        <Typography color="text.secondary">{reasonLabel(row.reason)}</Typography>
        {row.decisions?.length > 0 && <Box><Typography fontWeight={600}>Lịch sử đối soát</Typography>{row.decisions.map((decision) => <Box key={decision.id} sx={{ mt: 1, overflowWrap: "anywhere" }}>
          <Typography variant="body2" color="text.secondary">{dateTime(decision.created_at)} · {decision.actor_username || `Quản lý #${decision.actor_id}`}</Typography>
          <Typography>{decision.reason}</Typography>
          {decision.external_reference && <Typography variant="body2">Chứng từ hoàn ngoài hệ thống: {decision.external_reference} · {money(decision.refund_amount)}</Typography>}
        </Box>)}</Box>}
        {state.error && <Alert severity={locked ? "warning" : "error"}>{state.error}</Alert>}
        {complete ? <Alert severity="success">Đã lưu quyết định đối soát. Hệ thống không thực hiện chuyển tiền qua ngân hàng.</Alert> : <>
          <TextField select label="Nội dung ghi nhận" value={form.action} onChange={edit("action")} disabled={locked}>
            <MenuItem value="note">Ghi chú kết quả kiểm tra</MenuItem>
            {row.resolution !== "external_refund_recorded" && row.currency === "VND" && <MenuItem value="confirmed_external_refund">Xác nhận đã hoàn ngoài hệ thống</MenuItem>}
          </TextField>
          <TextField required label="Lý do / kết quả kiểm tra" value={form.reason} onChange={edit("reason")} disabled={locked}
            multiline minRows={3} inputProps={{ minLength: 3, maxLength: 500 }} />
          {refund && <>
            <Alert severity="warning">Chỉ ghi nhận sau khi đã kiểm tra chứng từ hoàn đủ {money(row.amount)}. Thao tác này lưu lịch sử, không gửi lệnh hoàn tiền và không thu hồi vé đã cấp.</Alert>
            <TextField required label="Mã chứng từ hoàn ngoài hệ thống" value={form.external_reference} onChange={edit("external_reference")} disabled={locked} inputProps={{ minLength: 3, maxLength: 100 }} />
            <FormControlLabel control={<Checkbox checked={form.confirmed} disabled={locked} onChange={(event) => setForm((old) => ({ ...old, confirmed: event.target.checked }))} />}
              label="Tôi đã xác minh khoản hoàn và chứng từ ngoài hệ thống" />
          </>}
        </>}
      </Stack>
    </DialogContent><DialogActions><Button disabled={locked} onClick={onClose}>{complete ? "Đóng" : "Quay lại"}</Button>
      {!complete && <Button type="submit" variant="contained" disabled={busy}>{busy ? "Đang ghi nhận…" : state.phase === "uncertain" ? "Thử lại xác nhận đã gửi" : "Lưu quyết định"}</Button>}
    </DialogActions></Box>
  </Dialog>;
}

function SiteReview({ siteId }) {
  const [page, setPage] = useState(0), [selected, setSelected] = useState(null);
  const load = useCallback(() => read(`/sites/${siteId}/online-payments/review`, { limit: 50, offset: page * 50 }), [siteId, page]);
  const remote = useRemote(load);
  return <>
    <RemoteSection remote={remote} title="Chuyển khoản cần đối soát" description="Khoản đến muộn, sai thông tin hoặc chuyển thêm được giữ lại để kiểm tra. Ghi chú và chứng từ hoàn ngoài hệ thống không tạo khoản thu mới.">
      {(data) => <><Records rows={data.items || []} empty="Chưa có chuyển khoản cần đối soát." columns={[
        { key: "reference", label: "Mã giao dịch", render: (row) => <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{row.reference}</Typography> },
        { key: "amount", label: "Số tiền", render: evidenceAmount },
        { key: "source", label: "Nguồn", render: (row) => <Typography variant="body2" sx={{ maxWidth: 230, overflowWrap: "anywhere" }}>{sourceLabel(row)}</Typography> },
        { key: "reason", label: "Cần kiểm tra", render: (row) => reasonLabel(row.reason) },
        { key: "received_at", label: "Tiếp nhận", render: (row) => dateTime(row.received_at) },
        { key: "resolution", label: "Đối soát", render: (row) => row.resolution === "external_refund_recorded" ? "Đã ghi nhận hoàn ngoài hệ thống" : "Đang kiểm tra" },
        { key: "action", label: "Xử lý", render: (row) => <Button size="small" onClick={() => setSelected(row)}>Ghi nhận đối soát</Button> },
      ]} /><PageControls page={page} count={data.items?.length || 0} size={50} busy={remote.loading} onChange={setPage} /></>}
    </RemoteSection>
    {selected && <DecisionDialog key={selected.id} row={selected} siteId={siteId} onClose={() => setSelected(null)} onSaved={() => void remote.reload()} />}
  </>;
}

export default function OnlinePaymentReview({ sites }) {
  const [choice, setChoice] = useState("");
  const siteId = sites.some((site) => String(site.id) === String(choice)) ? choice : sites[0]?.id;
  if (!siteId) return <Alert severity="info">Chưa có bãi được cấp quyền để đối soát.</Alert>;
  return <>
    {sites.length > 1 && <TextField select label="Bãi cần đối soát" value={siteId} onChange={(event) => setChoice(event.target.value)}>
      {sites.map((site) => <MenuItem key={site.id} value={site.id}>{site.name}</MenuItem>)}
    </TextField>}
    <SiteReview key={siteId} siteId={siteId} />
  </>;
}
