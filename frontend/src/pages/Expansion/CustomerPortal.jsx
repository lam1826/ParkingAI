import { useCallback, useState } from "react";
import { Alert, Box, Button, MenuItem, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { useExpansion } from "../../context/ExpansionContext";
import { toBusinessDateString } from "../../utils/businessDate";
import { mergeSelectedOrder, newOrderDraft, passStatus } from "./portalState";
import { combineRemotes, dateOnly, dateTime, endpoint, formLayout, items, money, PageControls, read, Records, refreshAll, RemoteSection, requestKey, Section, send, StateChip, useAction, usePage, useRemote, Workspace } from "./shared";

const sessionColumns = [
  { key: "license_plate", label: "Biển số" }, { key: "slot_name", label: "Vị trí" },
  { key: "check_in_time", label: "Giờ vào", render: (row) => dateTime(row.check_in_time) },
  { key: "check_out_time", label: "Giờ ra", render: (row) => dateTime(row.check_out_time) },
  { key: "parking_fee", label: "Phí", render: (row) => row.parking_fee == null ? "Chưa kết thúc" : money(row.parking_fee) },
];

/** One paged customer list; it only reloads when its own page changes or a mutation asks for it. */
function usePagedPortalList(path, page, linked) {
  const offset = page.params.offset;
  const load = useCallback(() => linked ? read(path, { limit: page.size, offset }).then(items) : Promise.resolve([]), [path, page.size, offset, linked]);
  return useRemote(load);
}

const loadIdentity = () => read("/me/profile");
const loadTypes = () => read("/catalog/vehicle-types").then(items);
const loadPlans = () => read("/plans").then(items);

function CatalogState({ remote, label }) {
  if (remote.error) return <Alert severity="error" action={<Button color="inherit" size="small" onClick={remote.reload} disabled={remote.loading}>Thử lại</Button>}>{label}: {remote.error}</Alert>;
  return remote.loading ? <Typography role="status" color="text.secondary">Đang tải {label.toLowerCase()}…</Typography> : null;
}

export default function CustomerPortal() {
  const capabilities = useExpansion();
  const demoPaymentsEnabled = Boolean(capabilities.demo_payments_enabled);
  const [tab, setTab] = useState(0);
  const [profile, setProfile] = useState({ full_name: "", phone_number: "", email: "" });
  const [link, setLink] = useState({ phone_number: "", note: "" });
  const [vehicle, setVehicle] = useState({ license_plate: "", vehicle_type_id: "", note: "" });
  const [orderForm, setOrderForm] = useState({ plan_id: "", vehicle_id: "", idempotency_key: requestKey() });
  const [selected, setSelected] = useState(null);
  const [refundReason, setRefundReason] = useState("");
  const identity = useRemote(loadIdentity);
  const types = useRemote(loadTypes);
  const plans = useRemote(loadPlans);
  const linked = Boolean(identity.data?.linked);
  const unlinked = identity.data?.linked === false;
  const loadLinks = useCallback(() => unlinked ? read("/me/link-requests").then(items) : Promise.resolve([]), [unlinked]);
  const links = useRemote(loadLinks);
  const loadVehicles = useCallback(() => linked ? read("/me/vehicles").then(items) : Promise.resolve([]), [linked]);
  const vehicles = useRemote(loadVehicles);
  const loadVehicleRequests = useCallback(() => linked ? read("/me/vehicle-requests").then(items) : Promise.resolve([]), [linked]);
  const vehicleRequests = useRemote(loadVehicleRequests);
  const passesPage = usePage({}, 50), ordersPage = usePage({}, 50), sessionsPage = usePage({}, 50), receiptsPage = usePage({}, 50), notificationsPage = usePage({}, 50);
  const passes = usePagedPortalList("/me/passes", passesPage, linked);
  const orders = usePagedPortalList("/me/orders", ordersPage, linked);
  const sessions = usePagedPortalList("/me/sessions", sessionsPage, linked);
  const receipts = usePagedPortalList("/me/receipts", receiptsPage, linked);
  const notifications = usePagedPortalList("/me/notifications", notificationsPage, linked);
  const loadRefunds = useCallback(() => linked ? read("/me/refund-requests").then(items) : Promise.resolve([]), [linked]);
  const refunds = useRemote(loadRefunds);
  // Profile/link changes alter what every other section may show, so they reload the identity gate
  // (which re-keys the dependent loaders). A payment result touches orders, passes, receipts and notices.
  const identityAction = useAction(refreshAll(identity, links));
  const vehicleAction = useAction(refreshAll(vehicles, vehicleRequests));
  const orderAction = useAction(refreshAll(orders, passes, receipts, notifications, refunds));
  const notificationAction = useAction(refreshAll(notifications));
  const downloadAction = useAction();
  const data = identity.data;
  const currentOrder = mergeSelectedOrder(selected, orders.data);
  const pager = (page, remote, busy) => <PageControls page={page.page} count={remote.data?.length || 0} size={page.size} busy={remote.loading || busy} onChange={page.setPage} />;
  const downloadReceipt = (row) => downloadAction.run(async () => {
    const response = await api.get(endpoint(`/me/receipts/${row.id}/pdf`), { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `ParkingAI-${row.method === "demo" ? "DEMO-" : ""}${row.id}.pdf`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, "Đã tải chứng từ PDF.");
  const edit = (setter, field) => (event) => setter((old) => ({ ...old, [field]: event.target.value }));
  const submit = (action) => (event, operation, message, onSuccess) => { event.preventDefault(); void action.run(operation, message, onSuccess); };
  const openOrder = (order) => orderAction.run(() => read(`/me/orders/${order.id}`), "Đã mở đơn đăng ký.", setSelected);
  const startNewOrder = () => {
    setSelected(null);
    setOrderForm((old) => newOrderDraft(old, requestKey));
  };
  const everything = combineRemotes(identity, types, plans, links, vehicles, vehicleRequests, passes, orders, sessions, receipts, notifications, refunds);
  return <Workspace title="Bãi xe của tôi" description="Quản lý xe, vé tháng và các lượt gửi của bạn trong một nơi." remote={everything}
    actions={[identityAction, vehicleAction, orderAction, notificationAction, downloadAction]}>
    {identity.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={identity.reload} disabled={identity.loading}>Thử lại</Button>}>Hồ sơ: {identity.error}</Alert>}
    {data && !linked && <>
      <Alert severity="info">Liên kết hồ sơ trước khi đăng ký xe và vé. Hồ sơ đã tồn tại cần được nhân viên xác minh để bảo vệ dữ liệu của bạn.</Alert>
      <Section title="Tạo hồ sơ khách hàng">
        <Box component="form" onSubmit={(event) => submit(identityAction)(event, () => send("/me/profile", { ...profile, email: profile.email || null }), "Đã tạo hồ sơ khách hàng.")} sx={formLayout}>
          <TextField required label="Họ và tên" value={profile.full_name} onChange={edit(setProfile, "full_name")} inputProps={{ maxLength: 100 }} />
          <TextField required label="Số điện thoại" value={profile.phone_number} onChange={edit(setProfile, "phone_number")} inputProps={{ maxLength: 20 }} />
          <TextField label="Email" type="email" value={profile.email} onChange={edit(setProfile, "email")} />
          <Button type="submit" variant="contained" disabled={identityAction.busy}>Tạo hồ sơ</Button>
        </Box>
      </Section>
      <Section title="Tôi đã có hồ sơ tại bãi" description="Gửi yêu cầu để nhân viên kiểm tra và liên kết với tài khoản này.">
        <Box component="form" onSubmit={(event) => submit(identityAction)(event, () => send("/me/link-requests", link), "Đã gửi yêu cầu liên kết. Nhân viên sẽ kiểm tra hồ sơ.")} sx={formLayout}>
          <TextField required label="Số điện thoại đã đăng ký" value={link.phone_number} onChange={edit(setLink, "phone_number")} />
          <TextField label="Thông tin hỗ trợ xác minh" value={link.note} onChange={edit(setLink, "note")} inputProps={{ maxLength: 500 }} />
          <Button type="submit" variant="outlined" disabled={identityAction.busy}>Yêu cầu liên kết</Button>
        </Box>
        <CatalogState remote={links} label="Yêu cầu liên kết" />
        {!links.error && !links.loading && <Records rows={links.data || []} columns={[{ key: "created_at", label: "Ngày yêu cầu", render: (row) => dateTime(row.created_at) }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} /> }]} empty="Chưa có yêu cầu liên kết." />}
      </Section>
    </>}
    {data && linked && <>
      <Typography color="text.secondary">Hồ sơ: <strong>{data.customer.full_name}</strong> · {data.customer.phone_number}</Typography>
      <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto" aria-label="Quản lý bãi xe cá nhân"><Tab label="Xe của tôi" /><Tab label="Vé tháng" /><Tab label="Đăng ký & QR" /><Tab label="Lịch sử & chứng từ" /><Tab label="Thông báo" /></Tabs>
      {tab === 0 && <>
        <RemoteSection remote={vehicles} title="Xe đã liên kết" description="Nhân viên duyệt yêu cầu trước khi xe được liên kết với tài khoản.">
        {(rows) => <>
          <Records rows={rows} columns={[{ key: "license_plate", label: "Biển số" }, { key: "type_name", label: "Loại xe" }, { key: "current_slot", label: "Vị trí hiện tại", render: (row) => row.slot_name || row.current_slot || "Không có lượt gửi đang hoạt động" }]} empty="Bạn chưa có xe được xác minh. Gửi yêu cầu thêm xe bên dưới." />
        </>}
        </RemoteSection>
        <Section title="Yêu cầu thêm xe">
          <CatalogState remote={types} label="Loại xe" />
          <Box component="form" sx={formLayout} onSubmit={(event) => submit(vehicleAction)(event, () => send("/me/vehicle-requests", { ...vehicle, vehicle_type_id: Number(vehicle.vehicle_type_id) }), "Đã gửi yêu cầu thêm xe.", () => setVehicle({ license_plate: "", vehicle_type_id: "", note: "" }))}>
            <TextField required label="Biển số" value={vehicle.license_plate} onChange={edit(setVehicle, "license_plate")} inputProps={{ maxLength: 20 }} />
            <TextField select required label="Loại xe" value={vehicle.vehicle_type_id} disabled={types.loading || !!types.error} onChange={edit(setVehicle, "vehicle_type_id")}>{(types.data || []).map((type) => <MenuItem key={type.id} value={type.id}>{type.name}</MenuItem>)}</TextField>
            <TextField label="Ghi chú" value={vehicle.note} onChange={edit(setVehicle, "note")} />
            <Button type="submit" variant="contained" disabled={vehicleAction.busy || types.loading || !!types.error || !types.data?.length}>Gửi yêu cầu</Button>
          </Box>
        </Section>
        <RemoteSection remote={vehicleRequests} title="Yêu cầu thêm xe đã gửi">
          {(rows) => <Records rows={rows} columns={[{ key: "license_plate", label: "Biển số" }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} /> }]} empty="Chưa có yêu cầu thêm xe." />}
        </RemoteSection>
      </>}
      {tab === 1 && <RemoteSection remote={passes} title="Vé tháng của tôi" description="Vé tháng áp dụng chính sách phí theo kỳ. Quyền giữ chỗ được quản lý riêng.">
        {(rows) => <><Records rows={rows} columns={[{ key: "license_plate", label: "Biển số" }, { key: "card_code", label: "Mã thẻ" }, { key: "start_date", label: "Từ ngày", render: (row) => dateOnly(row.start_date) }, { key: "end_date", label: "Đến hết ngày", render: (row) => dateOnly(row.end_date) }, { key: "price", label: "Giá kỳ", render: (row) => money(row.price) }, { key: "is_active", label: "Tình trạng", render: (row) => passStatus(row, toBusinessDateString()) }]} empty="Chưa có vé tháng. Chọn Đăng ký & QR để mua hoặc gia hạn." />{pager(passesPage, passes, orderAction.busy)}</>}
      </RemoteSection>}
      {tab === 2 && <>
        <Alert severity="info">{demoPaymentsEnabled ? "Chế độ đồ án: QR và các kết quả thanh toán ở đây là mô phỏng, không chuyển tiền qua ngân hàng." : "Đơn đăng ký sẽ chờ nhân viên xác nhận đã thu tiền tại bãi."}</Alert>
        <RemoteSection remote={vehicles} title="Đăng ký hoặc gia hạn vé tháng">
          {(rows) => <><CatalogState remote={plans} label="Gói vé tháng" /><Box component="form" sx={formLayout} onSubmit={(event) => submit(orderAction)(event, () => send("/me/orders", { ...orderForm, plan_id: Number(orderForm.plan_id), vehicle_id: Number(orderForm.vehicle_id), payment_mode: demoPaymentsEnabled ? "demo" : "manual" }), "Đã tạo đơn đăng ký.", (order) => { setSelected(order); setOrderForm((old) => newOrderDraft(old, requestKey)); })}>
            <TextField select required label="Xe sử dụng" value={orderForm.vehicle_id} onChange={edit(setOrderForm, "vehicle_id")}>{rows.map((car) => <MenuItem key={car.id} value={car.id}>{car.license_plate}</MenuItem>)}</TextField>
            <TextField select required label="Gói vé tháng" value={orderForm.plan_id} disabled={plans.loading || !!plans.error} onChange={edit(setOrderForm, "plan_id")}>{(plans.data || []).map((plan) => <MenuItem key={plan.id} value={plan.id}>{plan.site_name} · {plan.name} · {plan.type_name} · {money(plan.price)} · {plan.duration_days} ngày</MenuItem>)}</TextField>
            <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button type="submit" variant="contained" disabled={orderAction.busy || !rows.length || plans.loading || !!plans.error || !plans.data?.length}>{demoPaymentsEnabled ? "Tạo đơn và mã QR" : "Tạo đơn đăng ký"}</Button><Button type="button" variant="outlined" disabled={orderAction.busy} onClick={startNewOrder}>Yêu cầu mới</Button></Stack>
          </Box>{!plans.loading && !plans.error && plans.data?.length === 0 && <Typography color="text.secondary">Bãi chưa công bố gói vé. Nhân viên cần tạo gói trước khi bạn đăng ký.</Typography>}</>}
        </RemoteSection>
        {currentOrder && <Section title={currentOrder.payment_mode === "demo" ? "Thanh toán mô phỏng" : "Đơn chờ thu tại bãi"} description={`Đơn ${currentOrder.id}`}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ alignItems: { md: "center" } }}>
            {currentOrder.demo_qr_svg && <Box component="img" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(currentOrder.demo_qr_svg)}`} alt="Mã QR thanh toán mô phỏng, không dùng chuyển tiền" sx={{ width: 220, height: 220, bgcolor: "white", alignSelf: "center" }} />}
            <Stack spacing={2} sx={{ minWidth: 0, flex: 1 }}><Typography variant="h5">{money(currentOrder.amount)}</Typography><Typography>{dateOnly(currentOrder.start_date)} – {dateOnly(currentOrder.end_date)}</Typography><Box><StateChip value={currentOrder.status} /></Box>
              {currentOrder.demo_payload && <TextField label="Nội dung QR mô phỏng" value={currentOrder.demo_payload} multiline slotProps={{ input: { readOnly: true } }} />}
              {currentOrder.payment_mode === "manual" && currentOrder.status === "pending" && <Typography color="text.secondary">Mang mã đơn tới quầy để nhân viên xác nhận thanh toán.</Typography>}
              <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>{currentOrder.payment_mode === "demo" && [["success", "Giả lập thanh toán thành công"], ["failed", "Giả lập thất bại"], ["cancelled", "Hủy thanh toán"]].map(([outcome, label]) => <Button key={outcome} variant={outcome === "success" ? "contained" : "outlined"} disabled={orderAction.busy || currentOrder.status !== "pending"} onClick={() => orderAction.run(() => send(`/me/orders/${currentOrder.id}/simulate`, { token: currentOrder.demo_token, outcome }), "Đã ghi kết quả mô phỏng.", setSelected)}>{label}</Button>)}{["pending", "expired"].includes(currentOrder.status) && <Button variant="outlined" color="error" disabled={orderAction.busy} onClick={() => orderAction.run(() => send(`/me/orders/${currentOrder.id}/cancel`), "Đã hủy đơn đăng ký.", setSelected)}>Hủy đơn</Button>}</Stack>
              {["paid", "fulfilled"].includes(currentOrder.status) && <Box component="form" onSubmit={(event) => submit(orderAction)(event, () => send(`/me/orders/${currentOrder.id}/refund-requests`, { reason: refundReason }), "Đã gửi yêu cầu hoàn tiền mô phỏng.")}><Stack spacing={1} useFlexGap><TextField required label="Lý do yêu cầu hoàn mô phỏng" value={refundReason} onChange={(event) => setRefundReason(event.target.value)} inputProps={{ maxLength: 500 }} /><Button type="submit" variant="outlined" disabled={orderAction.busy}>Gửi yêu cầu hoàn mô phỏng</Button></Stack></Box>}
            </Stack>
          </Stack>
        </Section>}
        <RemoteSection remote={refunds} title="Yêu cầu hoàn mô phỏng">{(rows) => <Records rows={rows} columns={[{ key: "reason", label: "Lý do" }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} /> }, { key: "note", label: "Phản hồi" }]} empty="Chưa có yêu cầu hoàn." />}</RemoteSection>
        <RemoteSection remote={orders} title="Đơn đăng ký">{(rows) => <><Records rows={rows} columns={[{ key: "id", label: "Đơn", render: (row) => <Button size="small" onClick={() => openOrder(row)} disabled={orderAction.busy}>{String(row.id).slice(0, 8)}</Button> }, { key: "amount", label: "Số tiền mô phỏng", render: (row) => money(row.amount) }, { key: "start_date", label: "Kỳ hiệu lực", render: (row) => `${dateOnly(row.start_date)} – ${dateOnly(row.end_date)}` }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} /> }]} />{pager(ordersPage, orders, orderAction.busy)}</>}</RemoteSection>
      </>}
      {tab === 3 && <>
        <RemoteSection remote={sessions} title="Lịch sử gửi xe" description="Chỉ hiển thị các lượt thuộc quyền truy cập đã xác minh của bạn.">{(rows) => <><Records rows={rows} columns={sessionColumns} />{pager(sessionsPage, sessions, false)}</>}</RemoteSection>
        <RemoteSection remote={receipts} title="Chứng từ của tôi">{(rows) => <><Records rows={rows} columns={[{ key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) }, { key: "kind", label: "Loại", render: (row) => row.kind === "refund" ? "Hoàn" : "Thu" }, { key: "amount", label: "Số tiền", render: (row) => money(row.amount) }, { key: "method", label: "Phương thức", render: (row) => row.method === "demo" ? "Mô phỏng đồ án" : row.method === "cash" ? "Tiền mặt" : row.method === "transfer" ? "Chuyển khoản" : "Chứng từ lịch sử" }, { key: "download", label: "Chứng từ", render: (row) => <Button size="small" disabled={downloadAction.busy} onClick={() => downloadReceipt(row)}>Tải PDF</Button> }]} />{pager(receiptsPage, receipts, downloadAction.busy)}</>}</RemoteSection>
      </>}
      {tab === 4 && <RemoteSection remote={notifications} title="Thông báo">{(rows) => <><Records rows={rows} columns={[{ key: "title", label: "Nội dung", render: (row) => <Box><Typography fontWeight={row.is_read ? 400 : 700}>{row.title}</Typography><Typography variant="body2" color="text.secondary">{row.message || row.body}</Typography></Box> }, { key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) }, { key: "action", label: "Thao tác", render: (row) => !row.is_read && <Button size="small" disabled={notificationAction.busy} onClick={() => notificationAction.run(() => send(`/me/notifications/${row.id}/read`), "Đã đánh dấu thông báo.")}>Đã đọc</Button> }]} empty="Bạn chưa có thông báo mới." />{pager(notificationsPage, notifications, notificationAction.busy)}</>}</RemoteSection>}
    </>}
  </Workspace>;
}
