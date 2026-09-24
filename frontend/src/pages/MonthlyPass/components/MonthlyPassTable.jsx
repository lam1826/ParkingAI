import { useState } from "react";
import formatDate from "../../../utils/formatDate";
import { getMonthlyPassStatus } from "../../../utils/monthlyPassStatus";

export default function MonthlyPassTable({ passes, loading, canManage = false, onEdit, onDeactivate }) {
  const [page, setPage] = useState(0);
  const currentPage = Math.min(page, Math.max(0, Math.ceil(passes.length / 25) - 1));
  return <section className="surface">
    {loading ? <p className="empty" role="status">Đang tải vé tháng…</p> : !passes.length ? <div className="empty">Chưa có kỳ vé tháng.</div> : <>
      <div className="table-wrap"><table className="data-table core-table"><thead><tr><th scope="col">Vé / xe</th><th scope="col">Khách hàng</th><th scope="col">Thời hạn</th><th scope="col">Giá kỳ vé</th><th scope="col">Trạng thái</th>{canManage && <th scope="col">Thao tác</th>}</tr></thead>
        <tbody>{passes.slice(currentPage * 25, currentPage * 25 + 25).map(pass => { const status = getMonthlyPassStatus(pass); return <tr key={pass.id}>
          <td><strong className="plate">{pass.vehicle?.license_plate || "—"}</strong><div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{pass.card_code || pass.pass_code || "—"}{pass.vehicle?.vehicle_type?.name ? ` · ${pass.vehicle.vehicle_type.name}` : ""}</div></td>
          <td>{pass.customer?.full_name || "—"}</td><td>{formatDate(pass.start_date)}<br />đến hết {formatDate(pass.end_date)}</td><td>{Number(pass.price || 0).toLocaleString("vi-VN")} đ</td>
          <td><span className={`badge ${status.color === "success" ? "success" : status.color === "warning" ? "warning" : "neutral"}`}>{status.label}</span></td>
          {canManage && <td><div className="core-row-actions"><button className="button quiet small" onClick={() => onEdit(pass)}>Gia hạn</button><button className="button quiet small danger" disabled={!pass.is_active} onClick={() => onDeactivate(pass)}>Ngừng vé</button></div></td>}
        </tr>; })}</tbody></table></div>
      {passes.length > 25 && <div className="form-actions" style={{ justifyContent: "flex-end", marginTop: 18 }}><button className="button quiet small" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Trang trước</button><span className="muted">Trang {currentPage + 1}</span><button className="button quiet small" disabled={(currentPage + 1) * 25 >= passes.length} onClick={() => setPage(currentPage + 1)}>Trang sau</button></div>}
    </>}
    <p className="inline-note">Vé có hiệu lực đến hết ngày kết thúc theo giờ Việt Nam. Gia hạn tạo kỳ mới; ngừng vé vẫn giữ các kỳ đã sử dụng và chứng từ.</p>
  </section>;
}
