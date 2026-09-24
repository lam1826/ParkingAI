import { useCallback, useState } from "react";
import { Alert, Button } from "@mui/material";
import CameraOperations from "./CameraOperations.jsx";
import OperationIcon from "./OperationIcon";
import { admissionChoices, operationLookup, operationTypeName } from "./operationsState";
import { items, read, send, dateTime, money, PageControls, useAction, useRemote } from "./shared";
import { settlementAmounts } from "../ParkingSession/settlementAmounts";
import { formatParkingDuration } from "../ParkingSession/sessionPresentation";
import BillingBasisDetails from "../ParkingSession/components/BillingBasisDetails";
import PrepaidDetails from "../ParkingSession/components/PrepaidDetails";

const time = value => value ? new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Ho_Chi_Minh" }).format(new Date(value)) : "—";

function SelectedStay({ session, vehicleTypes, slots, adapters, onCheckout, onDetail, onTicket }) {
  const sessionId = session?.id, status = session?.status;
  const load = useCallback(() => sessionId && status === "active" ? adapters.loadQuote(sessionId) : Promise.resolve(null), [sessionId, status, adapters]);
  const remote = useRemote(load);
  const quote = remote.data, amounts = settlementAmounts(quote);
  const typeName = quote?.vehicle_type_name || operationTypeName(session, vehicleTypes, slots);
  return <section className="surface fee-panel">
    {!session ? <><div className="section-head"><h2>Thông tin lượt gửi</h2></div><div className="empty"><OperationIcon name="ticket" />Nhập biển số hoặc chọn một xe bên dưới.<br />Phí và thao tác thanh toán sẽ hiện tại đây.</div></> : <>
      <div className="section-head"><span className="plate">{quote?.license_plate || session.license_plate}</span>{amounts && <span className={`badge ${amounts.due ? "warning" : "success"}`}>{amounts.due ? "Chưa thanh toán đủ" : "Đã thanh toán"}</span>}</div>
      {remote.loading && <p role="status" className="muted">Đang lấy phí từ bãi xe…</p>}
      {remote.error && <Alert severity="error" action={<Button onClick={remote.reload} color="inherit">Thử lại</Button>}>{remote.error}</Alert>}
      {amounts && <><div className="muted" style={{ fontSize: 13 }}>{quote.prepaid ? "Phí phát sinh cần thu" : "Số tiền còn phải trả"}</div><div className="fee-total">{money(amounts.due)}</div></>}
      <div className="fee-lines">
        <div className="fee-line"><span>Loại xe</span><span>{typeName}</span></div>
        <div className="fee-line"><span>Giờ vào</span><span>{dateTime(quote?.check_in_time || session.check_in_time)}</span></div>
        {quote && <div className="fee-line"><span>Thời gian gửi</span><span>{formatParkingDuration(quote.duration_minutes)}</span></div>}
        {quote?.monthly_coverage_end && <div className="fee-line"><span>Vé tháng áp dụng</span><span>Đến hết {quote.monthly_coverage_end}</span></div>}
        {amounts && <><div className="fee-line"><span>Phí gửi xe</span><span>{money(amounts.gross)}</span></div><div className="fee-line"><span>Đã thanh toán</span><span>{money(amounts.paid)}</span></div></>}
      </div>
      <div className="fee-line" style={{ marginTop: 12 }}><span>Vị trí đỗ</span><span>{quote?.slot_name || session.slot_name || "—"}</span></div>
      {session.status === "active" && <div className="form-actions">
        {amounts?.due > 0 ? <><button className="button primary" onClick={() => onCheckout(session.id, "online")}>Tạo QR cho khách</button><button className="button secondary" onClick={() => onCheckout(session.id, "cash")}>Thu tiền mặt</button></> : <button className="button primary full" onClick={() => onCheckout(session.id)}>{amounts?.due === 0 ? "Ghi nhận xe ra" : "Kiểm tra phí & xe ra"}<OperationIcon name="arrow" /></button>}
      </div>}
      <details className="demo-help"><summary>Xem vé của lượt này</summary><button className="button quiet small" onClick={() => onTicket(session.id)}>Mở vé / in vé</button><button className="button quiet small" onClick={() => onDetail(session)}>Chi tiết lượt gửi</button></details>
      {quote && <details className="demo-help" style={{ marginTop: 8 }}><summary>Căn cứ giá & quyền lợi vé</summary><PrepaidDetails prepaid={quote.prepaid} /><BillingBasisDetails basis={quote.billing_basis} preview /><p>Phí được kiểm tra lại khi xác nhận xe ra.</p></details>}
    </>}
  </section>;
}

