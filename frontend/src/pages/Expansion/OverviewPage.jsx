import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { canViewReportRevenue } from "../../utils/coreAnalytics";
import { hasMinimumRole } from "../../constants/roles";
import { toBusinessDateString } from "../../utils/businessDate";
import { settlementAmounts } from "../ParkingSession/settlementAmounts";
import { PrototypeIcon } from "../../components/common/PrototypeUI";
import { dateTime, items, money, read, Records, SitePicker, useRemote, useSites, Workspace } from "./shared";

async function loadOpenBalances(prefix) {
  const active = [];
  for (let offset = 0; ; offset += 100) {
    const page = items(await read(`${prefix}/sessions`, { status: "active", limit: 100, offset }));
    active.push(...page);
    if (page.length < 100) break;
    if (active.length >= 1000) throw new Error("Vui lòng xem phí từng lượt trong Vận hành.");
  }
  const amounts = [];
  // Limit concurrent requests; the server remains the sole source of fee arithmetic.
  for (let index = 0; index < active.length; index += 4) {
    const batch = await Promise.all(active.slice(index, index + 4).map(async session => {
      const quote = await read(`${prefix}/sessions/${session.id}/checkout-quote`);
      const value = settlementAmounts(quote);
      if (!value) throw new Error("Chưa tổng hợp được phí đang gửi.");
      return value.due;
    }));
    amounts.push(...batch);
  }
  return { due: amounts.reduce((sum, amount) => sum + amount, 0), unpaid: amounts.filter(amount => amount > 0).length };
}

function QuickLink({ to, children }) {
  return <Link className="button quiet" to={to}>{children}<PrototypeIcon name="arrow" /></Link>;
}

