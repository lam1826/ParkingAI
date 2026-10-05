import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle } from "@mui/material";
import { PageHeader, ParkingIllustration, PrototypeIcon } from "../../components/common/PrototypeUI";
import SessionFeePayment from "./SessionFeePayment";
import { feeLookupBody, feeLookupTypes, feePaymentChoice, refreshFeeLookup, validFeeLookup } from "./customerFlow";
import { dateTime, items, money, read, send, SitePicker, useAction, useRemote, useSites } from "./shared";

const loadTypes = () => read("/catalog/vehicle-types").then(items);
// Session timestamps without an offset are business time in Vietnam, even on a browser abroad.
const businessMillis = (value) => Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value || "") ? value : `${value}+07:00`);

function SiteFees({ site }) {
  const types = useRemote(loadTypes);
  const loadAvailability = useCallback(() => read(`/sites/${site.id}/availability`), [site.id]);
  const availability = useRemote(loadAvailability);
  const action = useAction();
  const [form, setForm] = useState({ license_plate: "", vehicle_type_id: "", ticket_proof: "" });
  const [proofOpen, setProofOpen] = useState(false);
  const [result, setResult] = useState(null);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);
  // The availability panel lists every active type; the lookup offers only the
  // types this site serves, and a choice the inventory no longer offers is dropped.
  const activeTypes = (types.data || []).filter((row) => row.is_active !== false);
  const choices = feeLookupTypes(types.data, availability);
  const vehicleTypeId = choices.some((row) => String(row.id) === form.vehicle_type_id) ? form.vehicle_type_id : "";
  const type = choices.find((row) => String(row.id) === vehicleTypeId);
  const edit = (key) => (event) => {
    generation.current += 1;
    setResult(null); setPaymentOpen(false);
    setForm((old) => ({ ...old, [key]: event.target.value }));
  };
  const lookup = (event) => {
    event.preventDefault();
    if (action.busy) return;
    const turn = ++generation.current;
    setResult(null); setPaymentOpen(false);
    void action.run(async () => {
      const body = feeLookupBody({ ...form, vehicle_type_id: vehicleTypeId }, site.id);
      const token = localStorage.getItem("token");
      try {
        const data = await send("/me/fee-lookup", body);
        if (turn !== generation.current) return;
        if (token !== localStorage.getItem("token")) throw new Error("Phiên đăng nhập đã thay đổi.");
        if (!validFeeLookup(data)) throw new Error("Chưa xác nhận được số dư hợp lệ. Vui lòng tải lại.");
        return data;
      } catch (error) {
        if (turn !== generation.current) return;
        // The same prompt covers unknown vehicles and missing access without disclosing a plate.
        if (error.response?.status === 404) setProofOpen(true);
        throw error;
      } finally { if (turn === generation.current) setForm((old) => ({ ...old, ticket_proof: "" })); }
    }, "", (data) => { if (data && turn === generation.current) setResult(data); });
  };
  const refreshBalance = () => action.run(async () => {
    if (!result) return;
    const sessionId = result.session.id, token = localStorage.getItem("token"), turn = generation.current;
    try {
      const paymentStatus = await read(`/me/sessions/${encodeURIComponent(sessionId)}/payment-status`);
      if (turn !== generation.current) return;
      if (token !== localStorage.getItem("token")) {
        setResult((old) => old?.session.id === sessionId ? null : old);
        return;
      }
      const updated = refreshFeeLookup(result, paymentStatus);
      if (!updated) throw new Error("Chưa xác nhận được trạng thái và số dư hợp lệ. Hãy tra cứu lại lượt gửi.");
      setResult((old) => old?.session.id === sessionId ? updated : old);
    } catch (error) {
      if (turn !== generation.current) return;
      setResult((old) => old?.session.id === sessionId ? null : old);
      if (token !== localStorage.getItem("token")) return;
      throw error;
    }
  }, "");
  const closePayment = () => {
    setPaymentOpen(false);
    void refreshBalance();
  };
  const balance = result?.payment_status;
  const payment = feePaymentChoice(balance);
  const completed = result?.session.status === "completed", cancelled = result?.session.status === "cancelled";
  const closed = completed || cancelled;
  const minutes = result ? Math.max(0, Math.floor((businessMillis(balance.server_now) - businessMillis(result.session.check_in_time)) / 60000)) : 0;
  const duration = Number.isFinite(minutes) ? `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút` : "Đang cập nhật";
  return <>
    <PageHeader title="Tra phí & thanh toán" description="Xem thời gian gửi và thanh toán trước khi lấy xe." />
    <div className="content-grid">
      <div>
        <section className="surface">
          <div className="section-head"><h2>Xe của bạn</h2><PrototypeIcon name="car" /></div>
          {types.error && <Alert severity="error" action={<Button onClick={types.reload}>Thử lại</Button>}>{types.error}</Alert>}
          <form onSubmit={lookup}>
            <div className="field"><label htmlFor="customer-plate">{type?.requires_plate === false ? "Mã xe" : "Biển số xe"}</label><input id="customer-plate" value={form.license_plate} onChange={edit("license_plate")} placeholder={type?.requires_plate === false ? "Mã xe nhận tại bãi" : "Ví dụ: 59A-123.45"} maxLength={20} required autoComplete="off" disabled={action.busy} /></div>
            <div className="field"><label htmlFor="customer-type">Loại xe</label><select id="customer-type" required value={vehicleTypeId} onChange={edit("vehicle_type_id")} aria-describedby="customer-lookup-help" disabled={action.busy || types.loading || availability.loading || !!types.error}><option value="" disabled>Chọn đúng loại xe trên vé</option>{choices.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></div>
            <p id="customer-lookup-help" className="muted" style={{ fontSize: 13, marginBottom: 16 }}>Tra phí cho xe đang gửi tại bãi này. Chọn đúng loại xe trên vé; biển số có thể nhập có hoặc không có dấu chấm, gạch ngang.</p>
            <button className="button primary full" type="submit" disabled={action.busy || types.loading || !!types.error || !vehicleTypeId}><PrototypeIcon name="search" />{action.busy ? "Đang tra phí…" : "Tra phí gửi xe"}</button>
          </form>
          <p className="muted" style={{ fontSize: 12, marginTop: 16 }}>Xe chưa liên kết? <button className="button quiet small" type="button" disabled={action.busy} onClick={() => { setProofOpen((old) => !old); setForm((old) => ({ ...old, ticket_proof: "" })); }}>Dùng mã trên vé</button></p>
          <p className="muted" style={{ fontSize: 13 }}>Xe đã ra bãi? <Link to="/portal?tab=tickets">Xem vé và lịch sử của bạn</Link>.</p>
        </section>
        {action.error && <div role="alert" className="inline-note warning">{action.error}</div>}
        {proofOpen && !result && <section className="surface">
          <h2>Xác nhận lượt gửi của bạn</h2>
          <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Kiểm tra lại biển số và loại xe đã chọn. Nếu xe chưa liên kết tài khoản, nhập mã tra phí riêng trên vé của lượt đang gửi; đây là mã khác với mã lượt dành cho nhân viên.</p>
          <form onSubmit={lookup} style={{ marginTop: 18 }}>
            <div className="field"><label htmlFor="ticket">Mã vé</label><input id="ticket" type="password" value={form.ticket_proof} onChange={edit("ticket_proof")} placeholder="Mã tra phí riêng trên vé" maxLength={160} required autoComplete="off" disabled={action.busy} /></div>
            <button className="button primary" type="submit" disabled={action.busy || !vehicleTypeId || !form.license_plate.trim()}>Xác nhận vé</button>
          </form>
        </section>}
        {result && <section className="surface fee-panel">
          <div className="section-head"><span className="plate">{result.session.license_plate}</span><span className={`badge ${cancelled ? "neutral" : completed || !balance.balance_due ? "success" : "warning"}`}>{cancelled ? "Lượt gửi đã hủy" : completed ? "Xe đã ra bãi" : balance.balance_due ? "Chưa thanh toán đủ" : "Không còn phí hiện tại"}</span></div>
          {!cancelled && <><div className="muted" style={{ fontSize: 13 }}>{completed ? "Đã thu khi ra" : "Số tiền còn phải trả"}</div><div className="fee-total">{money(balance.balance_due)}</div></>}
          <div className="fee-lines">
            <div className="fee-line"><span>Loại xe</span><span>{types.data?.find((row) => row.id === result.session.vehicle_type_id)?.name || "—"}</span></div>
            <div className="fee-line"><span>Giờ vào</span><span>{dateTime(result.session.check_in_time)}</span></div>
            {!closed && <div className="fee-line"><span>Thời gian gửi</span><span>{duration}</span></div>}
            <div className="fee-line"><span>Phí gửi xe</span><span>{money(balance.gross_fee)}</span></div>
            <div className="fee-line"><span>Đã trả online</span><span>{money(balance.online_paid)}</span></div>
          </div>
          {closed ? <><p className="inline-note">{cancelled ? "Lượt gửi đã hủy. Không thanh toán thêm cho lượt này." : "Lượt gửi đã kết thúc; khoản thu khi xe ra đã được xác nhận."}</p><Link className="button quiet small" to="/portal?tab=tickets">Xem vé và lịch sử</Link></> : balance.balance_due > 0 ? (payment.online ? <button className="button primary full" type="button" disabled={action.busy} onClick={() => setPaymentOpen(true)}>Thanh toán online <PrototypeIcon name="arrow" /></button> : <p className="inline-note" role="status">{payment.message}</p>) : <><div className="receipt-success"><PrototypeIcon name="check" />Không còn phí cần trả tại thời điểm tra cứu.</div><p className="muted" style={{ fontSize: 12 }}>Phí sẽ được kiểm tra lại khi xe ra nếu bạn gửi thêm thời gian.</p></>}
        </section>}
      </div>
      <section className="surface availability-panel">
        <div className="section-head"><h2>Còn chỗ cho chuyến đi của bạn</h2></div>
        <div className="parking-illustration"><ParkingIllustration /></div>
        {availability.error && <Alert severity="error" action={<Button onClick={availability.reload}>Thử lại</Button>}>{availability.error}</Alert>}
        {(availability.loading || types.loading) && <p className="muted" role="status">Đang kiểm tra chỗ trống…</p>}
        {availability.data && activeTypes.map((row) => {
          const slots = availability.data.slots.filter((slot) => slot.vehicle_type_id === row.id);
          const available = slots.filter((slot) => slot.available_now).length;
          return <div key={row.id}><div className="capacity-row"><span>{row.name}</span><span><strong>{available}</strong> / {slots.length} chỗ nhận xe</span></div><div className="capacity-meter"><div className="capacity-fill" style={{ width: `${available / Math.max(1, slots.length) * 100}%` }} /></div></div>;
        })}
        <p>Bạn có thể đến gửi trực tiếp. Đặt trước khi muốn giữ sẵn một chỗ phù hợp.</p>
        <Link className="button quiet" to="/reservations">Đặt chỗ trước <PrototypeIcon name="arrow" /></Link>
      </section>
    </div>
    <Dialog open={paymentOpen && Boolean(result) && payment.online} onClose={closePayment} fullWidth maxWidth="sm" aria-labelledby="customer-payment-title">
      <div className="prototype-ui" style={{ background: "white", minHeight: 0 }}>
        <DialogTitle id="customer-payment-title">Thanh toán phí gửi xe</DialogTitle>
        <DialogContent>{paymentOpen && result && <SessionFeePayment key={result.session.id} sessionId={result.session.id} onChanged={refreshBalance} />}</DialogContent>
        <DialogActions><Button onClick={closePayment}>Đóng</Button></DialogActions>
      </div>
    </Dialog>
  </>;
}

export default function CustomerFees() {
  const sites = useSites();
  const selected = sites.sites.find((row) => String(row.id) === String(sites.siteId));
  return <>{sites.sites.length > 1 && !sites.singleSiteMode && <SitePicker sites={sites} sx={{ mb: 2 }} />}{selected ? <SiteFees key={selected.id} site={selected} /> : <><PageHeader title="Tra phí & thanh toán" description="Xem thời gian gửi và thanh toán trước khi lấy xe." />{sites.error ? <Alert severity="error" action={<Button onClick={sites.reload}>Thử lại</Button>}>{sites.error}</Alert> : <p className="muted" role="status">{sites.loading ? "Đang tải bãi đỗ…" : "Chưa có bãi đang hoạt động."}</p>}</>}</>;
}
