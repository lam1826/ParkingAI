import { useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useSearchParams } from "react-router-dom";
import { AuthContext } from "../../context/AuthContext";
import { sessionSearchParams } from "../../utils/coreAnalytics";
import { admissionVehicleTypes } from "../../utils/admissionVehicleTypes";
import OperationsPanel from "./OperationsPanel";
import api from "../../services/api";
import CheckoutDialog from "../ParkingSession/components/CheckoutDialog";
import SessionDetailsDialog from "../ParkingSession/components/SessionDetailsDialog";
import TicketDialog from "../ParkingSession/components/TicketDialog";
import FleetSection from "./FleetSection";
import SiteFinance from "./SiteFinance";
import { useExpansion } from "../../context/ExpansionContext";
import SiteConfiguration, { CreateSiteForm } from "./SiteConfiguration";
import { Availability, BookingForm, BookingRecords, WaitlistRecords } from "./siteComponents";
import { checkoutAdapters } from "./siteForms";
import { combineRemotes, dateTime, formLayout, items, money, PageControls, read, Records, refreshAll, RemoteSection, Section, send, StateChip, useAction, usePage, useRemote, useSites, Workspace, SitePicker } from "./shared";

const RESERVATION_STATES = [["", "Tất cả"], ["confirmed", "Đã đặt"], ["arrived", "Đã đến"], ["cancelled", "Đã hủy"], ["expired", "Hết hạn"]];
const ALLOCATION_STATES = [["", "Tất cả"], ["active", "Đang hiệu lực"], ["cancelled", "Đã hủy"]];
const WAITLIST_STATES = [["waiting", "Đang chờ"], ["offered", "Đã có chỗ"], ["cancelled", "Đã hủy"], ["", "Tất cả"]];

function StatusFilter({ value, options, onChange, disabled, label = "Trạng thái" }) {
  return <TextField select size="small" label={label} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} sx={{ minWidth: 180 }}>
    {options.map(([key, text]) => <MenuItem key={key} value={key}>{text}</MenuItem>)}
  </TextField>;
}

const loadVehicleTypes = () => read("/catalog/vehicle-types").then(items);

function MetadataFeedback({ remote, label }) {
  return <>
    {remote.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={remote.reload} disabled={remote.loading}>Thử lại</Button>}>{label}: {remote.error}</Alert>}
    {remote.loading && <Typography role="status">Đang tải {label.toLowerCase()}…</Typography>}
  </>;
}

function OperationWorkspace({ actions = [], children }) {
  return <div>{actions.map((action, index) => <div key={index}>{action.error && <Alert severity="error" sx={{ mb: 2 }}>{action.error}</Alert>}{action.notice && <Alert severity="success" role="status" sx={{ mb: 2 }}>{action.notice}</Alert>}</div>)}{children}</div>;
}

