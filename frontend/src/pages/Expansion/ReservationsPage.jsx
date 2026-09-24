import { useCallback, useContext, useRef, useState } from "react";
import { Alert, Button, Stack } from "@mui/material";
import { Link } from "react-router-dom";
import { AuthContext } from "../../context/AuthContext";
import { PageHeader, PrototypeIcon } from "../../components/common/PrototypeUI";
import { nextBookingWindow } from "./siteForms";
import { advanceBookingBody, uncertainMutation } from "./customerFlow";
import { dateTime, items, PageControls, read, Records, refreshAll, RemoteSection, requestKey, send, StateChip, useAction, usePage, useRemote, useSites, SitePicker } from "./shared";

const loadTypes = () => read("/catalog/vehicle-types").then(items);
const labels = { confirmed: "Đã giữ chỗ", arrived: "Đã đến", cancelled: "Đã hủy", expired: "Hết hạn" };

function PreviousBookings({ siteId }) {
  const loadPrevious = useCallback(async () => {
    const profile = await read("/me/profile");
    return profile.linked ? read("/me/reservations", { site_id: siteId, limit: 50 }).then(items) : [];
  }, [siteId]);
  const rows = useRemote(loadPrevious);
  const action = useAction(rows.reload);
  return <Stack spacing={2}>
    {action.error && <Alert severity="error">{action.error}</Alert>}
    {action.notice && <Alert severity="success">{action.notice}</Alert>}
    <RemoteSection remote={rows} title="Đặt chỗ từ vé hoặc quyền đã cấp" description="Các đặt chỗ cũ được giữ nguyên. Vé trả trước và chứng từ nằm trong Vé & lịch sử.">
      {(records) => <Records rows={records} columns={[{ key: "start_at", label: "Đến", render: (row) => dateTime(row.start_at) }, { key: "end_at", label: "Đi", render: (row) => dateTime(row.end_at) }, { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} label={labels[row.status]} /> }, { key: "action", label: "Thao tác", render: (row) => row.order_id ? <Button component={Link} to={`/portal?order=${encodeURIComponent(row.order_id)}`}>Xem đơn vé</Button> : row.status === "confirmed" ? <Button disabled={action.busy} onClick={() => void action.run(() => send(`/me/reservations/${row.id}/cancel`), "Đã hủy đặt chỗ.")}>Hủy đặt chỗ</Button> : "—" }]} empty="Không có đặt chỗ cũ." />}
    </RemoteSection>
  </Stack>;
}

