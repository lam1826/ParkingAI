import { useCallback, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { dateTime, read, Records, RemoteSection, send, StateChip, useAction, useRemote } from "./shared";
import { categoryLabel, LINK_LABEL, SUPPORT_CATEGORIES, SUPPORT_STATUS, supportStatusLabel } from "./supportState";

/** Manager side: list/filter support requests of the site, read the thread, reply, close or reopen. */
export default function SupportAdminPanel({ siteId }) {
  const [status, setStatus] = useState("open");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState(null);
  const [reply, setReply] = useState("");
  const load = useCallback(() => siteId ? read(`/sites/${siteId}/support-requests`, { ...(status ? { status } : {}), ...(category ? { category } : {}) }).then((data) => Array.isArray(data) ? data : data.items) : Promise.resolve([]), [siteId, status, category]);
  const remote = useRemote(load);
  const detailLoad = useCallback(() => selected ? read(`/sites/${siteId}/support-requests/${selected}`) : Promise.resolve(null), [siteId, selected]);
  const detail = useRemote(detailLoad);
  const action = useAction(async () => { await remote.reload(); await detail.reload(); });
  const base = detail.data ? `/sites/${siteId}/support-requests/${detail.data.id}` : "";
  return <Stack spacing={2}>
    {action.error && <Alert severity="error">{action.error}</Alert>}
    {action.notice && <Alert severity="success" role="status">{action.notice}</Alert>}
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
      <TextField select size="small" label="Trạng thái" value={status} onChange={(event) => setStatus(event.target.value)} sx={{ minWidth: 180 }}><MenuItem value="">Tất cả</MenuItem>{Object.entries(SUPPORT_STATUS).map(([key, label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}</TextField>
      <TextField select size="small" label="Chủ đề" value={category} onChange={(event) => setCategory(event.target.value)} sx={{ minWidth: 200 }}><MenuItem value="">Tất cả</MenuItem>{SUPPORT_CATEGORIES.map(([key, label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}</TextField>
    </Stack>
    <RemoteSection remote={remote} title="Yêu cầu hỗ trợ của khách" description="Phản hồi được gửi kèm thông báo trong ứng dụng cho khách. Đóng yêu cầu khi đã xử lý xong.">
      {(rows) => <Records rows={rows} columns={[
        { key: "last_message_at", label: "Cập nhật", render: (row) => dateTime(row.last_message_at) },
        { key: "customer_name", label: "Khách" }, { key: "subject", label: "Tiêu đề" },
        { key: "category", label: "Chủ đề", render: (row) => categoryLabel(row.category) },
        { key: "linked", label: "Gắn với", render: (row) => row.linked_type ? `${LINK_LABEL[row.linked_type]} ${String(row.linked_id).slice(0, 8)}` : "—" },
        { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={supportStatusLabel(row.status)} /> },
        { key: "open", label: "Xử lý", render: (row) => <Button size="small" onClick={() => { setSelected(row.id); setReply(""); }}>Mở trao đổi</Button> },
      ]} empty="Không có yêu cầu hỗ trợ ở bộ lọc này." />}
    </RemoteSection>
    <Dialog open={Boolean(selected)} onClose={() => { if (!action.busy) setSelected(null); }} fullWidth maxWidth="md" aria-labelledby="support-admin-title">
      <DialogTitle id="support-admin-title">{detail.data ? `${detail.data.subject} · ${detail.data.customer_name}` : "Yêu cầu hỗ trợ"}</DialogTitle>
      <DialogContent>
        {detail.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={detail.reload}>Thử lại</Button>}>{detail.error}</Alert>}
        {detail.loading && <Typography role="status" color="text.secondary">Đang tải trao đổi…</Typography>}
        {detail.data && <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">Tài khoản {detail.data.requester_username || "—"} · {categoryLabel(detail.data.category)}{detail.data.linked_type ? ` · ${LINK_LABEL[detail.data.linked_type]} ${detail.data.linked_id}` : ""} · <StateChip value={detail.data.status} label={supportStatusLabel(detail.data.status)} /></Typography>
          <Stack spacing={1.5}>
            {detail.data.messages.map((row) => <Box key={row.id} sx={{ p: 1.5, borderRadius: 1, bgcolor: row.author_role === "customer" ? "grey.100" : "primary.50", alignSelf: row.author_role === "customer" ? "flex-start" : "flex-end", minWidth: { sm: 280 }, maxWidth: "100%" }}>
              <Typography variant="caption" color="text.secondary">{row.author_role === "customer" ? "Khách" : "Quản lý"} · {dateTime(row.created_at)}</Typography>
              <Typography sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.body}</Typography>
            </Box>)}
          </Stack>
          {detail.data.status !== "closed" ? <Box component="form" onSubmit={(event) => { event.preventDefault(); void action.run(() => send(`${base}/messages`, { body: reply.trim() }), "Đã gửi phản hồi cho khách.", () => setReply("")); }}>
            <Stack spacing={1}>
              <TextField label="Phản hồi cho khách" value={reply} onChange={(event) => setReply(event.target.value)} multiline minRows={2} disabled={action.busy} slotProps={{ htmlInput: { maxLength: 2000 } }} />
              <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                <Button type="submit" variant="contained" disabled={action.busy || !reply.trim()}>Gửi phản hồi</Button>
                <Button color="inherit" disabled={action.busy} onClick={() => action.run(() => send(`${base}/close`, { note: reply.trim() }), "Đã đóng yêu cầu.", () => setReply(""))}>Đóng yêu cầu{reply.trim() ? " kèm ghi chú" : ""}</Button>
              </Stack>
            </Stack>
          </Box> : <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Alert severity="info" sx={{ flex: 1 }}>Đã đóng{detail.data.closed_at ? ` lúc ${dateTime(detail.data.closed_at)}` : ""}.</Alert>
            <Button disabled={action.busy} onClick={() => action.run(() => send(`${base}/reopen`), "Đã mở lại yêu cầu.")}>Mở lại</Button>
          </Stack>}
        </Stack>}
      </DialogContent>
      <DialogActions><Button disabled={action.busy} onClick={() => setSelected(null)}>Đóng</Button></DialogActions>
    </Dialog>
  </Stack>;
}