/** Each list is its own remote: one failing API keeps the other sections usable. */
function usePagedList(path, page, extra = "") {
  const key = JSON.stringify([path, page.params.offset, page.filters, extra]);
  const load = useCallback(() => read(path, sessionSearchParams(page.params, page.filters)).then(items), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return useRemote(load);
}

function SiteOperations({ site, initialPlate, initialAction, onCheckoutChange, view = "operations" }) {
  const capabilities = useExpansion();
  const { user } = useContext(AuthContext);
  const [tab, setTab] = useState(view);
  const [selectedStay, setSelectedStay] = useState(null);
  const [receptionDraft, setReceptionDraft] = useState(null);
  const [search, setSearch] = useState(initialAction === "checkout_lookup" ? initialPlate : "");
  const [searchTicket, setSearchTicket] = useState("");
  const [dateRange, setDateRange] = useState({ date_from: "", date_to: "" });
  const invalidDateRange = !!(dateRange.date_from && dateRange.date_to && dateRange.date_from > dateRange.date_to);
  const [checkout, setCheckout] = useState(null);
  const [checkoutIntent, setCheckoutIntent] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [ticket, setTicket] = useState(null);
  const [organizationName, setOrganizationName] = useState("");
  const canManage = ["manager", "admin"].includes(site.role);
  const canHandleExceptions = canManage && ["manager", "admin"].includes(user?.role);
  const prefix = `/sites/${site.id}`;
  const adapters = useMemo(() => checkoutAdapters(api, site.id), [site.id]);
  const loadZones = useCallback(() => read(`${prefix}/zones`).then(items), [prefix]);
  const loadOrganizations = useCallback(() => read(`${prefix}/organizations`).then(items), [prefix]);
  const loadMembers = useCallback(() => canManage ? read(`${prefix}/members`).then(items) : Promise.resolve([]), [prefix, canManage]);
  const loadAvailability = useCallback(() => read(`${prefix}/availability`), [prefix]);
  const vehicleTypes = useRemote(loadVehicleTypes);
  const zones = useRemote(loadZones);
  const organizations = useRemote(loadOrganizations);
  const members = useRemote(loadMembers);
  const availability = useRemote(loadAvailability);
  const sessionsPage = usePage({ license_plate: "", status: view === "history" ? "" : "active" });
  const reservationsPage = usePage({ status: "" });
  const advancePage = usePage({ status: "confirmed" });
  const allocationsPage = usePage({ status: "" });
  const waitlistPage = usePage({ status: "waiting" });
  const sessions = usePagedList(`${prefix}/sessions`, sessionsPage);
  const reservations = usePagedList(`${prefix}/reservations`, reservationsPage);
  const advanceBookings = usePagedList(`${prefix}/advance-bookings`, advancePage);
  const allocations = usePagedList(`${prefix}/allocations`, allocationsPage);
  const waitlist = usePagedList(`${prefix}/waitlist`, waitlistPage);
  // Mutations refresh only the sections that depend on them; every reload keeps its late-result guard.
  const checkInAction = useAction(refreshAll(sessions, availability, advanceBookings, reservations));
  const reservationAction = useAction(refreshAll(reservations, availability));
  const allocationAction = useAction(refreshAll(allocations, availability));
  const waitlistAction = useAction(refreshAll(waitlist, reservations, availability));
  const configAction = useAction(refreshAll(zones, members, availability));
  const organizationAction = useAction(organizations.reload);
  const everything = combineRemotes(vehicleTypes, zones, organizations, members, availability, sessions, reservations, advanceBookings, allocations, waitlist);
  const slots = availability.data?.slots || [];
  const types = admissionVehicleTypes(vehicleTypes.data || []);
  const closeCheckout = () => { setCheckout(null); };
  const openCheckout = (id, intent = "") => { setTicket(null); setCheckoutIntent(intent); setCheckout(id); };
  const Layout = view === "history" ? Workspace : OperationWorkspace;
  useEffect(() => {
    onCheckoutChange(Boolean(checkout) || detailBusy);
    return () => onCheckoutChange(false);
  }, [checkout, detailBusy, onCheckoutChange]);
  return <Layout title={view === "history" ? "Lịch sử xe" : "Vận hành bãi"} description={view === "history" ? "Tra cứu lượt gửi theo biển số, mã vé và thời gian." : "Nhận xe, kiểm tra phí và xử lý xe ra tại một nơi."} remote={everything}
    actions={[checkInAction, reservationAction, allocationAction, waitlistAction, configAction, organizationAction]}>
    {initialPlate && <Alert severity="info">Biển số {initialPlate} được chuyển từ camera. Kiểm tra đúng xe và bãi trước khi xác nhận thao tác.</Alert>}
    {view === "history" && <MetadataFeedback remote={vehicleTypes} label="Loại xe" />}
    {view !== "history" && tab !== "operations" && <div className="page-head"><div><h1>Vận hành bãi</h1><p>Tiếp nhận đặt chỗ và quản lý hoạt động của bãi.</p></div><button className="button secondary" onClick={() => setTab("operations")}>Về xe vào / ra</button></div>}
    {tab === "operations" && <OperationsPanel site={site} availability={availability} vehicleTypes={vehicleTypes} sessions={sessions} page={sessionsPage}
      action={checkInAction} adapters={adapters} selected={selectedStay} onSelect={row => { setSelectedStay(row); if (row) setReceptionDraft(null); }} onCheckout={openCheckout} onDetail={setDetail} onTicket={setTicket}
      initialPlate={receptionDraft?.license_plate || initialPlate} initialTypeId={receptionDraft?.vehicle_type_id || ""} initialAction={receptionDraft ? "check_in" : initialAction} onReservations={() => setTab("reservations")} onRefresh={refreshAll(sessions, availability, advanceBookings, reservations)} />}
    {view !== "history" && <details className="demo-help"><summary>Công cụ vận hành khác</summary><div className="demo-tools"><button className="button secondary small" onClick={() => setTab("availability")}>Chỗ trống</button><button className="button secondary small" onClick={() => setTab("reservations")}>Tiếp nhận đặt chỗ</button>{[["allocations", "Bảo đảm chỗ"], ["waitlist", "Danh sách chờ"], ["fleet", "Đội xe"], ...(capabilities?.site_finance_enabled ? [["finance", "Ca & chứng từ"]] : []), ...(canManage ? [["configuration", "Cấu hình bãi"]] : [])].map(([value, label]) => <button className="button quiet small" key={value} onClick={() => setTab(value)}>{label}</button>)}</div></details>}
    {tab === "history" && <>
      <RemoteSection remote={sessions} title="Tra cứu lượt gửi và cho xe ra" description="Mỗi trang 25 lượt; đổi biển số hoặc trạng thái sẽ về trang đầu.">
        {(rows) => <>
          <Box component="form" onSubmit={(event) => { event.preventDefault(); if (!invalidDateRange) sessionsPage.setFilters({ license_plate: search.trim().toUpperCase(), session_id: searchTicket.trim(), ...dateRange }); }} sx={formLayout}>
            <TextField label="Tìm đúng biển số" value={search} onChange={(event) => setSearch(event.target.value)} slotProps={{ htmlInput: { maxLength: 20 } }} />
            <TextField label="Mã vé (mã lượt)" value={searchTicket} onChange={(event) => setSearchTicket(event.target.value)} slotProps={{ htmlInput: { maxLength: 36 } }} helperText="Nhập đầy đủ mã lượt trên vé để tìm chính xác." />
            <TextField select label="Trạng thái lượt gửi" value={sessionsPage.filters.status} onChange={(event) => sessionsPage.setFilters({ status: event.target.value })}>
              <MenuItem value="active">Đang đỗ</MenuItem><MenuItem value="completed">Đã ra</MenuItem><MenuItem value="cancelled">Đã hủy</MenuItem><MenuItem value="">Tất cả</MenuItem>
            </TextField>
            {capabilities.site_analytics_enabled && <><TextField type="date" label="Ngày vào từ" value={dateRange.date_from} onChange={(event) => setDateRange((old) => ({ ...old, date_from: event.target.value }))}
              error={invalidDateRange} slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: "9998-12-31" } }} />
            <TextField type="date" label="Ngày vào đến" value={dateRange.date_to} onChange={(event) => setDateRange((old) => ({ ...old, date_to: event.target.value }))}
              error={invalidDateRange} helperText={invalidDateRange ? "Ngày kết thúc phải từ ngày bắt đầu trở đi." : "Tính trọn ngày theo giờ Việt Nam."} slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: "9998-12-31" } }} />
            </>}
            <Button type="submit" variant="outlined" disabled={invalidDateRange || sessions.loading}>Tìm lượt gửi</Button>
          </Box>
          <Records rows={rows} columns={[
            { key: "license_plate", label: "Biển số" }, { key: "slot_name", label: "Vị trí" },
            { key: "check_in_time", label: "Giờ vào", render: (row) => dateTime(row.check_in_time) },
            { key: "check_out_time", label: "Giờ ra", render: (row) => dateTime(row.check_out_time) },
            { key: "parking_fee", label: "Phí", render: (row) => row.parking_fee == null ? "Chưa tính phí" : money(row.parking_fee) },
            { key: "status", label: "Trạng thái", render: (row) => <StateChip value={row.status} /> },
            { key: "checkout", label: "Thao tác", render: (row) => <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
              <Button disabled={checkInAction.busy} onClick={() => setDetail(row)}>Chi tiết</Button>
              {row.status === "active" && <Button variant="outlined" disabled={checkInAction.busy} onClick={() => openCheckout(row.id)}>Xem phí / xe ra</Button>}
            </Stack> },
          ]} />
          <PageControls page={sessionsPage.page} count={rows.length} size={sessionsPage.size} busy={sessions.loading || checkInAction.busy} onChange={sessionsPage.setPage} />
        </>}
      </RemoteSection>
    </>}
    {tab === "finance" && <SiteFinance site={site} />}
    {tab === "availability" && <RemoteSection remote={availability} title="Tình trạng vị trí">{(data) => <Availability data={data} vehicleTypes={vehicleTypes.data || []} />}</RemoteSection>}
    {tab === "reservations" && <>
      <Typography color="text.secondary">Khách đặt chỗ trong cổng khách hàng. Khi xe đến, kiểm tra đặt chỗ và xác nhận tiếp nhận tại đây.</Typography>
      <RemoteSection remote={advanceBookings} title="Khách đã đặt trước" description="Biển số do khách khai báo; kiểm tra xe thực tế khi đến bãi."
        actions={<StatusFilter value={advancePage.filters.status} options={RESERVATION_STATES} disabled={advanceBookings.loading} onChange={status => advancePage.setFilters({ status })} />}>
        {rows => <><Records rows={rows} empty="Chưa có đặt trước phù hợp." columns={[
          { key: "license_plate", label: "Biển số" },
          { key: "vehicle_type_id", label: "Loại xe", render: row => (vehicleTypes.data || []).find(type => type.id === row.vehicle_type_id)?.name || "—" },
          { key: "slot_name", label: "Vị trí giữ" }, { key: "start_at", label: "Giờ đến", render: row => dateTime(row.start_at) },
          { key: "arrival_deadline", label: "Hạn tiếp nhận", render: row => dateTime(row.arrival_deadline) },
          { key: "status", label: "Trạng thái", render: row => <StateChip value={row.status} /> },
          { key: "receive", label: "Thao tác", render: row => row.status === "confirmed" ? <Button onClick={() => { setReceptionDraft(row); setSelectedStay(null); setTab("operations"); }}>Kiểm tra & nhận xe</Button> : row.session_id ? <Button onClick={() => setTicket(row.session_id)}>Xem vé</Button> : null },
        ]} /><PageControls page={advancePage.page} count={rows.length} size={advancePage.size} busy={advanceBookings.loading} onChange={advancePage.setPage} /></>}
      </RemoteSection>
      <RemoteSection remote={reservations} title="Lịch đặt chỗ" description="Mỗi trang 25 đặt chỗ, mới nhất trước." actions={<Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
        <StatusFilter value={reservationsPage.filters.status} options={RESERVATION_STATES} disabled={reservations.loading} onChange={(status) => reservationsPage.setFilters({ status })} />
        <Button disabled={reservationAction.busy} onClick={() => void reservationAction.run(() => send(`${prefix}/reservations/expire`), "Đã cập nhật các đặt chỗ quá hạn đến.")}>Cập nhật quá hạn</Button>
      </Stack>}>
        {(rows) => <>
          <BookingRecords rows={rows} slots={slots} busy={reservationAction.busy}
            onArrive={(row) => void reservationAction.run(() => send(`${prefix}/reservations/${row.id}/arrive`), "Đã xác nhận khách đến và ghi nhận xe vào.", () => void sessions.reload())}
            />
          <PageControls page={reservationsPage.page} count={rows.length} size={reservationsPage.size} busy={reservations.loading || reservationAction.busy} onChange={reservationsPage.setPage} />
        </>}
      </RemoteSection>
    </>}
    {tab === "allocations" && <>
      {canManage && <Section title="Cấp quyền bảo đảm chỗ" description="Dành vị trí cho một xe trong khoảng giờ. Quyền này không tự cấp vé tháng và không thu phí.">
        <BookingForm kind="allocation" siteId={site.id} slots={slots} action={allocationAction} onSubmit={(body) => send(`${prefix}/allocations`, body)} />
      </Section>}
      <RemoteSection remote={allocations} title="Vị trí được bảo đảm" description="Mỗi trang 25 quyền, mới nhất trước."
        actions={<StatusFilter value={allocationsPage.filters.status} options={ALLOCATION_STATES} disabled={allocations.loading} onChange={(status) => allocationsPage.setFilters({ status })} />}>
        {(rows) => <>
          <BookingRecords rows={rows} slots={slots} busy={allocationAction.busy}
            onCancel={canManage ? (row) => void allocationAction.run(() => send(`${prefix}/allocations/${row.id}/cancel`), "Đã hủy quyền bảo đảm chỗ.") : undefined} />
          <PageControls page={allocationsPage.page} count={rows.length} size={allocationsPage.size} busy={allocations.loading || allocationAction.busy} onChange={allocationsPage.setPage} />
        </>}
      </RemoteSection>
    </>}
    {tab === "waitlist" && <>
      <Section title="Ghi nhận khách chờ chỗ" description="Danh sách chờ không chiếm sức chứa. Cấp chỗ trống sẽ tạo đặt chỗ thật cho khách.">
        <BookingForm kind="waitlist" siteId={site.id} action={waitlistAction} onSubmit={(body) => send(`${prefix}/waitlist`, body)} />
      </Section>
      <RemoteSection remote={waitlist} title="Danh sách chờ" description="Thứ tự theo thời điểm yêu cầu; mỗi trang 25 yêu cầu."
        actions={<StatusFilter value={waitlistPage.filters.status} options={WAITLIST_STATES} disabled={waitlist.loading} onChange={(status) => waitlistPage.setFilters({ status })} />}>
        {(rows) => <>
          <WaitlistRecords rows={rows} busy={waitlistAction.busy}
            onOffer={(row) => void waitlistAction.run(() => send(`${prefix}/waitlist/${row.id}/offer`), "Đã cấp chỗ. Xem lịch mới trong mục Đặt chỗ.")}
            onCancel={(row) => void waitlistAction.run(() => send(`${prefix}/waitlist/${row.id}/cancel`), "Đã hủy yêu cầu chờ.")} />
          <PageControls page={waitlistPage.page} count={rows.length} size={waitlistPage.size} busy={waitlist.loading || waitlistAction.busy} onChange={waitlistPage.setPage} />
        </>}
      </RemoteSection>
    </>}
    {tab === "fleet" && <>
      <MetadataFeedback remote={organizations} label="Nhóm xe" />
      {canManage && <Section title="Tạo nhóm xe"><Box component="form" sx={formLayout} onSubmit={(event) => {
        event.preventDefault();
        void organizationAction.run(() => send(`${prefix}/organizations`, { name: organizationName.trim() }), "Đã tạo nhóm xe.", () => setOrganizationName(""));
      }}><TextField label="Tên đơn vị / nhóm xe" required value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} slotProps={{ htmlInput: { maxLength: 150 } }} /><Button type="submit" variant="contained" disabled={organizationAction.busy}>Tạo nhóm xe</Button></Box></Section>}
      <FleetSection organizations={organizations.data || []} canManage={canManage} siteId={site.id} />
    </>}
    {tab === "configuration" && canManage && <><MetadataFeedback remote={zones} label="Khu vực" /><MetadataFeedback remote={members} label="Nhân sự" /><SiteConfiguration siteId={site.id} zones={zones.data || []} types={types} members={members.data || []} isAdmin={site.role === "admin"} action={{ ...configAction, busy: configAction.busy || zones.loading || vehicleTypes.loading || members.loading }} /></>}
    {checkout && <CheckoutDialog key={`${site.id}:${checkout}`} sessionId={checkout} siteId={site.id} initialOnline={checkoutIntent === "online"} initialPaymentMethod={checkoutIntent === "cash" ? "cash" : ""} {...adapters} onClose={closeCheckout}
      onCompleted={() => { closeCheckout(); setSelectedStay(null); checkInAction.notify("Đã ghi nhận xe ra."); void refreshAll(sessions, availability)(); }} />}
    {detail && <SessionDetailsDialog key={`${site.id}:${detail.id}`} session={detail} siteId={site.id} canManage={canHandleExceptions}
      onClose={() => setDetail(null)} onBusy={setDetailBusy} onCheckout={openCheckout} onTicket={setTicket}
      onChanged={() => void refreshAll(sessions, availability)()} />}
    <TicketDialog sessionId={ticket} siteId={site.id} canManage={canHandleExceptions} onClose={() => setTicket(null)} onCheckOut={openCheckout} />
  </Layout>;
}