function SiteOverview({ site }) {
  const prefix = `/sites/${site.id}`;
  const today = toBusinessDateString();
  const financial = hasMinimumRole(site.role, "manager");
  const loadReport = useCallback(() => read(`${prefix}/reports/summary`, { period: "day", anchor_date: today }), [prefix, today]);
  const loadInventory = useCallback(async () => {
    const [availability, types] = await Promise.all([read(`${prefix}/availability`), read("/catalog/vehicle-types")]);
    return { availability, types: items(types) };
  }, [prefix]);
  const loadMoney = useCallback(async () => financial ? Promise.all([
    read(`${prefix}/revenue`, { date_from: today, date_to: today }), loadOpenBalances(prefix),
  ]).then(([revenue, balance]) => ({ revenue, balance })) : null, [prefix, today, financial]);
  const report = useRemote(loadReport), inventory = useRemote(loadInventory), finance = useRemote(loadMoney);
  const data = report.data, availability = inventory.data?.availability;
  const rows = (inventory.data?.types || []).map(type => {
    const slots = availability.slots.filter(slot => slot.vehicle_type_id === type.id);
    return { id: type.id, name: type.name || type.type_name, occupied: slots.filter(slot => slot.is_occupied).length,
      available: slots.filter(slot => slot.available_now).length, reserved: slots.filter(slot => slot.reserved).length, total: slots.length };
  });
  const cards = [[availability?.occupied, "Xe đang gửi"], [availability?.available_now, "Chỗ nhận xe ngay"], [data?.total_arrivals, "Lượt vào hôm nay"], [data?.total_departures, "Lượt ra hôm nay"]];
  return <>
    {[report, inventory].map((remote, index) => remote.error && <div className="inline-note warning" role="alert" key={index}>{remote.error} <button className="button quiet small" onClick={remote.reload}>Thử lại</button></div>)}
    {(report.loading || inventory.loading) && <p className="page-status" role="status">Đang cập nhật tình hình bãi…</p>}
    <div className="overview-metrics">{cards.map(([value, label]) => <div className="overview-metric" key={label}><span>{label}</span><strong className="tabular">{value ?? "—"}</strong></div>)}</div>
    {data && canViewReportRevenue(data, site.role) && <section className="surface">
      <div className="section-head"><h2>Thu tiền hôm nay</h2><span className="badge neutral">Theo chứng từ</span></div>
      {finance.error && <div className="inline-note warning" role="alert">Chưa tổng hợp được khoản thu. <button className="button quiet small" onClick={finance.reload}>Thử lại</button></div>}
      <div className="split"><div className="fee-lines"><div className="fee-line"><span>Thu ròng hôm nay</span><strong>{finance.data ? money(finance.data.revenue.total_revenue) : "—"}</strong></div><div className="fee-line"><span>Chứng từ thu / hoàn</span><strong>{finance.data?.revenue.payment_count ?? "—"}</strong></div></div>
        <div className="fee-lines"><div className="fee-line"><span>Còn phải thu tại thời điểm này</span><strong>{finance.data ? money(finance.data.balance.due) : "—"}</strong></div><div className="fee-line"><span>Lượt đang gửi còn phí</span><strong>{finance.data?.balance.unpaid ?? "—"}</strong></div></div></div>
      <p className="inline-note">Thu ròng đã trừ hoàn tiền, không gồm QR mô phỏng. Khoản còn phải thu là phí hiện tại của các xe đang gửi và có thể tăng theo thời gian.</p>
    </section>}
    <section className="surface"><div className="section-head"><h2>Tình trạng toàn bãi</h2><span className="muted">{availability ? `${availability.occupied}/${availability.total} vị trí đang có xe` : "Đang tải…"}</span></div>
      <Records rows={rows} columns={[
        { key: "name", label: "Loại xe", render: row => <strong>{row.name}</strong> }, { key: "occupied", label: "Đang gửi" },
        { key: "available", label: "Nhận xe ngay", render: row => <span className={`badge ${row.available ? "success" : "warning"}`}>{row.available}</span> },
        { key: "reserved", label: "Giữ trước" }, { key: "total", label: "Sức chứa" },
      ]} empty={inventory.loading ? "Đang tải chỗ đỗ…" : "Chưa có loại xe hoặc vị trí phục vụ."} />
      {availability?.inactive_slots > 0 && <p className="inline-note">{availability.inactive_slots} vị trí tạm ngừng không tính vào sức chứa đang phục vụ.</p>}
    </section>
    {availability?.available_now === 0 && <section className="surface"><div className="section-head"><h2>Cần theo dõi</h2></div><div className="overview-alert"><div><strong>Chưa còn chỗ nhận xe ngay</strong><p>Kiểm tra vị trí đang có xe và chỗ giữ trước.</p></div><QuickLink to="/parking-slots">Xem bãi đỗ</QuickLink></div></section>}
    <div className="overview-links"><QuickLink to="/customers">Khách & vé</QuickLink><QuickLink to="/reports">Báo cáo & AI</QuickLink><QuickLink to="/parking-slots">Sơ đồ bãi</QuickLink>{site.role === "admin" && <QuickLink to="/users">Quản lý tài khoản</QuickLink>}</div>
    {data?.current_availability?.as_of && <p className="muted overview-updated">Cập nhật {dateTime(data.current_availability.as_of)}</p>}
  </>;
}

export default function OverviewPage() {
  const sites = useSites();
  const [revision, setRevision] = useState(0);
  const site = sites.sites.find(row => String(row.id) === String(sites.siteId));
  return <Workspace title="Tổng quan bãi đỗ" description={`Hôm nay, ${toBusinessDateString().split("-").reverse().join("/")} · tình hình chỗ đỗ và thu phí.`} remote={{ ...sites, reload: async () => { await sites.reload(); setRevision(value => value + 1); } }}
    tools={<Link className="button primary" to="/sites">Vào vận hành<PrototypeIcon name="arrow" /></Link>}>
    <SitePicker sites={sites} />
    {site ? <SiteOverview key={`${site.id}-${revision}`} site={site} /> : !sites.loading && <p className="inline-note">Chưa có bãi được cấp quyền. Liên hệ quản trị viên để được phân công.</p>}
  </Workspace>;
}