function AdvanceBookings({ site }) {
  const types = useRemote(loadTypes);
  const page = usePage({}, 25);
  const loadBookings = useCallback(() => read("/me/advance-bookings", { site_id: site.id, limit: page.size, offset: page.params.offset }), [site.id, page.size, page.params.offset]);
  const bookings = useRemote(loadBookings);
  const loadAvailability = useCallback(() => read(`/sites/${site.id}/availability`), [site.id]);
  const availability = useRemote(loadAvailability);
  const action = useAction(refreshAll(bookings, availability));
  const [form, setForm] = useState(() => ({ license_plate: "", vehicle_type_id: "", ...nextBookingWindow() }));
  const [pending, setPending] = useState(false), [created, setCreated] = useState(null), [previousOpen, setPreviousOpen] = useState(false);
  const attempt = useRef(null);
  const typeChoices = (types.data || []).filter((row) => row.is_active !== false && (!availability.data || availability.data.slots.some((slot) => slot.vehicle_type_id === row.id)));
  const vehicleTypeId = form.vehicle_type_id || String(typeChoices[0]?.id || "");
  const type = types.data?.find((row) => String(row.id) === vehicleTypeId);
  const edit = (key) => (event) => setForm((old) => ({ ...old, [key]: event.target.value }));
  const submit = (event) => {
    event.preventDefault();
    void action.run(async () => {
      if (!attempt.current) attempt.current = Object.freeze(advanceBookingBody({ ...form, vehicle_type_id: vehicleTypeId }, site.id, types.data || [], requestKey()));
      const token = localStorage.getItem("token");
      try {
        const result = await send("/me/advance-bookings", attempt.current);
        if (token !== localStorage.getItem("token")) throw new Error("Phiên đăng nhập đã thay đổi.");
        if (!result?.id || !result.license_plate || !result.start_at || result.site_id !== site.id) throw new Error("Chưa xác nhận được kết quả đặt chỗ.");
        attempt.current = null; setPending(false);
        return result;
      } catch (error) {
        const uncertain = uncertainMutation(error);
        if (!uncertain) attempt.current = null;
        setPending(uncertain);
        throw error;
      }
    }, "Đã giữ chỗ. Bạn thanh toán phí theo lượt gửi thực tế, không cần trả trước.", setCreated);
  };
  return <>
    <PageHeader title="Đặt chỗ trước" description="Giữ một chỗ phù hợp, thanh toán theo thời gian gửi thực tế." />
    <div className="content-grid">
      <section className="surface">
        <div className="section-head"><h2>Thông tin đặt chỗ</h2></div>
        {types.error && <Alert severity="error" action={<Button onClick={types.reload}>Thử lại</Button>}>{types.error}</Alert>}
        {pending && <p role="alert" className="inline-note warning">Chưa xác định kết quả yêu cầu trước. Giữ nguyên thông tin và thử lại chính yêu cầu đó để tránh đặt trùng.</p>}
        <form onSubmit={submit}>
          <div className="form-grid">
            <div className="field"><label htmlFor="booking-plate">{type?.requires_plate === false ? "Mã xe (nếu đã có)" : "Biển số xe"}</label><input id="booking-plate" required={type?.requires_plate !== false} value={form.license_plate} onChange={edit("license_plate")} disabled={action.busy || pending} maxLength={20} autoComplete="off" />{type?.requires_plate === false && <small>Để trống để bãi cấp mã xe; giữ mã này khi đến.</small>}</div>
            <div className="field"><label htmlFor="booking-type">Loại xe</label><select id="booking-type" required value={vehicleTypeId} onChange={edit("vehicle_type_id")} disabled={action.busy || pending || types.loading}>{typeChoices.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></div>
            <div className="field"><label htmlFor="booking-start">Giờ đến dự kiến</label><input id="booking-start" type="datetime-local" required value={form.start_at} onChange={edit("start_at")} disabled={action.busy || pending} /></div>
            <div className="field"><label htmlFor="booking-end">Giờ về dự kiến</label><input id="booking-end" type="datetime-local" required value={form.end_at} onChange={edit("end_at")} disabled={action.busy || pending} /></div>
          </div>
          <p className="inline-note">Không thu tiền trước. Chỗ được giữ đến 15 phút sau giờ hẹn; tiền gửi tính từ lúc xe vào. Giờ Việt Nam.</p>
          <button className="button primary full" type="submit" disabled={action.busy || types.loading || !!types.error || !typeChoices.length}>{pending ? "Thử lại yêu cầu đã gửi" : action.busy ? "Đang giữ chỗ…" : "Giữ chỗ cho tôi"}<PrototypeIcon name="arrow" /></button>
        </form>
        {action.error && <p role="alert" className="inline-note warning">{action.error}</p>}
        {created && <p role="status" className="inline-note success">Xe <strong>{created.license_plate}</strong> · {created.slot_name || "Đã phân vị trí"}. Đến trước <strong>{dateTime(created.arrival_deadline)}</strong>. Khi vào bãi, nhận mã tra phí riêng trên vé.</p>}
        {!created && action.notice && <p className="inline-note success" role="status">{action.notice}</p>}
      </section>
      <section className="surface">
        <div className="section-head"><h2>Lịch sắp đến</h2></div>
        {bookings.error && <Alert severity="error" action={<Button onClick={bookings.reload}>Thử lại</Button>}>{bookings.error}</Alert>}
        {bookings.loading && <p className="muted" role="status">Đang tải lịch đặt chỗ…</p>}
        {items(bookings.data).map((row) => <div className="booking-row" key={row.id}>
          <div><div className="plate">{row.license_plate}</div><p>{types.data?.find((item) => item.id === row.vehicle_type_id)?.name || "Xe"} · {dateTime(row.start_at)} → {dateTime(row.end_at)}</p><p>{row.slot_name || "Vị trí phù hợp đã được giữ"}</p></div>
          <div><span className={`badge ${row.status === "confirmed" ? "success" : "neutral"}`}>{labels[row.status] || row.status}</span>{row.status === "confirmed" && <button className="button quiet small" type="button" disabled={action.busy || pending} onClick={() => void action.run(() => send(`/me/advance-bookings/${encodeURIComponent(row.id)}/cancel`), "Đã hủy đặt chỗ.", () => setCreated(null))}>Hủy</button>}</div>
        </div>)}
        {!bookings.loading && !bookings.error && !items(bookings.data).length && <div className="empty"><PrototypeIcon name="calendar" />Chưa có đặt chỗ. Bạn vẫn có thể đến gửi trực tiếp.</div>}
        {(page.page > 0 || items(bookings.data).length >= page.size) && <PageControls page={page.page} count={items(bookings.data).length} size={page.size} busy={bookings.loading || action.busy || pending} onChange={page.setPage} />}
      </section>
    </div>
    <details className="demo-help" onToggle={(event) => setPreviousOpen(event.currentTarget.open)}><summary>Đặt chỗ và vé trước đây</summary>{previousOpen && <PreviousBookings siteId={site.id} />}</details>
  </>;
}

function CustomerReservations() {
  const sites = useSites();
  const selected = sites.sites.find((site) => String(site.id) === String(sites.siteId));
  return <>{sites.sites.length > 1 && !sites.singleSiteMode && <SitePicker sites={sites} sx={{ mb: 2 }} />}{selected ? <AdvanceBookings key={selected.id} site={selected} /> : <><PageHeader title="Đặt chỗ trước" description="Giữ một chỗ phù hợp, thanh toán theo thời gian gửi thực tế." />{sites.error ? <Alert severity="error" action={<Button onClick={sites.reload}>Thử lại</Button>}>{sites.error}</Alert> : <p className="muted" role="status">{sites.loading ? "Đang tải bãi đỗ…" : "Chưa có bãi đang hoạt động."}</p>}</>}</>;
}

export default function ReservationsPage() {
  const { user } = useContext(AuthContext);
  return user?.role === "customer" ? <CustomerReservations /> : <Alert severity="info">Đặt chỗ trước dành cho khách hàng. Nhân viên ghi nhận xe đến tại mục Vận hành bãi.</Alert>;
}
