import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "../../components/common/PrototypeUI";
import { getErrorMessage } from "../../utils/errorMessage";
import api from "../../services/api";
import { requestAllOffsetPages } from "../../services/paginatedLookup";
import formatMetadataTimestamp from "../../utils/formatMetadataTimestamp";
import { createLatestRequestGate } from "../../utils/latestRequestGate";

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

export default function AuditLogPage() {
  const requestGate = useRef(null);
  if (requestGate.current === null) {
    requestGate.current = createLatestRequestGate();
  }
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [username, setUsername] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    const generation = requestGate.current.begin();
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (action) params.action = action;
      if (username.trim()) params.username = username.trim();
      if (success !== "") params.success = success;
      const data = await requestAllOffsetPages(
        api,
        "/api/v1/audit-logs",
        100,
        params,
      );
      if (requestGate.current.isCurrent(generation)) setRows(data);
    } catch (requestError) {
      if (requestGate.current.isCurrent(generation)) {
        setError(getErrorMessage(requestError, "Không thể tải nhật ký hoạt động."));
      }
    } finally {
      if (requestGate.current.isCurrent(generation)) setLoading(false);
    }
  }, [action, success, username]);

  useEffect(() => {
    load();
    return () => requestGate.current.invalidate();
  }, [load]);

  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / 25) - 1));
  const changeFilter = setter => event => { setter(event.target.value); setPage(0); };
  const detailFields = [["id", "ID"], ["resource_id", "Mã đối tượng"], ["path", "API"], ["request_id", "Mã truy vết"], ["site_id", "Bãi"], ["duration_ms", "Thời gian xử lý (ms)"], ["status_code", "Mã HTTP"]];
  return <>
    <PageHeader title="Nhật ký hoạt động" description="Theo dõi thao tác thay đổi dữ liệu của nhân viên, quản lý và quản trị viên." />
    <section className="surface"><div className="section-head"><h2>Lọc hoạt động</h2></div>
      <form className="form-grid" onSubmit={event => { event.preventDefault(); void load(); }}>
        <label className="field">Hành động<select value={action} onChange={changeFilter(setAction)}><option value="">Tất cả</option>{Object.entries(actionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="field">Tên tài khoản<input value={username} onChange={changeFilter(setUsername)} placeholder="Tìm theo tài khoản…" /></label>
        <label className="field">Kết quả<select value={success} onChange={changeFilter(setSuccess)}><option value="">Tất cả</option><option value="true">Thành công</option><option value="false">Thất bại</option></select></label>
        <div className="form-actions core-wide"><button className="button secondary" disabled={loading}>Làm mới</button><button type="button" className="button quiet" onClick={() => { setAction(""); setUsername(""); setSuccess(""); setPage(0); }}>Xóa bộ lọc</button></div>
      </form>
    </section>
    <section className="surface" aria-labelledby="audit-title"><div className="section-head"><h2 id="audit-title">Hoạt động gần đây</h2><span className="muted">{rows.length} bản ghi</span></div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {loading ? <p className="empty" role="status">Đang tải nhật ký hoạt động…</p> : !rows.length ? <div className="empty">Chưa có hoạt động phù hợp với bộ lọc.</div> : <>
        <div className="table-wrap"><table className="data-table"><thead><tr><th scope="col">Thời gian</th><th scope="col">Hành động</th><th scope="col">Đối tượng</th><th scope="col">Tài khoản</th><th scope="col">Kết quả</th><th scope="col">Chi tiết</th></tr></thead><tbody>
          {rows.slice(currentPage * 25, currentPage * 25 + 25).map(row => <tr key={row.id}>
            <td className="tabular">{formatMetadataTimestamp(row.created_at)}</td><td>{actionLabels[row.action] || row.action}</td><td>{row.resource || "—"}{row.resource_id != null && <div className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.resource_id}</div>}</td><td>{row.username || "—"}</td><td><span className={`badge ${row.success ? "success" : "warning"}`}>{row.success ? "Thành công" : "Thất bại"}</span></td>
            <td><details style={{ textAlign: "left", minWidth: 90 }}><summary style={{ cursor: "pointer", color: "var(--blue)" }}>Chi tiết</summary><dl className="definition-list" style={{ gridTemplateColumns: "1fr", gap: 12, marginTop: 16, maxWidth: 320 }}>{detailFields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd style={{ overflowWrap: "anywhere", whiteSpace: "pre-wrap", fontSize: 12 }}>{row[key] ?? "—"}</dd></div>)}</dl></details></td>
          </tr>)}
        </tbody></table></div>
        {rows.length > 25 && <div className="form-actions" style={{ justifyContent: "flex-end", marginTop: 18 }}><button className="button quiet small" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Trang trước</button><span className="muted">Trang {currentPage + 1} / {Math.ceil(rows.length / 25)}</span><button className="button quiet small" disabled={(currentPage + 1) * 25 >= rows.length} onClick={() => setPage(currentPage + 1)}>Trang sau</button></div>}
      </>}
    </section>
  </>;
}
