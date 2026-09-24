import { useState, useContext } from "react";
import { Link, Outlet, useNavigate, useLocation } from "react-router-dom";
import { Menu, MenuItem, Divider } from "@mui/material";
import { AuthContext } from "../context/AuthContext";
import AIChatbot from "../components/ai/AIChatbot";
import ErrorBoundary from "../components/common/ErrorBoundary";
import { PrototypeBrand, PrototypeIcon } from "../components/common/PrototypeUI";
import { useExpansion } from "../context/ExpansionContext";
import { singleSiteId } from "../utils/singleSiteMode";
import { navigationItemSelected, navigationSections } from "../utils/navigationItems";
import "../styles/prototype-reference.css";
import "../styles/prototype-app.css";

const iconNames = { dashboard: "chart", parking: "car", vehicle: "car", pass: "ticket", people: "users", zone: "parking", type: "parking", price: "wallet", reports: "wallet", roles: "shield", history: "history", camera: "camera", settings: "settings" };
const roles = { admin: "Admin", manager: "Manager", staff: "Nhân viên", customer: "Customer" };

export default function MainLayout() {
  const { user, logout } = useContext(AuthContext);
  const capabilities = useExpansion();
  const navigate = useNavigate(), location = useLocation();
  const [accountAnchor, setAccountAnchor] = useState(null);
  const customer = user?.role === "customer";
  const showcase = capabilities?.showcase_mode || globalThis.__PARKINGAI_CONFIG__?.DEMO;
  const sections = navigationSections(user?.role, capabilities, singleSiteId() !== null);
  const primary = sections.find(section => section.id === (customer ? "customer" : "operations"))?.items || [];
  const management = sections.find(section => section.id === "management")?.items || [];
  const extensions = sections.find(section => section.id === "extensions")?.items || [];
  const name = user?.full_name || user?.username || roles[user?.role];
  const go = path => { setAccountAnchor(null); navigate(path); };
  const nav = item => <Link key={item.path} className={`nav-item ${navigationItemSelected(location, item) ? "active" : ""}`} to={item.path} aria-current={navigationItemSelected(location, item) ? "page" : undefined}>
    <PrototypeIcon name={item.path === "/reservations" ? "calendar" : item.path.includes("support") ? "help" : iconNames[item.icon]} />{item.path === "/users" ? "Tài khoản & quyền" : item.text}
  </Link>;

  return <div className="prototype-ui">
    <a className="app-skip" href="#main-content">Chuyển đến nội dung chính</a>
    <header className="topbar">
      <Link to={customer ? "/portal" : "/"} className="brand-link"><PrototypeBrand /></Link>
      <div className="role-switch account-roles" role="group" aria-label="Vai trò tài khoản đang đăng nhập">
        {(user?.role === "staff" ? ["staff"] : ["customer", "manager", "admin"]).map(role => <span key={role} className={`role-display ${role === user?.role ? "active" : ""}`} aria-current={role === user?.role ? "true" : undefined}><PrototypeIcon name={{ customer: "user", manager: "car", admin: "shield", staff: "car" }[role]} />{roles[role]}</span>)}
      </div>
      <div className="top-actions">
        <button type="button" className="icon-button" onClick={event => setAccountAnchor(event.currentTarget)} aria-label="Tài khoản của tôi"><PrototypeIcon name="user" /></button>
        <button type="button" className="icon-button" onClick={logout} aria-label="Đăng xuất"><PrototypeIcon name="logout" /></button>
      </div>
    </header>
    <div className="demo-banner">{showcase ? "Bản chạy thử · Dữ liệu mẫu · Thanh toán mô phỏng" : "ParkingAI · Quản lý bãi đỗ và thanh toán"}</div>
    {customer && <nav className="customer-nav" aria-label="Điều hướng khách hàng">{primary.map(nav)}</nav>}
    <div className={`app-shell ${customer ? "customer" : "internal"}`}>
      {!customer && <aside className="sidebar" aria-label="Điều hướng nội bộ">
        <div className="nav-label">{user?.role === "admin" ? "ĐIỀU HÀNH BÃI" : "BÃI TRUNG TÂM"}</div>
        {primary.map(nav)}
        {user?.role === "admin" && <><div className="nav-label admin-section-label">QUẢN TRỊ</div>{management.filter(item => item.path !== "/roles").map(nav)}</>}
        <div className="sidebar-bottom">
          <span className="badge neutral">{showcase ? "Dữ liệu thử nghiệm" : "Tài khoản đã xác thực"}</span>
          <div className="profile-row"><div className="account-avatar">{name?.slice(0, 1)}</div><div>{name}<br /><span>{roles[user?.role]}</span></div></div>
        </div>
      </aside>}
      <main className={`main ${customer ? "customer-main" : ""}`} id="main-content" tabIndex={-1}>
        <ErrorBoundary key={location.pathname}><Outlet /></ErrorBoundary>
        <details className="app-help"><summary>Cách sử dụng & chức năng khác</summary><div className="app-help-body">
          <p>Bạn có thể gửi xe trực tiếp; đặt trước chỉ để giữ chỗ. Số tiền được tính theo lượt gửi và bảng giá trên hệ thống.{showcase && " Thanh toán mô phỏng không chuyển tiền thật."}</p>
          <div className="overview-links"><Link className="button quiet small" to="/gioi-thieu">Thông tin bãi xe</Link><Link className="button quiet small" to="/profile">Hồ sơ cá nhân</Link>
            {[...(user?.role === "admin" ? management.filter(item => item.path === "/roles") : management), ...extensions].map(item => <Link key={item.path} className="button quiet small" to={item.path}>{item.text}</Link>)}
          </div>
        </div></details>
        <p className="footer-note">ParkingAI · Quản lý một bãi đỗ<br />{showcase ? "Dữ liệu mẫu riêng để kiểm tra giao diện và nghiệp vụ." : "Thông tin cập nhật từ hệ thống quản lý bãi."}</p>
      </main>
    </div>
    <Menu anchorEl={accountAnchor} open={Boolean(accountAnchor)} onClose={() => setAccountAnchor(null)}>
      <MenuItem disabled>{roles[user?.role]} · {user?.username}</MenuItem>
      <MenuItem onClick={() => go("/profile")}>Hồ sơ cá nhân</MenuItem>
      <MenuItem onClick={() => go("/account")}>Tài khoản của tôi</MenuItem>
      <MenuItem onClick={() => go("/settings")}>Cài đặt tài khoản</MenuItem>
      <Divider />
      {management.map(item => <MenuItem key={item.path} onClick={() => go(item.path)}>{item.text}</MenuItem>)}
      <MenuItem onClick={() => { setAccountAnchor(null); logout(); }}>Đăng xuất</MenuItem>
    </Menu>
    <AIChatbot />
  </div>;
}
