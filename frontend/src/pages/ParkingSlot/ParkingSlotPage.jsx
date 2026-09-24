import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CrudFields, extractErrorMessage } from "../../components/common/CrudPage";
import { PageHeader, WorkspaceTabs, PrototypeIcon } from "../../components/common/PrototypeUI";
import { getParkingSlotVisualStatus } from "../../utils/parkingSlotStatus";
import { vehicleTypeService } from "../VehicleType/services/vehicleTypeService";
import { zoneService } from "../Zone/services/zoneService";
import { parkingSlotService } from "./parkingSlotService";
import { items, read } from "../Expansion/shared";
import useCorePermissions from "../../hooks/useCorePermissions";

const labels = { available: "Còn nhận xe", occupied: "Đang có xe", reserved: "Đã giữ chỗ", inactive: "Ngừng phục vụ", unknown: "Chưa rõ khả dụng" };
export default function ParkingSlotPage() {
  const { canManageConfiguration } = useCorePermissions();
  const [zones, setZones] = useState([]), [types, setTypes] = useState([]), [slots, setSlots] = useState([]), [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [filters, setFilters] = useState({ zone: "", status: "", type: "" }), [draftFilters, setDraftFilters] = useState(filters);
  const [editor, setEditor] = useState(null), [form, setForm] = useState({}), [formError, setFormError] = useState(""), [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const working = useRef(false), formRef = useRef(null);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [zoneList, typeList, slotList, inventories] = await Promise.all([
        zoneService.getAll(), vehicleTypeService.getAll(), parkingSlotService.getAll(),
        read("/sites").then(data => Promise.all(items(data).map(site => read(`/sites/${site.id}/availability`)))),
      ]);
      setZones(zoneList); setTypes(typeList); setSlots(slotList); setInventory(inventories.flatMap(data => data.slots || []));
    } catch (failure) { setSlots([]); setInventory([]); setError(extractErrorMessage(failure, "Không thể tải sơ đồ chỗ đỗ.")); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (editor) formRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [editor]);
  const enriched = useMemo(() => {
    const zoneMap = new Map(zones.map(row => [row.id, row])), typeMap = new Map(types.map(row => [row.id, row])), live = new Map(inventory.map(row => [row.id, row]));
    return slots.map(slot => ({ ...slot, zone: zoneMap.get(slot.zone_id), vehicleType: typeMap.get(slot.vehicle_type_id), visualStatus: getParkingSlotVisualStatus(slot, zoneMap.get(slot.zone_id), typeMap.get(slot.vehicle_type_id), live.get(slot.id) ?? null) }));
  }, [slots, zones, types, inventory]);
  const filtered = enriched.filter(slot => (!filters.zone || slot.zone_id === Number(filters.zone)) && (!filters.type || slot.vehicle_type_id === Number(filters.type)) && (!filters.status || slot.visualStatus === filters.status));
  const groups = new Map();
  filtered.forEach(slot => { if (!groups.has(slot.zone_id)) groups.set(slot.zone_id, []); groups.get(slot.zone_id).push(slot); });
  const grouped = [...groups.values()].sort((a, b) => (a[0].zone?.name || "").localeCompare(b[0].zone?.name || "", "vi"));
  const totals = enriched.reduce((sum, slot) => { sum[slot.visualStatus] += 1; return sum; }, { available: 0, occupied: 0, reserved: 0, inactive: 0, unknown: 0 });
  const fields = [
    { name: "slot_name", label: "Mã vị trí", required: true },
    { name: "zone_id", label: "Khu vực", type: "select", required: true, options: zones.map(row => ({ value: row.id, label: row.name })) },
    { name: "vehicle_type_id", label: "Loại xe", type: "select", required: true, options: types.map(row => ({ value: row.id, label: row.name })) },
    { name: "is_active", label: "Vị trí hoạt động", type: "boolean" },
  ];
  const open = row => {
    if (!canManageConfiguration || busy) return;
    setEditor(row || {}); setForm({ slot_name: row?.slot_name || "", zone_id: row?.zone_id || "", vehicle_type_id: row?.vehicle_type_id || "", is_active: row?.is_active ?? true }); setFormError(""); setNotice("");
  };
  const save = async event => {
    event.preventDefault();
    if (!canManageConfiguration || working.current) return;
    working.current = true; setBusy(true); setFormError("");
    try {
      const payload = { ...form, zone_id: Number(form.zone_id), vehicle_type_id: Number(form.vehicle_type_id) };
      if (editor.id) await parkingSlotService.update(editor.id, payload); else await parkingSlotService.create(payload);
      setEditor(null); setNotice("Đã lưu vị trí đỗ."); await load();
    } catch (failure) { setFormError(extractErrorMessage(failure, "Không thể lưu vị trí đỗ.")); }
    finally { working.current = false; setBusy(false); }
  };
  const remove = async row => {
    if (!canManageConfiguration || working.current || !window.confirm(`Xóa vị trí ${row.slot_name}?`)) return;
    working.current = true; setBusy(true);
    try { await parkingSlotService.delete(row.id); setNotice("Đã xóa vị trí đỗ."); await load(); }
    catch (failure) { setError(extractErrorMessage(failure, "Không thể xóa vị trí đã được sử dụng. Có thể ngừng hoạt động để giữ lịch sử.")); }
    finally { working.current = false; setBusy(false); }
  };
  const resetFilters = () => { const empty = { zone: "", status: "", type: "" }; setFilters(empty); setDraftFilters(empty); };
  return <>
    <PageHeader title="Bãi đỗ" description="Quản lý khu vực, chỗ đỗ và khả năng nhận xe tại một bãi." actions={canManageConfiguration && <button className="button primary" disabled={busy} onClick={() => open(null)}><PrototypeIcon name="plus" />Thêm vị trí đỗ</button>} />
    <WorkspaceTabs />
    {!canManageConfiguration && <p className="inline-note">Bạn có thể tra cứu chỗ đỗ. Quản lý phụ trách thêm và sửa vị trí.</p>}
    <div className="stat-strip"><span className="stat-item"><strong>{totals.available}</strong>còn nhận xe</span><span className="stat-item"><strong>{totals.occupied}</strong>đang có xe</span><span className="stat-item"><strong>{totals.reserved}</strong>giữ chỗ</span><span className="stat-item"><strong>{totals.inactive}</strong>ngừng phục vụ</span>{totals.unknown > 0 && <span className="stat-item"><strong>{totals.unknown}</strong>chưa rõ khả dụng</span>}</div>
    {notice && <p className="inline-note success" role="status">{notice}</p>}
    {editor && canManageConfiguration && <section ref={formRef} className="surface core-editor"><div className="section-head"><h2>{editor.id ? "Sửa" : "Thêm"} vị trí đỗ</h2></div><form className="form-grid" onSubmit={save}><CrudFields fields={fields} form={form} disabled={busy} onChange={(name, value) => setForm(old => ({ ...old, [name]: value }))} /><p className="inline-note core-wide">Ô có xe, giữ chỗ hoặc lịch sử sử dụng được bảo vệ khỏi thay đổi không phù hợp.</p>{formError && <p role="alert" className="form-error core-wide">{formError}</p>}<div className="form-actions core-wide"><button className="button primary" disabled={busy}>{busy ? "Đang lưu…" : "Lưu thay đổi"}</button><button type="button" className="button secondary" disabled={busy} onClick={() => setEditor(null)}>Hủy</button></div></form></section>}
    <section className="surface"><form className="form-grid" onSubmit={event => { event.preventDefault(); setFilters(draftFilters); }}>
      <label className="field">Khu vực<select value={draftFilters.zone} onChange={event => setDraftFilters(old => ({ ...old, zone: event.target.value }))}><option value="">Tất cả khu vực</option>{zones.map(zone => <option key={zone.id} value={zone.id}>{zone.name}</option>)}</select></label>
      <label className="field">Tình trạng vị trí<select value={draftFilters.status} onChange={event => setDraftFilters(old => ({ ...old, status: event.target.value }))}><option value="">Tất cả trạng thái</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="form-actions core-wide"><button className="button secondary">Lọc vị trí</button><button type="button" className="button quiet" onClick={resetFilters}>Xóa bộ lọc</button><button type="button" className="button quiet" disabled={loading || busy} onClick={load}>Làm mới</button><details><summary className="muted">Lọc theo loại xe</summary><label className="field">Loại xe<select value={draftFilters.type} onChange={event => setDraftFilters(old => ({ ...old, type: event.target.value }))}><option value="">Tất cả loại xe</option>{types.map(type => <option key={type.id} value={type.id}>{type.name}</option>)}</select></label></details></div>
    </form></section>
    {error && <p className="form-error" role="alert">{error}</p>}
    {loading ? <section className="surface empty" role="status">Đang tải sơ đồ chỗ đỗ…</section> : !grouped.length ? <section className="surface empty">Không có vị trí phù hợp. Đổi bộ lọc hoặc thêm vị trí mới.</section> : grouped.map(group => <section className="surface core-zone" key={group[0].zone_id}><div className="section-head"><div><h2>{group[0].zone?.name || "Chưa xác định khu vực"}</h2><p>{group.length} vị trí trong bộ lọc</p></div></div><div className="availability-grid core-slot-grid">{group.map(slot => <div key={slot.id} className={`slot ${slot.visualStatus === "reserved" ? "held" : slot.visualStatus === "unknown" ? "inactive" : slot.visualStatus}`}><strong>{slot.slot_name}</strong><span>{labels[slot.visualStatus]}</span>{canManageConfiguration && <button className="button quiet small" disabled={busy} onClick={() => open(slot)}>Sửa</button>}</div>)}</div></section>)}
    <details className="surface core-details"><summary>Danh sách vị trí & thao tác</summary><div className="table-wrap"><table className="data-table core-table"><thead><tr><th scope="col">Vị trí</th><th scope="col">Khu vực</th><th scope="col">Loại xe</th><th scope="col">Trạng thái</th>{canManageConfiguration && <th scope="col">Thao tác</th>}</tr></thead><tbody>{filtered.map(slot => <tr key={slot.id}><td><strong>{slot.slot_name}</strong></td><td>{slot.zone?.name || "—"}</td><td>{slot.vehicleType?.name || "—"}</td><td>{labels[slot.visualStatus]}</td>{canManageConfiguration && <td><div className="core-row-actions"><button className="button quiet small" disabled={busy} onClick={() => open(slot)}>Sửa</button><button className="button quiet small danger" disabled={busy} onClick={() => remove(slot)}>Xóa</button></div></td>}</tr>)}</tbody></table></div>{!filtered.length && <p className="empty">Không có vị trí phù hợp.</p>}</details>
  </>;
}
