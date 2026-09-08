import { useCallback, useState } from "react";
import { Alert, Box, Button, MenuItem, Tab, Tabs, TextField, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import FleetSection from "./FleetSection";
import { Availability, BookingForm, BookingRecords, WaitlistRecords } from "./siteComponents";
import { combineRemotes, items, PageControls, read, refreshAll, RemoteSection, Section, send, useAction, usePage, useRemote, useSites, Workspace, SitePicker } from "./shared";

const RESERVATION_STATES = [["", "Tất cả"], ["confirmed", "Đã đặt"], ["arrived", "Đã đến"], ["cancelled", "Đã hủy"], ["expired", "Hết hạn"]];
const WAITLIST_STATES = [["", "Tất cả"], ["waiting", "Đang chờ"], ["offered", "Đã có chỗ"], ["cancelled", "Đã hủy"]];
const loadProfile = () => read("/me/profile");

function BookingFeedback({ remote, label }) {
  return <>
    {remote.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={remote.reload} disabled={remote.loading}>Thử lại</Button>}>{label}: {remote.error}</Alert>}
    {remote.loading && <Typography role="status">Đang tải {label.toLowerCase()}…</Typography>}
  </>;
}

function StatusFilter({ label, value, options, onChange, disabled }) {
  return <TextField select size="small" label={label} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} sx={{ minWidth: 180 }}>
    {options.map(([key, text]) => <MenuItem key={key} value={key}>{text}</MenuItem>)}
  </TextField>;
}

