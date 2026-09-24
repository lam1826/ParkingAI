import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import api from "../../services/api";
import { useExpansion } from "../../context/ExpansionContext";
import { PageHeader } from "../../components/common/PrototypeUI";
import { toBusinessDateString } from "../../utils/businessDate";
import { mergeSelectedOrder, passStatus } from "./portalState";
import { entitlementLabel, orderStatusLabel, productKind, productLabel } from "./portalOffers";
import PortalPurchase from "./PortalPurchase";
import PortalOrderDetails from "./PortalOrderDetails";
import PortalSessionDetails from "./PortalSessionDetails";
import CustomerSupportPanel from "./CustomerSupportPanel";
import CustomerFees from "./CustomerFees";
import { portalTab } from "./customerFlow";
import { refundAction, supportStatusLabel } from "./supportState";
import { paymentModeLabel } from "./onlinePaymentState";
import { combineRemotes, dateOnly, dateTime, endpoint, formLayout, items, money, PageControls, read, Records, refreshAll, RemoteSection, Section, send, StateChip, useAction, usePage, useRemote, Workspace } from "./shared";

const sessionColumns = [
  { key: "license_plate", label: "Biển số" }, { key: "slot_name", label: "Vị trí" },
  { key: "check_in_time", label: "Giờ vào", render: (row) => dateTime(row.check_in_time) },
  { key: "check_out_time", label: "Giờ ra", render: (row) => dateTime(row.check_out_time) },
  { key: "prepaid", label: "Gói đã trả", render: (row) => row.prepaid ? `${money(row.prepaid.amount)}${row.prepaid.payment_mode === "demo" ? " · DEMO" : ""}` : "—" },
  { key: "parking_fee", label: "Phí khi ra", render: (row) => row.parking_fee == null ? (row.status === "cancelled" ? "Đã hủy" : "Chưa kết thúc") : money(row.parking_fee) },
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
  const [params] = useSearchParams();
  const destination = params.get("tab");
  if (!params.get("order") && (!destination || destination === "fees")) return <CustomerFees />;
  if (!params.get("order") && !params.get("view")) {
    if (destination === "tickets") return <TicketOverview />;
    if (destination === "support") return <SupportOverview />;
  }
  return <CustomerTickets />;
}

function CompactRemoteState({ remote, label }) {
  if (remote.error) return <Alert severity="error" action={<Button onClick={remote.reload}>Thử lại</Button>}>{remote.error}</Alert>;
  return remote.loading ? <p className="muted" role="status">Đang tải {label}…</p> : null;
}

