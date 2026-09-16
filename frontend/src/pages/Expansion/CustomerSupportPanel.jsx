import { useCallback, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { dateTime, formLayout, items, money, read, Records, RemoteSection, Section, send, StateChip, useAction, useRemote } from "./shared";
import { categoryLabel, channelLabel, LINK_LABEL, refundStatusLabel, SUPPORT_CATEGORIES, supportStatusLabel } from "./supportState";

const EMPTY = { subject: "", category: "general", message: "", linked_type: "", linked_id: "" };

function Thread({ detail }) {
  return <Stack spacing={1.5}>
    {detail.messages.map((row) => <Box key={row.id} sx={{ p: 1.5, borderRadius: 1, bgcolor: row.mine ? "primary.50" : "grey.100", alignSelf: row.mine ? "flex-end" : "flex-start", maxWidth: "100%", minWidth: { sm: 280 } }}>
      <Typography variant="caption" color="text.secondary">{row.mine ? "Bạn" : row.author_role === "customer" ? "Khách" : "Quản lý"} · {dateTime(row.created_at)}</Typography>
      <Typography sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.body}</Typography>
    </Box>)}
  </Stack>;
}

/** Customer side: create support requests (optionally linked to own order/session/receipt), follow replies, see refund requests. */
export default function CustomerSupportPanel({ linked, orders, sessions, receipts, refunds, onChanged }) {
  const [form, setForm] = useState(EMPTY);
  const [selected, setSelected] = useState(null);
  const [reply, setReply] = useState("");
  const loadRequests = useCallback(() => linked ? read("/me/support-requests").then(items) : Promise.resolve([]), [linked]);
  const requests = useRemote(loadRequests);
  const detailLoad = useCallback(() => selected ? read(`/me/support-requests/${encodeURIComponent(selected)}`) : Promise.resolve(null), [selected]);
  const detail = useRemote(detailLoad);
  const action = useAction(async () => { await requests.reload(); await detail.reload(); await onChanged?.(); });
  const change = (name) => (event) => setForm((old) => ({ ...old, [name]: event.target.value, ...(name === "linked_type" ? { linked_id: "" } : {}) }));
  const candidates = { order: (orders || []).map((row) => ({ id: row.id, label: `${row.plan_name || "Đơn"} · ${money(row.amount)} · ${String(row.id).slice(0, 8)}` })),
    session: (sessions || []).map((row) => ({ id: row.id, label: `${row.license_plate} · ${dateTime(row.check_in_time)}` })),
    receipt: (receipts || []).filter((row) => row.kind === "receipt").map((row) => ({ id: row.id, label: `${money(row.amount)} · ${dateTime(row.created_at)}` })),
    refund_request: (refunds?.data || []).filter((row) => !row.legacy).map((row) => ({ id: row.id, label: `${refundStatusLabel(row)} · ${row.reason.slice(0, 40)}` })) };
  const submit = (event) => {
    event.preventDefault();
    const body = { subject: form.subject.trim(), category: form.category, message: form.message.trim() };
    if (form.linked_type) { body.linked_type = form.linked_type; body.linked_id = form.linked_id; }
    void action.run(() => send("/me/support-requests", body), "Đã gửi yêu cầu hỗ trợ. Quản lý sẽ phản hồi trong mục này và qua Thông báo.", (result) => { setForm(EMPTY); setSelected(result.id); });
  };
  return <Stack spacing={3}>
    {action.error && <Alert severity="error">{action.error}</Alert>}
    {action.notice && <Alert severity="success" role="status">{action.notice}</Alert>}
    <Section title="Gửi yêu cầu hỗ trợ" description="Mô tả vấn đề và, nếu cần, gắn đơn vé, lượt gửi, chứng từ hoặc yêu cầu hoàn của bạn. Chỉ tài nguyên thuộc tài khoản của bạn mới gắn được.">
      <Box component="form" sx={formLayout} onSubmit={submit}>
        <TextField required label="Tiêu đề" value={form.subject} onChange={change("subject")} slotProps={{ htmlInput: { minLength: 3, maxLength: 150 } }} />
        <TextField select label="Chủ đề" value={form.category} onChange={change("category")}>{SUPPORT_CATEGORIES.map(([key, label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}</TextField>
        <TextField select label="Gắn với" value={form.linked_type} onChange={change("linked_type")}><MenuItem value="">Không gắn</MenuItem>{Object.entries(LINK_LABEL).map(([key, label]) => <MenuItem key={key} value={key} disabled={!candidates[key]?.length}>{label}</MenuItem>)}</TextField>
        {form.linked_type && <TextField select required label={LINK_LABEL[form.linked_type]} value={form.linked_id} onChange={change("linked_id")}>{candidates[form.linked_type].map((row) => <MenuItem key={row.id} value={row.id}>{row.label}</MenuItem>)}</TextField>}
        <TextField required label="Nội dung" value={form.message} onChange={change("message")} multiline minRows={3} sx={{ gridColumn: "1 / -1" }} slotProps={{ htmlInput: { maxLength: 2000 } }} />
        <Button type="submit" variant="contained" disabled={action.busy || !linked || (form.linked_type && !form.linked_id)}>Gửi yêu cầu</Button>
      </Box>
    </Section>
    <RemoteSection remote={requests} title="Yêu cầu hỗ trợ của tôi" description="Trạng thái đổi khi quản lý phản hồi hoặc đóng yêu cầu; bạn cũng nhận thông báo trong ứng dụng.">
      {(rows) => <Records rows={rows} columns={[
        { key: "subject", label: "Tiêu đề" }, { key: "category", label: "Chủ đề", render: (row) => categoryLabel(row.category) },
        { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={supportStatusLabel(row.status)} /> },
        { key: "last_message_at", label: "Cập nhật", render: (row) => dateTime(row.last_message_at) },
        { key: "open", label: "Chi tiết", render: (row) => <Button size="small" onClick={() => { setSelected(row.id); setReply(""); }}>Xem trao đổi</Button> },
      ]} empty="Bạn chưa gửi yêu cầu hỗ trợ nào." />}
    </RemoteSection>
    <RemoteSection remote={refunds} title="Yêu cầu hoàn tiền của tôi" description="Gửi yêu cầu từ mục Lịch sử & chứng từ (nút Yêu cầu hoàn trên phiếu thu đủ điều kiện). Được duyệt chưa có nghĩa tiền đã về; trạng thái Đã hoàn tiền mới kèm chứng từ hoàn.">
      {(rows) => <Records rows={rows} columns={[
        { key: "created_at", label: "Ngày gửi", render: (row) => dateTime(row.created_at) },
        { key: "payment_channel", label: "Kênh thanh toán", render: (row) => channelLabel(row.payment_channel) },
        { key: "requested_amount", label: "Số có thể hoàn", render: (row) => row.requested_amount == null ? "—" : money(row.requested_amount) },
        { key: "approved_amount", label: "Số duyệt hoàn", render: (row) => row.approved_amount == null ? "—" : money(row.approved_amount) },
        { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={refundStatusLabel(row)} /> },
        { key: "note", label: "Phản hồi của quản lý", render: (row) => row.note || row.decision_note || "—" },
        { key: "external_reference", label: "Tham chiếu hoàn", render: (row) => row.external_reference || (row.refund_method ? row.refund_method : "—") },
      ]} empty="Chưa có yêu cầu hoàn." />}
    </RemoteSection>
    <Dialog open={Boolean(selected)} onClose={() => { if (!action.busy) setSelected(null); }} fullWidth maxWidth="md" aria-labelledby="support-thread-title">
      <DialogTitle id="support-thread-title">{detail.data ? detail.data.subject : "Yêu cầu hỗ trợ"}</DialogTitle>
      <DialogContent>
        {detail.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={detail.reload}>Thử lại</Button>}>{detail.error}</Alert>}
        {detail.loading && <Typography role="status" color="text.secondary">Đang tải trao đổi…</Typography>}
        {detail.data && <Stack spacing={2} sx={{ pt: 1 }}>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
            <StateChip value={detail.data.status} label={supportStatusLabel(detail.data.status)} />
            <Typography variant="body2" color="text.secondary">{categoryLabel(detail.data.category)}{detail.data.linked_type ? ` · ${LINK_LABEL[detail.data.linked_type]} ${String(detail.data.linked_id).slice(0, 8)}` : ""}</Typography>
          </Stack>
          <Thread detail={detail.data} />
          {detail.data.status !== "closed" ? <Box component="form" onSubmit={(event) => { event.preventDefault(); void action.run(() => send(`/me/support-requests/${detail.data.id}/messages`, { body: reply.trim() }), "Đã gửi phản hồi.", () => setReply("")); }}>
            <Stack spacing={1}>
              <TextField label="Trả lời" value={reply} onChange={(event) => setReply(event.target.value)} multiline minRows={2} disabled={action.busy} slotProps={{ htmlInput: { maxLength: 2000 } }} />
              <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                <Button type="submit" variant="contained" disabled={action.busy || !reply.trim()}>Gửi trả lời</Button>
                <Button color="inherit" disabled={action.busy} onClick={() => action.run(() => send(`/me/support-requests/${detail.data.id}/close`), "Đã đóng yêu cầu.")}>Đóng yêu cầu</Button>
              </Stack>
            </Stack>
          </Box> : <Alert severity="info">Yêu cầu đã đóng{detail.data.closed_at ? ` lúc ${dateTime(detail.data.closed_at)}` : ""}. Tạo yêu cầu mới nếu bạn cần hỗ trợ tiếp.</Alert>}
        </Stack>}
      </DialogContent>
      <DialogActions><Button disabled={action.busy} onClick={() => setSelected(null)}>Đóng</Button></DialogActions>
    </Dialog>
  </Stack>;
}