function MySiteBookings({ site, organizations }) {
  const [tab, setTab] = useState("booking");
  const loadAvailability = useCallback(() => read(`/sites/${site.id}/availability`), [site.id]);
  const profile = useRemote(loadProfile);
  const availability = useRemote(loadAvailability);
  const linked = profile.data?.linked;
  const loadVehicles = useCallback(() => linked ? read("/me/vehicles").then(items) : Promise.resolve([]), [linked]);
  const vehicles = useRemote(loadVehicles);
  const bookingPage = usePage({ status: "" });
  const waitlistPage = usePage({ status: "" });
  const loadReservations = useCallback(() => linked
    ? read("/me/reservations", { site_id: site.id, ...bookingPage.params, ...(bookingPage.filters.status ? { status: bookingPage.filters.status } : {}) }).then(items)
    : Promise.resolve([]), [site.id, linked, bookingPage.params.offset, bookingPage.filters.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const loadWaitlist = useCallback(() => linked
    ? read("/me/waitlist", { site_id: site.id, ...waitlistPage.params, ...(waitlistPage.filters.status ? { status: waitlistPage.filters.status } : {}) }).then(items)
    : Promise.resolve([]), [site.id, linked, waitlistPage.params.offset, waitlistPage.filters.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const reservations = useRemote(loadReservations);
  const waitlist = useRemote(loadWaitlist);
  // A booking changes physical availability; an offer turns a waitlist row into a reservation.
  const bookingAction = useAction(refreshAll(reservations, availability));
  const waitlistAction = useAction(refreshAll(waitlist, reservations, availability));
  const slots = availability.data?.slots || [];
  const ownedVehicles = vehicles.data || [];
  const formUnavailable = vehicles.loading || !!vehicles.error || (tab === "booking" && (availability.loading || !availability.data));
  return <Workspace title={`Đặt chỗ tại ${site.name}`} description="Chọn khung giờ, giữ chỗ và theo dõi danh sách chờ. Nhân viên xác nhận xe đến tại bãi." remote={combineRemotes(profile, vehicles, availability, reservations, waitlist)} actions={[bookingAction, waitlistAction]}>
    <BookingFeedback remote={profile} label="Hồ sơ khách" />
    <BookingFeedback remote={vehicles} label="Xe của tôi" />
    {tab !== "availability" && <BookingFeedback remote={availability} label="Chỗ trống" />}
    <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto" aria-label="Đặt chỗ và đội xe">
      <Tab label="Đặt chỗ" value="booking" /><Tab label="Danh sách chờ" value="waitlist" /><Tab label="Chỗ trống" value="availability" /><Tab label="Đội xe của tôi" value="fleet" />
    </Tabs>
    {tab === "availability" && <RemoteSection remote={availability} title="Tình trạng vị trí">{(data) => <Availability data={data} />}</RemoteSection>}
    {tab === "fleet" && <FleetSection organizations={organizations.filter((row) => row.site_id === site.id)} />}
    {["booking", "waitlist"].includes(tab) && profile.data && <>
      {!linked ? <Alert severity="info" action={<Button component={Link} to="/portal">Mở hồ sơ</Button>}>Tạo hồ sơ khách hàng hoặc chờ quản lý xác minh hồ sơ để đăng ký chỗ.</Alert> : <>
        {vehicles.data && !ownedVehicles.length && <Alert severity="info" action={<Button component={Link} to="/portal">Đăng ký xe</Button>}>Bạn cần ít nhất một xe đã được duyệt.</Alert>}
        <Section title={tab === "booking" ? "Giữ một vị trí" : "Đăng ký khi chưa còn chỗ"} description={tab === "booking" ? "Đến trong 15 phút từ giờ bắt đầu. Đặt chỗ không bao gồm phí gửi xe hoặc vé tháng." : "Danh sách chờ chưa giữ chỗ. Khi nhân viên cấp vị trí, đặt chỗ mới sẽ xuất hiện ở mục Đặt chỗ."}>
          <Box component="fieldset" disabled={formUnavailable} sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
            <BookingForm key={tab} siteId={site.id} vehicles={ownedVehicles} slots={slots} action={tab === "waitlist" ? waitlistAction : bookingAction} kind={tab === "waitlist" ? "waitlist" : "reservation"}
              onSubmit={(body) => send(tab === "booking" ? "/me/reservations" : "/me/waitlist", body)} />
          </Box>
        </Section>
        {tab === "booking" ? <RemoteSection remote={reservations} title="Lịch đặt chỗ của tôi" description="Lọc theo bãi đang chọn tại máy chủ; mỗi trang 25 đặt chỗ, mới nhất trước."
          actions={<StatusFilter label="Trạng thái" value={bookingPage.filters.status} options={RESERVATION_STATES} disabled={reservations.loading} onChange={(status) => bookingPage.setFilters({ status })} />}>
          {(rows) => <>
            <BookingRecords rows={rows} slots={slots} vehicles={ownedVehicles} busy={bookingAction.busy}
              onCancel={(row) => void bookingAction.run(() => send(`/me/reservations/${row.id}/cancel`), "Đã hủy đặt chỗ.")} />
            <PageControls page={bookingPage.page} count={rows.length} size={bookingPage.size} busy={reservations.loading || bookingAction.busy} onChange={bookingPage.setPage} />
          </>}
        </RemoteSection> : <RemoteSection remote={waitlist} title="Yêu cầu chờ của tôi" description="Mỗi trang 25 yêu cầu, mới nhất trước."
          actions={<StatusFilter label="Trạng thái" value={waitlistPage.filters.status} options={WAITLIST_STATES} disabled={waitlist.loading} onChange={(status) => waitlistPage.setFilters({ status })} />}>
          {(rows) => <>
            <WaitlistRecords rows={rows} vehicles={ownedVehicles} busy={waitlistAction.busy}
              onCancel={(row) => void waitlistAction.run(() => send(`/me/waitlist/${row.id}/cancel`), "Đã rời danh sách chờ.")} />
            <PageControls page={waitlistPage.page} count={rows.length} size={waitlistPage.size} busy={waitlist.loading || waitlistAction.busy} onChange={waitlistPage.setPage} />
          </>}
        </RemoteSection>}
      </>}
    </>}
  </Workspace>;
}

const loadOrganizations = () => read("/me/organizations").then(items);

export default function ReservationsPage() {
  const sites = useSites();
  const organizations = useRemote(loadOrganizations);
  const selected = sites.sites.find((site) => String(site.id) === String(sites.siteId));
  return <>
    <SitePicker sites={sites} label="Bãi đỗ xe" sx={{ mb: 3, maxWidth: "100%" }} />
    {organizations.error && <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={organizations.reload}>Thử lại</Button>}>{organizations.error}</Alert>}
    {selected ? <MySiteBookings key={selected.id} site={selected} organizations={organizations.data || []} /> : <Workspace title="Đặt chỗ của tôi" description="Theo dõi quyền sử dụng chỗ đỗ và lịch đến bãi." remote={sites}><Alert severity="info">Chưa có bãi đang hoạt động.</Alert></Workspace>}
  </>;
}
