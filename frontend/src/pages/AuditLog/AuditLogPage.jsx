import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "../../components/common/PrototypeUI";
import { getErrorMessage } from "../../utils/errorMessage";
import api from "../../services/api";
import formatMetadataTimestamp from "../../utils/formatMetadataTimestamp";
import { createLatestRequestGate } from "../../utils/latestRequestGate";
import { AUDIT_TEXT_FILTER_DELAY_MS, auditLogPageView, auditLogRequest, textFiltersPending } from "./auditLogQuery";

const actionLabels = {
  CREATE: "Tạo mới",
  UPDATE: "Cập nhật",
  DELETE: "Xóa",
  CHECK_IN: "Xe vào",
  CHECK_OUT: "Xe ra",
  AI_ACTION: "Tác vụ AI",
  SHIFT_OPEN: "Mở ca", SHIFT_CLOSE: "Chốt ca", PAYMENT_COLLECT: "Thu tiền",
  PAYMENT_DEMO: "Thanh toán mô phỏng", REFUND: "Hoàn tiền",
  VISION_CAPTURE: "Nhận ảnh", VISION_REVIEW: "Duyệt biển số", VISION_DELETE: "Xóa ảnh", RESERVATION_ACTION: "Đặt chỗ / chờ",
  SESSION_CANCEL: "Hủy lượt gửi", TICKET_LOST: "Xác nhận mất vé", PLATE_CORRECTION: "Sửa biển số",
};

const EMPTY_TEXT = { username: "", requestId: "" };

export default function AuditLogPage() {
  const requestGate = useRef(null);
  if (requestGate.current === null) {
    requestGate.current = createLatestRequestGate();
  }
  const [rows, setRows] = useState([]);
  const [hasNext, setHasNext] = useState(false);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [success, setSuccess] = useState("");
  // What is typed vs. what is queried: text filters apply after a pause or on submit.
  const [typed, setTyped] = useState(EMPTY_TEXT);
  const [applied, setApplied] = useState(EMPTY_TEXT);
  const [reloadToken, setReloadToken] = useState(0);

  // One server page per view; a newer view aborts the request of the older one.
  const load = useCallback(async (signal) => {
    const generation = requestGate.current.begin();
    const request = auditLogRequest({ action, success, ...applied }, page);
    setError("");
    if (request.error) {
      setRows([]);
      setHasNext(false);
      setError(request.error);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const response = await api.get("/api/v1/audit-logs", { params: request.params, signal });
      if (!requestGate.current.isCurrent(generation)) return;
      const view = auditLogPageView(response.data);
      setRows(view.rows);
      setHasNext(view.hasNext);
    } catch (requestError) {
      if (requestGate.current.isCurrent(generation)) {
        setError(getErrorMessage(requestError, "Không thể tải nhật ký hoạt động."));
      }
    } finally {
      if (requestGate.current.isCurrent(generation)) setLoading(false);
    }
  }, [action, success, applied, page]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => {
      requestGate.current.invalidate();
      controller.abort();
    };
  }, [load, reloadToken]);

  useEffect(() => {
    if (!textFiltersPending(typed, applied)) return undefined;
    const timer = setTimeout(() => { setApplied(typed); setPage(0); }, AUDIT_TEXT_FILTER_DELAY_MS);
    return () => clearTimeout(timer);
  }, [typed, applied]);

  const changeFilter = setter => event => { setter(event.target.value); setPage(0); };
  const changeText = name => event => { const value = event.target.value; setTyped(old => ({ ...old, [name]: value })); };
  const submit = event => { event.preventDefault(); setApplied(typed); setPage(0); setReloadToken(old => old + 1); };
  const clearFilters = () => { setAction(""); setSuccess(""); setTyped(EMPTY_TEXT); setApplied(EMPTY_TEXT); setPage(0); };
  const detailFields = [["id", "ID"], ["resource_id", "Mã đối tượng"], ["path", "API"], ["request_id", "Mã truy vết"], ["site_id", "Bãi"], ["duration_ms", "Thời gian xử lý (ms)"], ["status_code", "Mã HTTP"]];
  return <>
    <PageHeader title="Nhật ký hoạt động" description="Theo dõi thao tác thay đổi dữ liệu của nhân viên, quản lý và quản trị viên." />
    <section className="surface"><div className="section-head"><h2>Lọc hoạt động</h2></div>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">Hành động<select value={action} onChange={changeFilter(setAction)}><option value="">Tất cả</option>{Object.entries(actionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="field">Tên tài khoản<input value={typed.username} onChange={changeText("username")} placeholder="Tìm theo tài khoản…" maxLength={50} /></label>
        <label className="field">Mã truy vết<input value={typed.requestId} onChange={changeText("requestId")} placeholder="Mã trong thông báo lỗi…" maxLength={64} autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
        <label className="field">Kết quả<select value={success} onChange={changeFilter(setSuccess)}><option value="">Tất cả</option><option value="true">Thành công</option><option value="false">Thất bại</option></select></label>
        <div className="form-actions core-wide"><button className="button secondary" disabled={loading}>Làm mới</button><button type="button" className="button quiet" onClick={clearFilters}>Xóa bộ lọc</button></div>
      </form>
    </section>
    <section className="surface" aria-labelledby="audit-title"><div className="section-head"><h2 id="audit-title">Hoạt động gần đây</h2><span className="muted">Trang {page + 1} · {rows.length} bản ghi</span></div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {loading ? <p className="empty" role="status">Đang tải nhật ký hoạt động…</p> : !rows.length ? <div className="empty">{page ? "Không còn hoạt động ở trang này." : "Chưa có hoạt động phù hợp với bộ lọc."}</div> : <>
        <div className="table-wrap"><table className="data-table"><thead><tr><th scope="col">Thời gian</th><th scope="col">Hành động</th><th scope="col">Đối tượng</th><th scope="col">Tài khoản</th><th scope="col">Kết quả</th><th scope="col">Chi tiết</th></tr></thead><tbody>
          {rows.map(row => <tr key={row.id}>
            <td className="tabular">{formatMetadataTimestamp(row.created_at)}</td><td>{actionLabels[row.action] || row.action}</td><td>{row.resource || "—"}{row.resource_id != null && <div className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.resource_id}</div>}</td><td>{row.username || "—"}</td><td><span className={`badge ${row.success ? "success" : "warning"}`}>{row.success ? "Thành công" : "Thất bại"}</span></td>
            <td><details style={{ textAlign: "left", minWidth: 90 }}><summary style={{ cursor: "pointer", color: "var(--blue)" }}>Chi tiết</summary><dl className="definition-list" style={{ gridTemplateColumns: "1fr", gap: 12, marginTop: 16, maxWidth: 320 }}>{detailFields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd style={{ overflowWrap: "anywhere", whiteSpace: "pre-wrap", fontSize: 12 }}>{row[key] ?? "—"}</dd></div>)}</dl></details></td>
          </tr>)}
        </tbody></table></div>
      </>}
      {!loading && (page > 0 || hasNext) && <div className="form-actions" style={{ justifyContent: "flex-end", marginTop: 18 }}><button type="button" className="button quiet small" disabled={!page} onClick={() => setPage(page - 1)}>Trang trước</button><span className="muted">Trang {page + 1}</span><button type="button" className="button quiet small" disabled={!hasNext} onClick={() => setPage(page + 1)}>Trang sau</button></div>}
    </section>
  </>;
}
