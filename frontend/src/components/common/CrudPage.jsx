import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Snackbar } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { PageHeader, WorkspaceTabs } from "./PrototypeUI";

export function extractErrorMessage(error, fallback = "Đã xảy ra lỗi.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map(item => {
      if (typeof item === "string") return item;
      const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : null;
      return field && item?.msg ? `${field}: ${item.msg}` : item?.msg;
    }).filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

export function CrudFields({ fields, form, onChange, disabled = false }) {
  const firstTextFieldName = fields.find(field => field.type !== "boolean")?.name;
  return fields.map(field => field.type === "boolean"
    ? <label key={field.name} className="checkbox-field"><input type="checkbox" name={field.name} checked={Boolean(form[field.name])} disabled={disabled} onChange={event => onChange(field.name, event.target.checked)} /><span>{field.label}</span></label>
    : <label key={field.name} className="field">{field.label}{field.required ? " *" : ""}
      {field.type === "select"
        ? <select name={field.name} required={field.required} value={form[field.name] ?? ""} disabled={disabled} autoFocus={field.name === firstTextFieldName} onChange={event => onChange(field.name, event.target.value)}><option value="">Chọn {field.label.toLowerCase()}</option>{(field.options || []).map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
        : <input name={field.name} type={field.type || "text"} required={field.required} value={form[field.name] ?? ""} disabled={disabled} autoFocus={field.name === firstTextFieldName} onChange={event => onChange(field.name, event.target.value)} />}
    </label>);
}

const catalogue = {
  "Quản lý khu vực bãi xe": ["Bãi đỗ", "Quản lý khu vực, chỗ đỗ và khả năng nhận xe tại một bãi.", "khu vực", "Các khu vực"],
  "Quản lý loại phương tiện": ["Loại xe & bảng giá", "Danh mục phương tiện, mã xe và đơn giá cho lượt gửi mới.", "loại xe", "Các loại xe"],
  "Cấu hình bảng giá": ["Loại xe & bảng giá", "Danh mục phương tiện, mã xe và đơn giá cho lượt gửi mới.", "bảng giá", "Bảng giá gửi xe"],
  "Quản lý khách hàng thân thiết": ["Khách & vé", "Hồ sơ khách, phương tiện liên kết và các kỳ vé tháng.", "khách hàng", "Khách hàng"],
};

export default function CrudPage({ title, fields, service, canEdit = true, canDelete = canEdit, readOnlyMessage, descriptionNote, embedded = false }) {
  const [rows, setRows] = useState([]), [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false), [editing, setEditing] = useState(null), [form, setForm] = useState({});
  const [busy, setBusy] = useState(false), [formError, setFormError] = useState("");
  const [search, setSearch] = useState(""), [page, setPage] = useState(0), [sort, setSort] = useState(null);
  const [notice, setNotice] = useState({ open: false, severity: "success", message: "" });
  const working = useRef(false), editor = useRef(null);
  const [heading, description, entity, section] = catalogue[title] || [title, "Tra cứu và cập nhật thông tin của bãi.", "bản ghi", title];
  const visible = fields.filter(field => !field.hideInTable);
  const valueFor = (row, field) => field.formatter ? field.formatter(row[field.name], row) : field.options?.find(option => String(option.value) === String(row[field.name]))?.label ?? (typeof row[field.name] === "boolean" ? row[field.name] ? "Đang hoạt động" : "Ngừng hoạt động" : row[field.name] ?? "—");
  const notify = (message, severity = "success") => setNotice({ open: true, message, severity });
  const load = useCallback(async () => {
    setLoading(true);
    try { const data = await service.getAll(); setRows(Array.isArray(data) ? data : data.items || data.data || []); }
    catch (error) { notify(extractErrorMessage(error, "Không thể tải dữ liệu."), "error"); }
    finally { setLoading(false); }
  }, [service]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (open) editor.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [open, editing]);
  const start = row => {
    if (!canEdit || busy) return;
    setEditing(row); setFormError("");
    setForm(Object.fromEntries(fields.map(field => [field.name, row?.[field.name] ?? field.defaultValue ?? (field.type === "boolean" ? true : "")])));
    setOpen(true);
  };
  const save = async event => {
    event.preventDefault();
    if (!canEdit || working.current) return;
    const missing = fields.filter(field => field.required && field.type !== "boolean" && (form[field.name] === "" || form[field.name] == null));
    if (missing.length) { setFormError(`Vui lòng nhập: ${missing.map(field => field.label).join(", ")}.`); return; }
    working.current = true; setBusy(true); setFormError("");
    try {
      const payload = Object.fromEntries(fields.map(field => {
        let value = form[field.name];
        if (value === "" && !field.required) value = null;
        else if (field.type === "number" || field.valueType === "number" || field.name.endsWith("_id")) value = Number(value);
        return [field.name, value];
      }));
      if (editing) await service.update(editing.id, payload); else await service.create(payload);
      setOpen(false); notify(editing ? "Cập nhật thành công." : "Thêm mới thành công."); await load();
    } catch (error) { setFormError(extractErrorMessage(error, "Không thể lưu dữ liệu.")); }
    finally { working.current = false; setBusy(false); }
  };
  const remove = async row => {
    if (!canDelete || working.current || !window.confirm(`Xóa bản ghi #${row.id}?`)) return;
    working.current = true; setBusy(true);
    try { await service.delete(row.id); notify("Xóa thành công."); await load(); }
    catch (error) { notify(extractErrorMessage(error, "Không thể xóa dữ liệu đang được sử dụng. Có thể ngừng hoạt động để giữ lịch sử."), "error"); }
    finally { working.current = false; setBusy(false); }
  };
  const filtered = rows.filter(row => visible.some(field => String(valueFor(row, field)).toLocaleLowerCase("vi-VN").includes(search.trim().toLocaleLowerCase("vi-VN"))));
  if (sort) filtered.sort((a, b) => String(valueFor(a, sort.field)).localeCompare(String(valueFor(b, sort.field)), "vi", { numeric: true }) * sort.direction);
  const currentPage = Math.min(page, Math.max(0, Math.ceil(filtered.length / 25) - 1));
  const add = canEdit && <button className="button primary" onClick={() => start(null)} disabled={busy}><AddIcon fontSize="small" /> Thêm {entity}</button>;
  return <>
    {!embedded && <><PageHeader title={heading} description={description} actions={add} /><WorkspaceTabs /></>}
    {descriptionNote && <p className="inline-note">{descriptionNote}</p>}
    {!canEdit && readOnlyMessage && <p className="inline-note">{readOnlyMessage}</p>}
    {open && canEdit && <section ref={editor} className="surface core-editor" aria-labelledby="catalog-editor-title">
      <div className="section-head"><h2 id="catalog-editor-title">{editing ? "Sửa" : "Thêm"} {entity}</h2></div>
      <form className="form-grid" onSubmit={save}>
        <CrudFields fields={fields} form={form} disabled={busy} onChange={(name, value) => setForm(old => ({ ...old, [name]: value }))} />
        {formError && <p className="form-error core-wide" role="alert">{formError}</p>}
        <div className="form-actions core-wide"><button type="submit" className="button primary" disabled={busy}>{busy ? "Đang lưu…" : "Lưu thay đổi"}</button><button type="button" className="button secondary" disabled={busy} onClick={() => setOpen(false)}>Hủy</button></div>
      </form>
    </section>}
    <section className="surface">
      <div className="section-head"><h2>{section}</h2><div className="form-actions"><button className="button quiet small" disabled={loading || busy} onClick={load}>Làm mới</button>{embedded && add}</div></div>
      <div className="toolbar"><input aria-label={`Tìm ${entity}`} placeholder={`Tìm ${entity}…`} value={search} onChange={event => { setSearch(event.target.value); setPage(0); }} /><span className="muted">{filtered.length} bản ghi</span></div>
      {loading ? <p className="empty" role="status">Đang tải dữ liệu…</p> : !filtered.length ? <div className="empty">{search ? "Không có dữ liệu phù hợp với tìm kiếm." : "Chưa có dữ liệu."}</div> : <>
        <div className="table-wrap"><table className="data-table core-table"><thead><tr>{visible.map(field => <th key={field.name} scope="col" aria-sort={sort?.field.name === field.name ? sort.direction === 1 ? "ascending" : "descending" : "none"}><button type="button" onClick={() => setSort({ field, direction: sort?.field.name === field.name ? -sort.direction : 1 })} style={{ border: 0, background: "transparent", padding: 0, color: "inherit", font: "inherit", textAlign: "left", cursor: "pointer" }}>{field.label}{sort?.field.name === field.name ? sort.direction === 1 ? " ↑" : " ↓" : ""}</button></th>)}{(canEdit || canDelete) && <th scope="col">Thao tác</th>}</tr></thead>
          <tbody>{filtered.slice(currentPage * 25, currentPage * 25 + 25).map(row => <tr key={row.id}>{visible.map((field, index) => <td key={field.name}>{field.type === "boolean" ? <span className={`badge ${row[field.name] ? "success" : "neutral"}`}>{valueFor(row, field)}</span> : index === 0 ? <strong>{valueFor(row, field)}</strong> : valueFor(row, field)}</td>)}{(canEdit || canDelete) && <td><div className="core-row-actions">{canEdit && <button className="button quiet small" disabled={busy} onClick={() => start(row)}>Sửa</button>}{canDelete && <button className="button quiet small danger" disabled={busy} onClick={() => remove(row)}>Xóa</button>}</div></td>}</tr>)}</tbody>
        </table></div>
        {filtered.length > 25 && <div className="form-actions" style={{ justifyContent: "flex-end", marginTop: 18 }}><button className="button quiet small" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Trang trước</button><span className="muted">Trang {currentPage + 1} / {Math.ceil(filtered.length / 25)}</span><button className="button quiet small" disabled={(currentPage + 1) * 25 >= filtered.length} onClick={() => setPage(currentPage + 1)}>Trang sau</button></div>}
      </>}
    </section>
    <Snackbar open={notice.open} autoHideDuration={5000} onClose={() => setNotice(old => ({ ...old, open: false }))}><Alert severity={notice.severity}>{notice.message}</Alert></Snackbar>
  </>;
}
