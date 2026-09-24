import { useState } from "react";

export default function VehicleTable({ vehicles, loading, onEdit, onDelete }) {
  const [search, setSearch] = useState(""), [page, setPage] = useState(0);
  const rows = vehicles.filter(row => `${row.license_plate} ${row.customer?.full_name || ""}`.toLocaleLowerCase("vi").includes(search.trim().toLocaleLowerCase("vi")));
  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / 25) - 1));
  return <section className="surface"><div className="toolbar"><input aria-label="Tìm phương tiện" placeholder="Tìm biển số hoặc khách hàng…" value={search} onChange={event => { setSearch(event.target.value); setPage(0); }} /><span className="muted">{rows.length} phương tiện</span></div>
    {loading ? <p className="empty" role="status">Đang tải phương tiện…</p> : !rows.length ? <div className="empty">Không có phương tiện phù hợp.</div> : <>
      <div className="table-wrap"><table className="data-table core-table"><thead><tr><th scope="col">Biển số / mã xe</th><th scope="col">Loại xe</th><th scope="col">Khách hàng</th><th scope="col">Thao tác</th></tr></thead><tbody>{rows.slice(currentPage * 25, currentPage * 25 + 25).map(row => <tr key={row.id}><td><strong className="plate">{row.license_plate}</strong></td><td>{row.vehicle_type?.name || (typeof row.vehicle_type === "string" ? row.vehicle_type : "—")}</td><td>{row.customer?.full_name || "Khách vãng lai"}</td><td><div className="core-row-actions"><button className="button quiet small" onClick={() => onEdit(row)}>Sửa</button>{onDelete && <button className="button quiet small danger" onClick={() => onDelete(row)}>Xóa</button>}</div></td></tr>)}</tbody></table></div>
      {rows.length > 25 && <div className="form-actions" style={{ justifyContent: "flex-end", marginTop: 18 }}><button className="button quiet small" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Trang trước</button><span className="muted">Trang {currentPage + 1}</span><button className="button quiet small" disabled={(currentPage + 1) * 25 >= rows.length} onClick={() => setPage(currentPage + 1)}>Trang sau</button></div>}
    </>}
  </section>;
}