/** The default view mirrors the compact demo; complete billing workflows remain in detail views. */
function TicketOverview() {
  const identity = useRemote(loadIdentity);
  const linked = Boolean(identity.data?.linked);
  const page = usePage({}, 50);
  const passes = usePagedPortalList("/me/passes", page, linked);
  const vehicles = usePagedPortalList("/me/vehicles", page, linked);
  const sessions = usePagedPortalList("/me/sessions", page, linked);
  const receipts = usePagedPortalList("/me/receipts", page, Boolean(identity.data));
  const closed = (sessions.data || []).filter((row) => row.status === "completed");
  const paid = (receipts.data || []).filter((row) => row.kind === "receipt");
  const receiptMethod = (row) => row.method === "demo" ? "DEMO · mô phỏng" : row.method === "cash" ? "Tiền mặt" : row.method === "transfer" ? "Chuyển khoản" : "Chứng từ lịch sử";
  const receiptTitle = (row) => {
    const source = row.source_type === "monthly_pass" ? passes.data : ["parking_session", "session_credit"].includes(row.source_type) ? sessions.data : [];
    return source?.find((item) => String(item.id) === String(row.source_id))?.license_plate || (row.source_type === "monthly_pass" ? "Vé tháng" : row.source_type === "portal_order" ? "Đơn vé" : "Phí gửi xe");
  };
  return <>
    <PageHeader title="Vé & lịch sử" description="Vé tháng, thời hạn và chứng từ của bạn." />
    <CompactRemoteState remote={identity} label="hồ sơ" />
    <div className="content-grid">
      <section className="surface">
        <div className="section-head"><h2>Vé tháng của bạn</h2></div>
        <CompactRemoteState remote={passes} label="vé tháng" />
        {(passes.data || []).map((row) => {
          const status = passStatus(row, toBusinessDateString());
          const typeName = vehicles.data?.find((vehicle) => vehicle.id === row.vehicle_id)?.type_name;
          return <div className="list-row" key={row.id}><div><strong>{row.card_code} · {row.license_plate}</strong>{typeName && <p>{typeName}</p>}<p>{dateOnly(row.start_date)} → {dateOnly(row.end_date)}</p><p>Giá vé: {money(row.price)}</p></div><span className={`badge ${status === "Đang hiệu lực" ? "success" : "neutral"}`}>{status}</span></div>;
        })}
        {!passes.loading && !passes.error && !passes.data?.length && <div className="empty">{identity.data?.linked === false ? "Liên kết hồ sơ để xem vé tháng của bạn." : "Bạn chưa có vé tháng."}</div>}
        <p className="inline-note">Liên hệ quản lý để đăng ký hoặc gia hạn. Bạn cũng có thể mua vé bằng tài khoản đã liên kết.</p>
        <div className="form-actions"><Link className="button quiet small" to="/portal?tab=tickets&view=purchase">Mua vé / gia hạn</Link><Link className="button quiet small" to="/portal?tab=tickets&view=passes">Tất cả vé</Link></div>
      </section>
      <section className="surface">
        <div className="section-head"><h2>Chứng từ thanh toán</h2></div>
        <CompactRemoteState remote={receipts} label="chứng từ" />
        {paid.slice(0, 5).map((row) => <div className="history-row" key={row.id}><div><span className="plate">{receiptTitle(row)}</span><small>{dateTime(row.created_at)} · {receiptMethod(row)}</small></div><strong>{money(row.amount)}</strong></div>)}
        {!receipts.loading && !receipts.error && !paid.length && <div className="empty">Chưa có chứng từ thanh toán.</div>}
        <div className="divider" />
        <h3>Lượt gửi đã kết thúc</h3>
        <CompactRemoteState remote={sessions} label="lịch sử" />
        {closed.slice(0, 5).map((row) => <div className="history-row" key={row.id}><div>{row.license_plate}<small>{dateTime(row.check_in_time)} → {dateTime(row.check_out_time)}</small></div><span>{row.parking_fee == null ? "—" : money(row.parking_fee)}</span></div>)}
        {!sessions.loading && !sessions.error && !closed.length && <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>Lịch sử thuộc tài khoản xuất hiện sau khi xe ra.</p>}
        <Link className="button quiet small" style={{ marginTop: 18 }} to="/portal?tab=tickets&view=history">Xem tất cả · PDF & hoàn tiền</Link>
      </section>
    </div>
    <details className="demo-help"><summary>Xe, hồ sơ & thông báo</summary><div className="demo-tools"><Link className="button secondary small" to="/portal?tab=tickets&view=profile">Xe & hồ sơ</Link><Link className="button secondary small" to="/portal?tab=tickets&view=notifications">Thông báo</Link></div></details>
  </>;
}

const supportSubjects = [["receipt", "Thanh toán & hoàn tiền"], ["order", "Đặt chỗ trước"], ["session", "Mất vé / không tìm thấy lượt"]];