export default function SitesWorkspace({ view = "operations" }) {
  const { user } = useContext(AuthContext);
  const sites = useSites();
  const [params, setParams] = useSearchParams();
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [creatingSite, setCreatingSite] = useState(false);
  const requestedSite = params.get("site");
  const selected = sites.sites.find((site) => String(site.id) === requestedSite) || sites.sites.find((site) => String(site.id) === String(sites.siteId));
  const action = useAction(sites.reload);
  const onCheckoutChange = useCallback((open) => setCheckoutOpen(open), []);
  return <Stack spacing={3}>
    {!sites.singleSiteMode && <Stack direction={{ xs: "column", sm: "row" }} spacing={2} useFlexGap sx={{ alignItems: { sm: "center" } }}>
      <SitePicker sites={sites} label="Bãi đang vận hành" value={selected?.id || ""} disabled={checkoutOpen} sx={{ maxWidth: "100%" }}
        onChange={(value) => { sites.setSiteId(value); setParams({ site: String(value) }); }} />
      {!sites.singleSiteMode && user?.role === "admin" && <Button variant="outlined" disabled={checkoutOpen} onClick={() => setCreatingSite((old) => !old)}>{creatingSite ? "Đóng tạo bãi" : "Tạo bãi mới"}</Button>}
    </Stack>}
    {sites.error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={sites.reload}>Thử lại</Button>}>{sites.error}</Alert>}
    {action.error && <Alert severity="error">{action.error}</Alert>}
    {action.notice && <Alert severity="success">{action.notice}</Alert>}
    {requestedSite && sites.data && !sites.sites.some((site) => String(site.id) === requestedSite) && <Alert severity="warning">Bạn không có quyền truy cập bãi được chọn hoặc bãi đã ngừng hoạt động. Hãy chọn lại bãi và kiểm tra biển số.</Alert>}
    {!sites.singleSiteMode && creatingSite && user?.role === "admin" && <CreateSiteForm action={action} onCreated={(row) => { setParams({ site: String(row.id) }); setCreatingSite(false); }} />}
    {selected ? <SiteOperations key={`${selected.id}:${view}:${params.get("plate") || ""}:${params.get("action") || ""}`} site={selected} view={view}
      initialPlate={requestedSite === String(selected.id) ? params.get("plate") || "" : ""} initialAction={params.get("action")} onCheckoutChange={onCheckoutChange} /> : <Workspace title="Vận hành bãi đỗ" description="Mỗi nhân sự chỉ thao tác tại bãi được phân công." remote={sites}><Alert severity="info">Chưa có bãi được cấp quyền. Quản trị viên có thể tạo bãi và phân công nhân sự.</Alert></Workspace>}
  </Stack>;
}
