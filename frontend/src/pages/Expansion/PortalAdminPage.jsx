import { useCallback, useState } from "react";
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { singleSiteId } from "../../utils/singleSiteMode";
import OnlinePaymentReview from "./OnlinePaymentReview";
import { paymentModeLabel } from "./onlinePaymentState";
import { orderStatusLabel, portalPlanBody, productDuration, productKind, productLabel } from "./portalOffers";
import { Workspace, Section, Records, StateChip, useRemote, useAction, read, send, items, money, dateTime, dateOnly, endpoint, formLayout } from "./shared";

const emptyPlan = { name: "", site_id: "", vehicle_type_id: "", product_kind: "monthly", duration_days: "30", duration_minutes: "60", price: "" };

export default function PortalAdminPage() {
  const [tab, setTab] = useState(0);
  const [page, setPage] = useState(0);
  const [plan, setPlan] = useState(emptyPlan);
  const [editingPlan, setEditingPlan] = useState(null);
  const [resolution, setResolution] = useState(null);
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [method, setMethod] = useState("cash");
  const load = useCallback(async () => {
    const paths = ["link-requests", "vehicle-requests", "account-links", "plans", "orders", "refund-requests"];
    const responses = await Promise.all(paths.map((path) => read(`/portal/admin/${path}`, path === "orders" ? { limit: 50, offset: page * 50 } : undefined)));
    const [sites, types] = await Promise.all([read("/sites"), read("/catalog/vehicle-types")]);
    return { ...Object.fromEntries(paths.map((path, index) => [path, items(responses[index])])), sites: items(sites), types: items(types) };
  }, [page]);
  const remote = useRemote(load);
  const action = useAction(remote.reload);
  const data = remote.data;
  const singleSiteMode = singleSiteId() !== null;
  const planSiteId = plan.site_id || (singleSiteMode ? data?.sites[0]?.id || "" : "");
  const edit = (field) => (event) => setPlan((old) => ({ ...old, [field]: event.target.value }));
  const openResolution = (kind, row, approve) => { setResolution({ kind, row, approve }); setNote(""); setConfirmed(false); setMethod("cash"); };
  const decisionButtons = (kind, row) => <Stack direction="row" spacing={1} useFlexGap><Button size="small" disabled={action.busy} onClick={() => openResolution(kind, row, true)}>Duyệt</Button><Button size="small" color="error" disabled={action.busy} onClick={() => openResolution(kind, row, false)}>Từ chối</Button></Stack>;
  const savePlan = (event) => {
    event.preventDefault();
    void action.run(() => {
      const body = portalPlanBody(plan, { editing: Boolean(editingPlan), siteId: planSiteId });
      return editingPlan ? api.patch(endpoint(`/portal/admin/plans/${editingPlan.id}`), body) : send("/portal/admin/plans", body);
    }, "Đã lưu gói vé. Giá và thời hạn trên đơn đã tạo được giữ nguyên.", () => { setEditingPlan(null); setPlan(emptyPlan); });
  };
  const resolve = (event) => {
    event.preventDefault();
    const { kind, row, approve } = resolution;
    const suffix = kind === "orders" ? "review" : kind === "collect" ? "collect" : "resolve";
    const path = `/portal/admin/${kind === "collect" ? "orders" : kind}/${row.id}/${suffix}`;
    const body = kind === "collect" ? { payment_method: method, confirmed: true } : { approve, note };
    void action.run(() => send(path, body), "Đã ghi nhận quyết định xử lý.", () => setResolution(null));
  };
  return <Workspace title="Khách & đơn vé" description="Xác minh hồ sơ, công bố gói vé và xử lý các đơn đăng ký của khách hàng." remote={remote} action={action}>
    <Alert severity="info">Đơn DEMO không chuyển tiền qua ngân hàng. Phiếu thu và hoàn mô phỏng được tách khỏi doanh thu và chốt ca.</Alert>
    <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto" aria-label="Quản lý cổng khách"><Tab label="Xác minh khách & xe" /><Tab label="Gói vé" /><Tab label="Đơn đăng ký" /><Tab label="Yêu cầu hoàn" /><Tab label="Đối soát chuyển khoản" /></Tabs>
    {data && tab === 4 && <OnlinePaymentReview sites={data.sites} />}
    {data && tab === 0 && <>
      <Section title="Liên kết hồ sơ khách" description="Đối chiếu thông tin của khách trước khi duyệt. Biết số điện thoại chưa chứng minh quyền sở hữu hồ sơ."><Records rows={data["link-requests"]} columns={[{ key: "username", label: "Tài khoản" }, { key: "user_full_name", label: "Họ tên" }, { key: "requester_role", label: "Vai trò" }, { key: "phone_number", label: "Điện thoại hồ sơ" }, { key: "note", label: "Thông tin xác minh" }, { key: "action", label: "Xử lý", render: (row) => decisionButtons("link-requests", row) }]} empty="Không có yêu cầu liên kết chờ duyệt." /></Section>
      <Section title="Liên kết phương tiện" description="Kiểm tra biển số, loại xe và quyền sử dụng của khách trước khi duyệt."><Records rows={data["vehicle-requests"]} columns={[{ key: "customer_name", label: "Khách" }, { key: "requester_role", label: "Vai trò" }, { key: "license_plate", label: "Biển số" }, { key: "type_name", label: "Loại xe" }, { key: "note", label: "Ghi chú" }, { key: "action", label: "Xử lý", render: (row) => decisionButtons("vehicle-requests", row) }]} empty="Không có yêu cầu thêm xe chờ duyệt." /></Section>
      <Section title="Tài khoản đang liên kết" description="Chỉ quản trị viên toàn hệ thống được gỡ liên kết; hồ sơ khách và lịch sử vẫn được giữ nguyên."><Records rows={data["account-links"]} columns={[{ key: "username", label: "Tài khoản" }, { key: "requester_role", label: "Vai trò" }, { key: "customer_name", label: "Hồ sơ khách" }, { key: "phone_number", label: "Điện thoại" }, { key: "action", label: "Thao tác", render: (row) => row.can_unlink ? <Button size="small" color="error" disabled={action.busy} onClick={() => action.run(() => api.delete(endpoint(`/portal/admin/account-links/${row.user_id}`)), "Đã gỡ liên kết tài khoản.")}>Gỡ liên kết</Button> : "Chỉ admin" }]} empty="Chưa có tài khoản liên kết." /></Section>
    </>}
    {data && tab === 1 && <>
      <Section title={editingPlan ? "Chỉnh sửa gói vé" : "Công bố gói vé mới"} description="Mỗi gói áp dụng cho một loại xe. Vé giờ/ngày gồm một lượt và đặt chỗ theo khung giờ; vé tháng không mặc nhiên giữ chỗ. Thay đổi chỉ áp dụng cho đơn mới."><Box component="form" sx={formLayout} onSubmit={savePlan}>
        <TextField required label="Tên gói" value={plan.name} onChange={edit("name")} inputProps={{ maxLength: 100 }} />
        {singleSiteMode ? <Typography color="text.secondary">Bãi áp dụng: {data.sites[0]?.name || "Chưa được cấp quyền"}</Typography> : <TextField select required disabled={Boolean(editingPlan)} label="Bãi áp dụng" value={plan.site_id} onChange={edit("site_id")}>{data.sites.map((site) => <MenuItem key={site.id} value={site.id}>{site.name}</MenuItem>)}</TextField>}
        <TextField select required disabled={Boolean(editingPlan)} label="Loại xe" value={plan.vehicle_type_id} onChange={edit("vehicle_type_id")}>{data.types.map((type) => <MenuItem key={type.id} value={type.id}>{type.name}</MenuItem>)}</TextField>
        <TextField select required disabled={Boolean(editingPlan)} label="Loại gói vé" value={productKind(plan)} onChange={edit("product_kind")}><MenuItem value="monthly">Vé tháng</MenuItem><MenuItem value="hourly">Vé giờ</MenuItem><MenuItem value="daily">Vé ngày (24 giờ)</MenuItem></TextField>
        {productKind(plan) === "monthly" && <TextField required type="number" label="Số ngày hiệu lực" value={plan.duration_days ?? ""} onChange={edit("duration_days")} inputProps={{ min: 1, max: 366, step: 1 }} />}
        {productKind(plan) === "hourly" && <TextField required type="number" label="Thời lượng (phút)" value={plan.duration_minutes ?? ""} onChange={edit("duration_minutes")} inputProps={{ min: 60, max: 1440, step: 60 }} helperText="Từ 1 đến 24 giờ, theo bước 60 phút." />}
        {productKind(plan) === "daily" && <Typography color="text.secondary">Thời lượng cố định: 24 giờ từ giờ bắt đầu trên đơn.</Typography>}
        <TextField required type="number" label="Giá gói (đồng)" value={plan.price} onChange={edit("price")} inputProps={{ min: 1, max: Number.MAX_SAFE_INTEGER, step: 1 }} />
        <Stack direction="row" spacing={1} useFlexGap><Button variant="contained" type="submit" disabled={action.busy || !planSiteId}>{editingPlan ? "Lưu gói vé" : "Công bố gói"}</Button>{editingPlan && <Button onClick={() => { setEditingPlan(null); setPlan(emptyPlan); }}>Hủy sửa</Button>}</Stack>
      </Box></Section>
      <Section title="Danh sách gói"><Records rows={data.plans} columns={[{ key: "name", label: "Gói vé" }, { key: "site_name", label: "Bãi" }, { key: "type_name", label: "Loại xe" }, { key: "product_kind", label: "Loại vé", render: productLabel }, { key: "duration", label: "Thời lượng", render: productDuration }, { key: "price", label: "Giá", render: (row) => money(row.price) }, { key: "is_active", label: "Công bố", render: (row) => row.is_active ? "Đang mở" : "Đã ẩn" }, { key: "action", label: "Thao tác", render: (row) => <Stack direction="row"><Button size="small" onClick={() => { setEditingPlan(row); setPlan({ ...emptyPlan, ...row, product_kind: productKind(row), site_id: row.site_id || "" }); }}>Sửa</Button><Button size="small" disabled={action.busy} onClick={() => action.run(() => api.patch(endpoint(`/portal/admin/plans/${row.id}`), { is_active: !row.is_active }), "Đã cập nhật công bố gói vé.")}>{row.is_active ? "Ẩn gói" : "Mở gói"}</Button></Stack> }]} /></Section>
    </>}
    {data && tab === 2 && <Section title="Đơn đăng ký và đối soát"><Records rows={data.orders} columns={[{ key: "id", label: "Mã đơn", render: (row) => <Typography variant="body2" title={row.id}>{row.id.slice(0, 8)}</Typography> }, { key: "customer_name", label: "Khách" }, { key: "license_plate", label: "Biển số" }, { key: "site_name", label: "Bãi" }, { key: "product_kind", label: "Loại vé", render: productLabel }, { key: "amount", label: "Số tiền", render: (row) => money(row.amount) }, { key: "hold_expires_at", label: "Hạn giữ chỗ", render: (row) => dateTime(row.hold_expires_at) }, { key: "payment_mode", label: "Hình thức", render: (row) => paymentModeLabel(row.payment_mode) }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={orderStatusLabel(row.status)} /> }, { key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) }, { key: "action", label: "Xử lý", render: (row) => row.status === "review" && row.payment_mode === "demo" ? decisionButtons("orders", row) : row.status === "pending" && row.payment_mode === "manual" ? <Button size="small" onClick={() => openResolution("collect", row, true)}>Thu tại quầy</Button> : "—" }]} /><Stack direction="row" sx={{ alignItems: "center" }} spacing={2} useFlexGap><Button disabled={page === 0 || remote.loading} onClick={() => setPage((old) => old - 1)}>Trang trước</Button><Typography>Trang {page + 1}</Typography><Button disabled={data.orders.length < 50 || remote.loading} onClick={() => setPage((old) => old + 1)}>Trang sau</Button></Stack></Section>}
    {data && tab === 3 && <Section title="Yêu cầu hoàn" description="Kiểm tra khoản thu và quyền đã sử dụng trước khi duyệt. Hoàn DEMO chỉ là mô phỏng; không chuyển tiền qua ngân hàng."><Records rows={data["refund-requests"]} columns={[{ key: "customer_name", label: "Khách" }, { key: "order_id", label: "Đơn", render: (row) => row.order_id.slice(0, 8) }, { key: "reason", label: "Lý do" }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={orderStatusLabel(row.status)} /> }, { key: "action", label: "Quyết định", render: (row) => row.status === "pending" ? decisionButtons("refund-requests", row) : "—" }]} /></Section>}
    <Dialog open={Boolean(resolution)} onClose={() => { if (!action.busy) setResolution(null); }} fullWidth maxWidth="sm" aria-labelledby="portal-resolution-title"><Box component="form" onSubmit={resolve}><DialogTitle id="portal-resolution-title">{resolution?.kind === "collect" ? "Xác nhận thu tại quầy" : resolution?.approve ? "Duyệt yêu cầu" : "Từ chối yêu cầu"}</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      <Typography>{resolution?.row.customer_name || resolution?.row.username} · {resolution?.row.license_plate || resolution?.row.phone_number || resolution?.row.id}</Typography>
      {["collect", "orders"].includes(resolution?.kind) && <>
        <Typography>{productLabel(resolution.row)} · {resolution.row.plan_name || `Gói #${resolution.row.plan_id}`}</Typography>
        <Typography>Hiệu lực: {productKind(resolution.row) === "monthly" ? `${dateOnly(resolution.row.start_date)} – hết ${dateOnly(resolution.row.end_date)}` : `${dateTime(resolution.row.start_at)} – ${dateTime(resolution.row.end_at)}`}</Typography>
        {resolution.row.hold_expires_at && <Typography>Hạn giữ chỗ: {dateTime(resolution.row.hold_expires_at)}</Typography>}
      </>}
      {resolution?.kind === "collect" ? <><Typography>Số tiền phải thu: <strong>{money(resolution.row.amount)}</strong></Typography><TextField select label="Phương thức đã thu" value={method} onChange={(event) => setMethod(event.target.value)}><MenuItem value="cash">Tiền mặt</MenuItem><MenuItem value="transfer">Chuyển khoản</MenuItem></TextField></> : <TextField required label="Ghi chú xác minh / lý do xử lý" value={note} onChange={(event) => setNote(event.target.value)} multiline minRows={2} inputProps={{ maxLength: 500 }} />}
      <FormControlLabel control={<Checkbox checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />} label={resolution?.kind === "collect" ? "Tôi xác nhận đã thu đủ tiền qua phương thức đã chọn" : "Tôi đã kiểm tra thông tin và xác nhận quyết định này"} />
      {action.error && <Alert severity="error">{action.error}</Alert>}
    </Stack></DialogContent><DialogActions><Button disabled={action.busy} onClick={() => setResolution(null)}>Quay lại</Button><Button type="submit" variant="contained" disabled={action.busy || !confirmed}>Xác nhận</Button></DialogActions></Box></Dialog>
  </Workspace>;
}
