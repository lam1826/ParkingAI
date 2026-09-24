import { useState, useContext } from "react";
import { Link, useLocation } from "react-router-dom";
import { AuthContext } from "../../context/AuthContext";
import { PrototypeBrand } from "../../components/common/PrototypeUI";
import { nextFromSearch, withNext } from "../../utils/safeNext";
import "../../styles/prototype-reference.css";
import "../../styles/prototype-app.css";

export default function LoginPage() {
  const { login } = useContext(AuthContext);
  const location = useLocation();
  const next = nextFromSearch(location.search);
  const [formData, setFormData] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const handleChange = event => setFormData(old => ({ ...old, [event.target.name]: event.target.value }));
  async function handleSubmit(event) {
    event.preventDefault();
    if (loading) return;
    setError(""); setLoading(true);
    if (!formData.username || !formData.password) {
      setError("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu."); setLoading(false); return;
    }
    try {
      const result = await login(formData, next);
      if (!result.success) { setError(result.message); setLoading(false); }
    } catch { setError("Chưa kết nối được hệ thống. Vui lòng thử lại."); setLoading(false); }
  }
  return <div className="prototype-ui"><main className="login-shell">
    <div className="login-intro"><PrototypeBrand /><h1>Một bãi xe.<br />Mọi thao tác rõ ràng.</h1>
      <p>Theo dõi chỗ trống, tính phí và thanh toán trong một nơi. Đăng nhập để gửi xe hoặc quản lý bãi.</p>
      <p className="inline-note">Không cần đặt trước để gửi xe. Đặt chỗ giúp bạn giữ một vị trí trước giờ đến.</p>
    </div>
    <section className="surface login-form"><div className="section-head"><div><h2>Đăng nhập</h2><p>Chào mừng bạn quay lại ParkingAI.</p></div></div>
      {error && <p className="inline-note warning" role="alert">{error}</p>}
      {location.state?.message && <p className="inline-note success" role="status">{location.state.message}</p>}
      {next && <p className="inline-note">Đăng nhập để tiếp tục thao tác bạn đã chọn.</p>}
      <form onSubmit={handleSubmit}>
        <div className="field"><label htmlFor="username">Tên đăng nhập</label><input id="username" name="username" autoComplete="username" autoFocus required value={formData.username} onChange={handleChange} /></div>
        <div className="field"><label htmlFor="password">Mật khẩu</label><div className="app-password"><input id="password" name="password" type={visible ? "text" : "password"} autoComplete="current-password" required value={formData.password} onChange={handleChange} /><button type="button" onClick={() => setVisible(old => !old)} aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}>{visible ? "Ẩn" : "Hiện"}</button></div></div>
        <button className="button primary full" type="submit" disabled={loading}>{loading ? "Đang đăng nhập…" : "Đăng nhập"}</button>
      </form>
      <div className="login-links"><Link to={withNext("/register", next)}>Chưa có tài khoản? Đăng ký</Link><Link to="/gioi-thieu">Thông tin bãi xe</Link></div>
    </section>
  </main></div>;
}