function SupportOverview() {
  const identity = useRemote(loadIdentity);
  const linked = Boolean(identity.data?.linked);
  const loadRequests = useCallback(() => linked ? read("/me/support-requests").then(items) : Promise.resolve([]), [linked]);
  const requests = useRemote(loadRequests);
  const [category, setCategory] = useState("receipt"), [message, setMessage] = useState("");
  const [selected, setSelected] = useState(null), [reply, setReply] = useState("");
  const loadDetail = useCallback(() => selected ? read(`/me/support-requests/${encodeURIComponent(selected)}`) : Promise.resolve(null), [selected]);
  const detail = useRemote(loadDetail);
  const action = useAction(refreshAll(requests, detail));
  const submit = (event) => {
    event.preventDefault();
    void action.run(() => send("/me/support-requests", { subject: supportSubjects.find(([key]) => key === category)[1], category, message: message.trim() }), "Đã gửi yêu cầu. Quản lý sẽ phản hồi trong mục này.", () => setMessage(""));
  };
  return <>
    <PageHeader title="Bạn cần hỗ trợ?" description="Gửi yêu cầu để quản lý bãi tiếp nhận." />
    <CompactRemoteState remote={identity} label="hồ sơ" />
    <div className="content-grid">
      <section className="surface">
        <form onSubmit={submit}>
          <div className="field"><label htmlFor="support-subject">Vấn đề cần hỗ trợ</label><select id="support-subject" value={category} onChange={(event) => setCategory(event.target.value)} disabled={action.busy}>{supportSubjects.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
          <div className="field"><label htmlFor="support-message">Nội dung</label><textarea id="support-message" placeholder="Mô tả vấn đề để quản lý hỗ trợ bạn…" required maxLength={2000} value={message} onChange={(event) => setMessage(event.target.value)} disabled={action.busy} /></div>
          <button className="button primary" type="submit" disabled={action.busy || !linked || !message.trim()}>Gửi yêu cầu</button>
        </form>
        {identity.data?.linked === false && <p className="inline-note">Liên kết hồ sơ để bãi tiếp nhận hỗ trợ cho đúng khách hàng. <Link to="/portal?tab=tickets&view=profile">Mở hồ sơ</Link></p>}
        {action.error && <p role="alert" className="inline-note warning">{action.error}</p>}
        {action.notice && <p role="status" className="inline-note success">{action.notice}</p>}
      </section>
      <section className="surface">
        <h2>Yêu cầu của bạn</h2>
        <CompactRemoteState remote={requests} label="yêu cầu" />
        {(requests.data || []).map((row) => <div className="list-row" key={row.id}><div><strong>{row.subject}</strong><p>{dateTime(row.last_message_at || row.created_at)}</p><button className="button quiet small" type="button" onClick={() => { setSelected(row.id); setReply(""); }}>Xem trao đổi</button></div><span className={`badge ${row.status === "open" ? "warning" : "neutral"}`}>{supportStatusLabel(row.status)}</span></div>)}
        {!requests.loading && !requests.error && !requests.data?.length && <div className="empty">Chưa có yêu cầu hỗ trợ.</div>}
      </section>
    </div>
    <details className="demo-help"><summary>Hoàn tiền & yêu cầu chi tiết</summary><p>Yêu cầu hoàn được gửi từ chứng từ đủ điều kiện. Quản lý kiểm tra và cập nhật kết quả; gửi yêu cầu chưa có nghĩa đã hoàn tiền.</p><div className="demo-tools"><Link className="button secondary small" to="/portal?tab=tickets&view=history">Chứng từ & yêu cầu hoàn</Link><Link className="button secondary small" to="/portal?tab=support&view=details">Theo dõi hoàn tiền / gắn chứng từ</Link></div></details>
    <Dialog open={Boolean(selected)} onClose={() => { if (!action.busy) setSelected(null); }} fullWidth maxWidth="sm" aria-labelledby="support-thread-title">
      <div className="prototype-ui" style={{ background: "white", minHeight: 0 }}>
        <DialogTitle id="support-thread-title">{detail.data?.subject || "Yêu cầu hỗ trợ"}</DialogTitle>
        <DialogContent>
          <CompactRemoteState remote={detail} label="trao đổi" />
          {detail.data && <>
            <span className="badge neutral">{supportStatusLabel(detail.data.status)}</span>
            {detail.data.messages.map((row) => <div className={`chat-message ${row.mine ? "user" : "assistant"}`} key={row.id}><small className="muted">{row.mine ? "Bạn" : "Quản lý"} · {dateTime(row.created_at)}</small><p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.body}</p></div>)}
            {detail.data.status !== "closed" ? <form style={{ marginTop: 20 }} onSubmit={(event) => { event.preventDefault(); void action.run(() => send(`/me/support-requests/${detail.data.id}/messages`, { body: reply.trim() }), "Đã gửi trả lời.", () => setReply("")); }}>
              <div className="field"><label htmlFor="support-reply">Trả lời</label><textarea id="support-reply" value={reply} onChange={(event) => setReply(event.target.value)} required maxLength={2000} disabled={action.busy} /></div>
              <div className="form-actions"><button className="button primary" type="submit" disabled={action.busy || !reply.trim()}>Gửi trả lời</button><button className="button quiet" type="button" disabled={action.busy} onClick={() => void action.run(() => send(`/me/support-requests/${detail.data.id}/close`), "Đã đóng yêu cầu.")}>Đóng yêu cầu</button></div>
            </form> : <p className="inline-note">Yêu cầu đã đóng. Tạo yêu cầu mới nếu bạn cần hỗ trợ tiếp.</p>}
          </>}
          {action.error && <p className="inline-note warning" role="alert">{action.error}</p>}
        </DialogContent>
        <DialogActions><Button disabled={action.busy} onClick={() => setSelected(null)}>Đóng</Button></DialogActions>
      </div>
    </Dialog>
  </>;
}