export default function OperationsPanel({ site, availability, vehicleTypes, sessions, page, action, adapters, selected, onSelect, onCheckout, onDetail, onTicket, initialPlate = "", initialTypeId = "", initialAction, onReservations, onRefresh }) {
  const [mode, setMode] = useState("manual");
  const [direction, setDirection] = useState(initialAction === "checkout_lookup" ? "exit" : "entry");
  const [form, setForm] = useState({ license_plate: initialAction === "check_in" ? initialPlate : "", vehicle_type_id: initialTypeId, parking_slot_id: "" });
  const [query, setQuery] = useState(initialAction === "checkout_lookup" ? initialPlate : "");
  const [queryKind, setQueryKind] = useState("plate");
  const [chooseSlot, setChooseSlot] = useState(false);
  const lookup = useAction();
  const choices = admissionChoices(vehicleTypes.data || [], availability.data?.slots || [], form.vehicle_type_id, form.parking_slot_id);
  const admissionAvailable = !availability.loading && !availability.error && !vehicleTypes.loading && !vehicleTypes.error && !!choices.typeId && (!form.parking_slot_id || !!choices.slotId);
  const ready = admissionAvailable && (!choices.requiresPlate || !!form.license_plate.trim());
  const current = sessions.data?.find(row => row.id === selected?.id) || selected;
  const rows = sessions.data || [];
  const submitEntry = event => {
    event.preventDefault();
    if (!ready || action.busy) return;
    void action.run(() => send(`/sites/${site.id}/check-in`, { license_plate: form.license_plate.trim().toUpperCase(), vehicle_type_id: Number(choices.typeId), ...(form.parking_slot_id ? { parking_slot_id: Number(choices.slotId) } : {}) }), "Đã ghi nhận xe vào.", row => {
      onSelect({ ...row, id: row.session_id || row.id }); setForm(old => ({ ...old, license_plate: "", parking_slot_id: "" }));
    });
  };
  const submitLookup = event => {
    event.preventDefault(); onSelect(null);
    void lookup.run(async () => {
      const found = items(await read(`/sites/${site.id}/sessions`, operationLookup(query, queryKind)));
      if (found.length !== 1) throw new Error(found.length ? "Có nhiều lượt phù hợp. Hãy dùng mã vé để xác định đúng lượt." : "Không tìm thấy xe đang gửi. Kiểm tra biển số hoặc mã vé; lượt đã ra nằm trong Lịch sử xe.");
      onSelect(found[0]); return found[0];
    }, "Đã tìm thấy lượt gửi.");
  };
  return <>
    <div className="page-head"><div><h1>Vận hành bãi</h1><p>Nhận xe, kiểm tra phí và xử lý xe ra tại một nơi.</p></div><div className="head-actions"><div className="segments" aria-label="Cách nhận xe">{[["manual", "car", "Nhập tay"], ["camera", "camera", "Camera"]].map(([value, icon, label]) => <button key={value} className={mode === value ? "active" : ""} aria-pressed={mode === value} onClick={() => setMode(value)}><OperationIcon name={icon} style={{ width: 20, height: 20 }} />{label}</button>)}</div></div></div>
    <div className="stat-strip" aria-label="Tình trạng bãi"><span className="stat-item"><strong>{availability.data?.occupied ?? "—"}</strong> xe đang gửi</span>{choices.types.map(type => <span className="stat-item" key={type.id}><strong>{availability.data ? (availability.data.slots || []).filter(slot => slot.vehicle_type_id === type.id && slot.available_now).length : "—"}</strong> chỗ {type.name.toLowerCase()}</span>)}</div>
    <div className="content-grid">
      <section className="surface">
        <div className="toolbar"><h2>{mode === "manual" ? "Nhập thông tin xe" : "Đọc biển số"}</h2><div className="segments" aria-label="Hướng xe">{[["entry", "Xe vào"], ["exit", "Xe ra"]].map(([value, label]) => <button key={value} className={direction === value ? "active" : ""} aria-pressed={direction === value} onClick={() => setDirection(value)}>{label}</button>)}</div></div>
        {mode === "camera" ? <CameraOperations key={direction} site={site} direction={direction} onCheckout={onCheckout} onManual={(plate, lane) => {
          setMode("manual"); setDirection(lane === "exit" ? "exit" : "entry"); setForm(old => ({ ...old, license_plate: plate })); setQueryKind("plate"); setQuery(plate); onSelect(null);
        }} onPassage={(result, { updateSelection = true } = {}) => {
          if (["entered", "exited"].includes(result.state)) void onRefresh();
          if (!updateSelection) return;
          if (result.state === "exited") onSelect(null);
          else if (result.session_id) onSelect({ id: result.session_id, license_plate: result.license_plate, status: "active" });
        }} /> : direction === "entry" ? <form onSubmit={submitEntry}>
          <div className="field"><label htmlFor="operation-plate">{choices.requiresPlate ? "Biển số xe" : "Mã xe / mã vé"}</label><input id="operation-plate" placeholder={choices.requiresPlate ? "Ví dụ: 51K-246.80" : "Để trống để tự cấp mã xe"} required={choices.requiresPlate} maxLength={20} autoComplete="off" value={form.license_plate} onChange={event => setForm(old => ({ ...old, license_plate: event.target.value }))} disabled={action.busy} />{!choices.requiresPlate && <small>Để trống để hệ thống cấp mã xe trên vé.</small>}</div>
          <div className="field"><label htmlFor="operation-type">Loại xe</label><select id="operation-type" required value={choices.typeId} disabled={vehicleTypes.loading || !!vehicleTypes.error || action.busy} onChange={event => setForm(old => ({ ...old, vehicle_type_id: event.target.value, parking_slot_id: "" }))}><option value="" disabled>Chọn loại xe</option>{choices.types.map(type => <option key={type.id} value={type.id}>{type.name}</option>)}</select>{form.vehicle_type_id && !choices.typeId && <small>Loại đã chọn ngừng nhận xe. Hãy chọn lại.</small>}</div>
          <div className="inline-note">Tự chọn vị trí phù hợp. Xe có thể vào mà không cần đặt trước.</div>
          {chooseSlot && <div className="field"><label htmlFor="operation-slot">Vị trí nhận xe</label><select id="operation-slot" value={form.parking_slot_id && choices.slotId ? choices.slotId : ""} disabled={action.busy} onChange={event => setForm(old => ({ ...old, parking_slot_id: event.target.value }))}><option value="">Hệ thống xếp chỗ</option>{choices.slots.map(slot => <option key={slot.id} value={slot.id}>{slot.slot_name} · {slot.zone_name}</option>)}</select>{form.parking_slot_id && !choices.slotId && <small>Vị trí đã chọn không còn trống. Hãy chọn lại hoặc để hệ thống xếp chỗ.</small>}</div>}
          {(availability.error || vehicleTypes.error) && <Alert severity="error">{availability.error || vehicleTypes.error}</Alert>}
          <button className="button primary full" type="submit" disabled={!admissionAvailable || action.busy}>{action.busy ? "Đang nhận xe…" : "Ghi nhận xe vào"}<OperationIcon name="arrow" /></button>
        </form> : <form onSubmit={submitLookup}>
          <div className="field"><label htmlFor="operation-query">{queryKind === "ticket" ? "Mã lượt trên vé" : "Biển số / mã xe"}</label><input id="operation-query" required value={query} autoComplete="off" placeholder={queryKind === "ticket" ? "Nhập đầy đủ mã lượt trên vé" : "Ví dụ: 51K-246.80"} maxLength={queryKind === "ticket" ? 36 : 20} onChange={event => setQuery(event.target.value)} /></div>
          {lookup.error && <Alert severity="error">{lookup.error}</Alert>}
          <button className="button primary full" type="submit" disabled={lookup.busy}>{lookup.busy ? "Đang tra cứu…" : "Tra phí & xử lý xe ra"}<OperationIcon name="arrow" /></button>
          <button className="button quiet small" type="button" style={{ marginTop: 12 }} onClick={() => { setQueryKind(old => old === "plate" ? "ticket" : "plate"); setQuery(""); }}>{queryKind === "plate" ? "Tra bằng mã vé" : "Tra bằng biển số / mã xe"}</button>
        </form>}
      </section>
      <SelectedStay key={current?.id || "empty"} session={current} vehicleTypes={vehicleTypes.data || []} slots={availability.data?.slots || []} adapters={adapters} onCheckout={onCheckout} onDetail={onDetail} onTicket={onTicket} />
    </div>
    <section className="surface" style={{ marginTop: 24 }}><div className="section-head"><div><h2>Xe đang trong bãi <span className="badge neutral">{availability.data?.occupied ?? rows.length}</span></h2><p>Chọn một xe để xem phí, thu tiền hoặc cho xe ra. Xe không có biển số dùng mã xe/mã vé.</p></div></div>
      {sessions.error && <Alert severity="error" action={<Button onClick={sessions.reload}>Thử lại</Button>}>{sessions.error}</Alert>}
      {sessions.loading && <p role="status" className="muted">Đang tải xe đang gửi…</p>}
      <div className="table-wrap"><table className="data-table"><thead><tr><th>Biển số / mã xe</th><th>Loại xe</th><th>Giờ vào</th><th>Vị trí</th><th>Còn trả</th><th style={{ position: "relative" }}><span className="sr-only">Thao tác</span></th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td className="plate">{row.license_plate}</td><td>{operationTypeName(row, vehicleTypes.data || [], availability.data?.slots || [])}</td><td title={dateTime(row.check_in_time)}>{time(row.check_in_time)}</td><td>{row.slot_name}</td><td title="Chọn Xem phí để lấy phí hiện tại">—</td><td><button className="button quiet small" onClick={() => onSelect(row)}>{current?.id === row.id ? "Đang chọn" : "Xem phí"}</button></td></tr>)}</tbody></table>{!rows.length && !sessions.loading && <div className="empty">Bãi chưa có xe.</div>}</div>
      {(page.page > 0 || rows.length >= page.size) && <PageControls page={page.page} count={rows.length} size={page.size} busy={sessions.loading || action.busy} onChange={page.setPage} />}
    </section>
    <details className="demo-help"><summary>Tiếp nhận đặt chỗ & thao tác bổ sung</summary><div className="demo-tools"><button className="button secondary small" onClick={onReservations}>Tiếp nhận xe đã đặt chỗ</button><button className="button secondary small" onClick={() => { setMode("manual"); setDirection("entry"); setChooseSlot(old => !old); }}>{chooseSlot ? "Tự xếp chỗ" : "Chọn vị trí nhận xe"}</button><button className="button quiet small" onClick={onRefresh}>Làm mới dữ liệu</button></div></details>
  </>;
}
