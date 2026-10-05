import { useContext, useState } from "react";
import CrudPage from "../../components/common/CrudPage";
import { AuthContext } from "../../context/AuthContext";
import { getErrorMessage } from "../../utils/errorMessage";
import useRole from "./hooks/useRole";
import { missingCanonicalRoles } from "./roleRestore";
import { roleService } from "./services/roleService";

// Canonical roles are fixed; an Admin can only restore one that is missing
// (e.g. a fresh install without "staff"), never invent or rename roles.
function CanonicalRoleRestore({ onRestored }) {
  const { roles, loading, error, fetchRoles } = useRole();
  const [state, setState] = useState({ busy: false, message: "", error: "" });
  const missing = loading || error ? [] : missingCanonicalRoles(roles);
  if (!missing.length && !state.message && !state.error) return null;
  async function restore(role) {
    setState({ busy: true, message: "", error: "" });
    try {
      await roleService.create(role);
      setState({ busy: false, message: `Đã khôi phục vai trò ${role.name}.`, error: "" });
      await fetchRoles();
      onRestored();
    } catch (failure) {
      setState({ busy: false, message: "", error: getErrorMessage(failure, "Không khôi phục được vai trò.") });
    }
  }
  return <section className="surface" aria-labelledby="role-restore-title">
    <div className="section-head"><h2 id="role-restore-title">Khôi phục vai trò chuẩn</h2></div>
    {state.message && <p className="inline-note success" role="status">{state.message}</p>}
    {state.error && <p className="form-error" role="alert">{state.error}</p>}
    {missing.length > 0 && <>
      <p className="muted">Hệ thống đang thiếu vai trò chuẩn nên trang Tài khoản không tạo được loại tài khoản này.</p>
      <div className="form-actions">{missing.map(role => <button key={role.name} type="button" className="button secondary" disabled={state.busy} onClick={() => void restore(role)}>Khôi phục vai trò {role.name}</button>)}</div>
    </>}
  </section>;
}

export default function RolePage() {
  const { user } = useContext(AuthContext);
  const [version, setVersion] = useState(0);
  return <>
    <CrudPage key={version} title="Vai trò hệ thống" service={roleService} canEdit={false} fields={[
      { name: "name", label: "Tên vai trò", required: true },
      { name: "description", label: "Mô tả quyền hạn" },
    ]} />
    {user?.role === "admin" && <CanonicalRoleRestore onRestored={() => setVersion(old => old + 1)} />}
  </>;
}