function CustomerTickets() {
  const capabilities = useExpansion();
  const demoPaymentsEnabled = Boolean(capabilities.demo_payments_enabled);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedOrder = searchParams.get("order");
  const tab = portalTab(searchParams);
  const setTab = (value) => setSearchParams(value === 5 ? { tab: "support" } : { tab: "tickets", view: ["profile", "passes", "purchase", "history", "notifications"][value] });
  const [refundTarget, setRefundTarget] = useState(null);
  const [refundReason, setRefundReason] = useState("");
  const [purchaseLocked, setPurchaseLocked] = useState(false);
  const [profile, setProfile] = useState({ full_name: "", phone_number: "", email: "" });
  const [link, setLink] = useState({ phone_number: "", note: "" });
  const [vehicle, setVehicle] = useState({ license_plate: "", vehicle_type_id: "", note: "" });
  const [selected, setSelected] = useState(null);
  const [selectedSession, setSelectedSession] = useState(null);
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
  const passesPage = usePage({}, 50), timedPage = usePage({}, 50), ordersPage = usePage({}, 50), sessionsPage = usePage({}, 50), receiptsPage = usePage({}, 50), notificationsPage = usePage({}, 50);
  const passes = usePagedPortalList("/me/passes", passesPage, linked);
  const timedPasses = usePagedPortalList("/me/timed-passes", timedPage, linked);
  const orders = usePagedPortalList("/me/orders", ordersPage, linked);
  const sessions = usePagedPortalList("/me/sessions", sessionsPage, linked);
  const receipts = usePagedPortalList("/me/receipts", receiptsPage, Boolean(identity.data));
  const notifications = usePagedPortalList("/me/notifications", notificationsPage, linked);
  const loadRefunds = useCallback(() => linked ? read("/me/refund-requests").then(items) : Promise.resolve([]), [linked]);
  const refunds = useRemote(loadRefunds);
  const loadRequestedOrder = useCallback(() => linked && requestedOrder ? read(`/me/orders/${encodeURIComponent(requestedOrder)}`) : Promise.resolve(null), [linked, requestedOrder]);
  const requestedDetail = useRemote(loadRequestedOrder);
  // Profile/link changes alter what every other section may show, so they reload the identity gate
  // (which re-keys the dependent loaders). A payment result touches orders, passes, receipts and notices.
  const identityAction = useAction(refreshAll(identity, links));
  const vehicleAction = useAction(refreshAll(vehicles, vehicleRequests));
  const refreshPurchases = refreshAll(orders, passes, timedPasses, receipts, notifications, refunds);
  const orderAction = useAction(refreshPurchases);
  const notificationAction = useAction(refreshAll(notifications));
  const downloadAction = useAction();
  const data = identity.data;
  const currentOrder = mergeSelectedOrder(selected || requestedDetail.data, orders.data);
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
  const openOrder = (order) => orderAction.run(() => read(`/me/orders/${encodeURIComponent(order.id)}`), "Đã cập nhật đơn vé.", (result) => { setSelected(result); setTab(2); });
  const onCreated = (order) => { setSelected(order); void refreshPurchases(); };
  const everything = combineRemotes(identity, types, plans, links, vehicles, vehicleRequests, passes, timedPasses, orders, sessions, receipts, notifications, refunds, requestedDetail);
  return <Workspace title={tab === 5 ? "Hỗ trợ" : "Vé & lịch sử"} description={tab === 5 ? "Theo dõi trao đổi với bãi xe và yêu cầu hoàn tiền." : "Vé đã mua, lượt gửi và các chứng từ thuộc tài khoản của bạn."} remote={everything}
    actions={[identityAction, vehicleAction, orderAction, notificationAction, downloadAction, { busy: purchaseLocked }]}>
    {identity.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={identity.reload} disabled={identity.loading}>Thử lại</Button>}>Hồ sơ: {identity.error}</Alert>}
    {tab !== 5 && <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto" aria-label="Vé và lịch sử cá nhân"><Tab value={1} disabled={purchaseLocked} label="Vé của tôi" /><Tab value={2} disabled={purchaseLocked} label="Mua vé" /><Tab value={3} disabled={purchaseLocked} label="Lịch sử & chứng từ" /><Tab value={0} disabled={purchaseLocked} label="Xe & hồ sơ" /><Tab value={4} disabled={purchaseLocked} label="Thông báo" /></Tabs>}
    {data && !linked && tab !== 0 && <Alert severity="info" action={<Button onClick={() => setTab(0)}>Mở hồ sơ</Button>}>Đặt chỗ trước và thanh toán bằng mã vé không cần liên kết hồ sơ. Liên kết hồ sơ để xem toàn bộ lịch sử xe, mua vé và gửi yêu cầu hỗ trợ.</Alert>}
    {data && !linked && tab === 3 && <RemoteSection remote={receipts} title="Chứng từ đã thanh toán bằng tài khoản này">{(rows) => <><Records rows={rows} columns={[{ key: "created_at", label: "Ngày thu", render: (row) => dateTime(row.created_at) }, { key: "amount", label: "Số tiền", render: (row) => money(row.amount) }, { key: "method", label: "Phương thức", render: (row) => row.method === "demo" ? "DEMO — mô phỏng" : row.method === "cash" ? "Tiền mặt" : "Chuyển khoản" }, { key: "download", label: "Chứng từ", render: (row) => <Button size="small" disabled={downloadAction.busy} onClick={() => downloadReceipt(row)}>Tải PDF</Button> }]} />{pager(receiptsPage, receipts, downloadAction.busy)}</>}</RemoteSection>}
    {data && !linked && tab === 0 && <>
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
      {tab === 1 && <>
        <RemoteSection remote={timedPasses} title="Vé giờ / ngày của tôi" description="Một vé dùng một lượt trong khung giờ đã mua. Đến muộn không kéo dài giờ kết thúc.">
          {(rows) => <><Records rows={rows} columns={[
            { key: "license_plate", label: "Biển số" }, { key: "product_kind", label: "Loại vé", render: productLabel },
            { key: "start_at", label: "Bắt đầu", render: (row) => dateTime(row.start_at) }, { key: "end_at", label: "Kết thúc", render: (row) => dateTime(row.end_at) },
            { key: "arrival_deadline", label: "Đến trước", render: (row) => dateTime(row.arrival_deadline) },
            { key: "slot", label: "Chỗ đỗ", render: (row) => row.slot ? `${row.slot.zone_name} · ${row.slot.name}` : "—" },
            { key: "status", label: "Quyền sử dụng", render: (row) => <StateChip value={row.status} label={entitlementLabel(row.status)} /> },
            { key: "order_id", label: "Đơn vé", render: (row) => <Button disabled={orderAction.busy} onClick={() => openOrder({ id: row.order_id })}>Xem đơn</Button> },
          ]} empty="Chưa có vé giờ hoặc ngày. Mở Mua vé & đơn hàng để chọn gói." />{pager(timedPage, timedPasses, orderAction.busy)}</>}
        </RemoteSection>
        <RemoteSection remote={passes} title="Vé tháng của tôi" description="Vé tháng áp dụng theo kỳ, không mặc nhiên bảo đảm một chỗ trống.">
          {(rows) => <><Records rows={rows} columns={[{ key: "license_plate", label: "Biển số" }, { key: "card_code", label: "Mã thẻ" }, { key: "start_date", label: "Từ ngày", render: (row) => dateOnly(row.start_date) }, { key: "end_date", label: "Đến hết ngày", render: (row) => dateOnly(row.end_date) }, { key: "price", label: "Giá kỳ", render: (row) => money(row.price) }, { key: "is_active", label: "Tình trạng", render: (row) => passStatus(row, toBusinessDateString()) }]} empty="Chưa có vé tháng. Mở Mua vé & đơn hàng để mua hoặc gia hạn." />{pager(passesPage, passes, orderAction.busy)}</>}
        </RemoteSection>
      </>}
      {tab === 2 && <Alert severity="info">{demoPaymentsEnabled ? "Chế độ đồ án: QR và kết quả thanh toán DEMO là mô phỏng, không chuyển tiền qua ngân hàng." : "Chọn hình thức thanh toán khi mua vé. Vé được cấp sau khi khoản thu được xác nhận."}</Alert>}
      <PortalPurchase vehicles={vehicles} plans={plans} demoPaymentsEnabled={demoPaymentsEnabled} onCreated={onCreated} onLocked={setPurchaseLocked} visible={tab === 2} initialKind={searchParams.get("kind")} />
      {currentOrder && <Box sx={{ display: tab === 2 ? "block" : "none" }}><PortalOrderDetails key={`${currentOrder.id}-${currentOrder.server_now}-${currentOrder.status}`} order={currentOrder} busy={orderAction.busy || purchaseLocked}
          onRefresh={() => openOrder(currentOrder)}
          onSimulate={(outcome) => orderAction.run(() => send(`/me/orders/${currentOrder.id}/simulate`, { token: currentOrder.demo_token, outcome }), "Đã ghi nhận kết quả mô phỏng.", setSelected)}
          onCancel={() => orderAction.run(() => send(`/me/orders/${currentOrder.id}/cancel`), "Đã hủy đơn chưa thanh toán.", setSelected)}
          onRefund={(reason) => orderAction.run(() => send(`/me/orders/${currentOrder.id}/refund-requests`, { reason }), "Đã gửi yêu cầu hoàn để quản lý kiểm tra.")} /></Box>}
      {tab === 2 && <>
        {requestedDetail.error && <Alert severity="error" action={<Button disabled={requestedDetail.loading || purchaseLocked} onClick={requestedDetail.reload}>Thử lại</Button>}>Không mở được đơn vé: {requestedDetail.error}</Alert>}
        <RemoteSection remote={refunds} title="Yêu cầu hoàn của tôi">{(rows) => <Records rows={rows} columns={[{ key: "reason", label: "Lý do" }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={orderStatusLabel(row.status)} /> }, { key: "note", label: "Phản hồi" }]} empty="Chưa có yêu cầu hoàn." />}</RemoteSection>
        <RemoteSection remote={orders} title="Đơn mua vé">{(rows) => <><Records rows={rows} columns={[
          { key: "id", label: "Đơn", render: (row) => <Button size="small" onClick={() => openOrder(row)} disabled={orderAction.busy || purchaseLocked}>{String(row.id).slice(0, 8)}</Button> },
          { key: "product_kind", label: "Loại vé", render: productLabel },
          { key: "amount", label: "Số tiền", render: (row) => money(row.amount) },
          { key: "payment_mode", label: "Thanh toán", render: (row) => paymentModeLabel(row.payment_mode) },
          { key: "period", label: "Hiệu lực", render: (row) => productKind(row) === "monthly" ? `${dateOnly(row.start_date)} – hết ${dateOnly(row.end_date)}` : `${dateTime(row.start_at)} – ${dateTime(row.end_at)}` },
          { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={orderStatusLabel(row.status)} /> },
        ]} />{pager(ordersPage, orders, orderAction.busy || purchaseLocked)}</>}</RemoteSection>
      </>}
      {tab === 3 && <>
        <RemoteSection remote={sessions} title="Lịch sử gửi xe" description="Khoản gói đã mua và phí khi ra được ghi riêng. Chỉ hiển thị các lượt thuộc quyền truy cập đã xác minh của bạn.">{(rows) => <><Records rows={rows} columns={[...sessionColumns, { key: "details", label: "Chi tiết", render: (row) => <Button size="small" onClick={() => setSelectedSession(row)}>{row.status === "active" ? "Chi tiết & thanh toán" : "Xem căn cứ phí"}</Button> }]} />{pager(sessionsPage, sessions, false)}</>}</RemoteSection>
        <RemoteSection remote={receipts} title="Chứng từ của tôi">{(rows) => <><Records rows={rows} columns={[{ key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) }, { key: "kind", label: "Loại", render: (row) => row.kind === "refund" ? "Hoàn" : "Thu" }, { key: "amount", label: "Số tiền", render: (row) => money(row.amount) }, { key: "method", label: "Phương thức", render: (row) => row.method === "demo" ? "Mô phỏng đồ án" : row.method === "cash" ? "Tiền mặt" : row.method === "transfer" ? "Chuyển khoản" : "Chứng từ lịch sử" }, { key: "download", label: "Chứng từ", render: (row) => <Button size="small" disabled={downloadAction.busy} onClick={() => downloadReceipt(row)}>Tải PDF</Button> },
          { key: "refund", label: "Hoàn tiền", render: (row) => { const state = refundAction(row); return state.kind === "request" ? <Button size="small" variant="outlined" disabled={orderAction.busy} onClick={() => { setRefundTarget(row); setRefundReason(""); }}>Yêu cầu hoàn</Button> : state.kind === "none" ? "—" : <Typography variant="body2" color="text.secondary">{state.label}</Typography>; } }]} />{pager(receiptsPage, receipts, downloadAction.busy)}</>}</RemoteSection>
      </>}
      {tab === 5 && <CustomerSupportPanel linked={linked} orders={orders.data} sessions={sessions.data} receipts={receipts.data} refunds={refunds} onChanged={refreshAll(notifications)} />}
      <Dialog open={Boolean(refundTarget)} onClose={() => { if (!orderAction.busy) setRefundTarget(null); }} fullWidth maxWidth="sm" aria-labelledby="refund-request-title">
        {refundTarget && <Box component="form" onSubmit={(event) => { event.preventDefault(); void orderAction.run(() => send(`/me/receipts/${refundTarget.id}/refund-requests`, { reason: refundReason.trim() }), "Đã gửi yêu cầu hoàn để quản lý kiểm tra. Gửi yêu cầu chưa có nghĩa tiền đã được hoàn.", () => { setRefundTarget(null); setTab(5); }); }}>
          <DialogTitle id="refund-request-title">Yêu cầu hoàn tiền</DialogTitle>
          <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
            <Typography>Phiếu thu {money(refundTarget.amount)} · {dateTime(refundTarget.created_at)}{refundTarget.method === "demo" ? " · DEMO (mô phỏng, không có tiền thật)" : ""}</Typography>
            <Typography>Số có thể hoàn theo máy chủ: <strong>{money(refundTarget.refund?.refundable_amount)}</strong>. Quản lý sẽ kiểm tra và quyết định; số tiền hoàn không vượt số này.</Typography>
            <TextField autoFocus required label="Lý do yêu cầu hoàn" value={refundReason} onChange={(event) => setRefundReason(event.target.value)} multiline minRows={2} disabled={orderAction.busy} slotProps={{ htmlInput: { maxLength: 500 } }} />
          </Stack></DialogContent>
          <DialogActions><Button disabled={orderAction.busy} onClick={() => setRefundTarget(null)}>Quay lại</Button><Button type="submit" variant="contained" disabled={orderAction.busy || !refundReason.trim()}>Gửi yêu cầu hoàn</Button></DialogActions>
        </Box>}
      </Dialog>
      {tab === 4 && <RemoteSection remote={notifications} title="Thông báo">{(rows) => <><Records rows={rows} columns={[{ key: "title", label: "Nội dung", render: (row) => <Box><Typography fontWeight={row.is_read ? 400 : 700}>{row.title}</Typography><Typography variant="body2" color="text.secondary">{row.message || row.body}</Typography></Box> }, { key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) }, { key: "action", label: "Thao tác", render: (row) => !row.is_read && <Button size="small" disabled={notificationAction.busy} onClick={() => notificationAction.run(() => send(`/me/notifications/${row.id}/read`), "Đã đánh dấu thông báo.")}>Đã đọc</Button> }]} empty="Bạn chưa có thông báo mới." />{pager(notificationsPage, notifications, notificationAction.busy)}</>}</RemoteSection>}
      {selectedSession && <PortalSessionDetails session={selectedSession} onClose={() => setSelectedSession(null)} onChanged={refreshAll(sessions, receipts)} />}
    </>}
  </Workspace>;
}
