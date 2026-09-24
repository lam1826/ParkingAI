import { useState } from "react";

const roleLabels = { admin: "Admin", manager: "Manager", staff: "Nhân viên", customer: "Customer" };
export default function UserTable({ users, loading, canManage, canDelete = false, canEditUser = () => false, onEdit, onDelete, busy = false }) {
  const [page, setPage] = useState(0);
  const currentPage = Math.min(page, Math.max(0, Math.ceil(users.length / 25) - 1));
  return <section className="surface" aria-labelledby="accounts-title">
    <div className="section-head"><h2 id="accounts-title">Danh sách tài khoản</h2><span className="muted">{users.length} tài khoản</span></div>
    {loading ? <p className="empty" role="status">Đang tải tài khoản…</p> : !users.length ? <div className="empty">Chưa có tài khoản được phép xem.</div> : <>
      <div className="table-wrap"><table className="data-table"><thead><tr><th scope="col">Tài khoản</th><th scope="col">Vai trò</th><th scope="col">Trạng thái</th>{canManage && <th scope="col">Thao tác</th>}</tr></thead><tbody>
        {users.slice(currentPage * 25, currentPage * 25 + 25).map(user => { const editable = canManage && canEditUser(user); const role = user.role?.name || ""; return <tr key={user.id}>
          <td>{editable ? <button className="button quiet small" style={{ paddingLeft: 0 }} disabled={busy} aria-label={`Sửa tài khoản ${user.username}`} onClick={() => onEdit(user)}>{user.full_name || user.username}</button> : <strong>{user.full_name || user.username}</strong>}<div className="muted">{user.username}</div></td>
          <td><span className="badge neutral">{roleLabels[role] || role || "—"}</span></td><td><span className={`badge ${user.is_active !== false ? "success" : "neutral"}`}>{user.is_active !== false ? "Đang hoạt động" : "Đã khóa"}</span></td>
          {canManage && <td><div className="core-row-actions">{editable && <button className="button quiet small" disabled={busy} onClick={() => onEdit(user)}>Sửa / {user.is_active !== false ? "khóa" : "mở khóa"}</button>}{canDelete && <button className="button quiet small danger" disabled={busy} aria-label={`Xóa tài khoản ${user.username}`} onClick={() => onDelete(user)}>Xóa</button>}</div></td>}
        </tr>; })}
      </tbody></table></div>
      {users.length > 25 && <div className="form-actions" style={{ justifyContent: "flex-end", marginTop: 18 }}><button className="button quiet small" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Trang trước</button><span className="muted">Trang {currentPage + 1} / {Math.ceil(users.length / 25)}</span><button className="button quiet small" disabled={(currentPage + 1) * 25 >= users.length} onClick={() => setPage(currentPage + 1)}>Trang sau</button></div>}
    </>}
  </section>;
}
