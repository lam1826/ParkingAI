import { canShowMenuItem } from "./menuPermissions.js";

export const customerNavigation = [
  { text: "Phí gửi xe", icon: "price", path: "/portal?tab=fees" },
  { text: "Đặt chỗ trước", icon: "parking", path: "/reservations" },
  { text: "Vé & lịch sử", icon: "pass", path: "/portal?tab=tickets" },
  { text: "Hỗ trợ", icon: "people", path: "/portal?tab=support" },
];

// Group destinations without changing the server's legacy/site permission boundary.
export function workspaceTabs(pathname, role, capabilities) {
  if (role === "customer") return [];
  const analytics = Boolean(capabilities?.site_analytics_enabled);
  const groups = [
    [
      { text: "Tài khoản", path: "/users", role: "manager" },
      { text: "Vai trò", path: "/roles", role: "manager" },
    ],
    [
      { text: "Vị trí đỗ", path: "/parking-slots", role: "staff" },
      { text: "Khu vực", path: "/zones", role: "staff" },
    ],
    [
      { text: "Khách hàng", path: "/customers", role: "staff" },
      { text: "Phương tiện", path: "/vehicles", role: "staff" },
      { text: "Vé tháng", path: "/monthly-passes", role: "staff" },
      { text: "Đơn vé & hỗ trợ", path: "/portal-admin", role: "manager", scoped: true },
    ],
    [
      { text: "Loại xe", path: "/vehicle-types", role: "staff" },
      { text: "Bảng giá", path: "/price-configs", role: "staff" },
    ],
    [
      { text: "Lưu lượng", path: "/reports", role: analytics ? "staff" : "manager", scoped: analytics },
      { text: "AI phân tích", path: "/ai", role: analytics ? "staff" : "manager", scoped: analytics },
      { text: "Thu chi & ca", path: "/finance", role: "staff", scoped: Boolean(capabilities?.site_finance_enabled) },
    ],
  ];
  return (groups.find((group) => group.some((item) => item.path === pathname)) || [])
    .filter((item) => canShowMenuItem(item, role, capabilities, false));
}

export function navigationSections(role, capabilities, singleSiteMode) {
  if (role === "customer") return [{ id: "customer", label: "Bãi xe của bạn", items: customerNavigation }];
  const analytics = Boolean(capabilities?.site_analytics_enabled);
  const sections = [
    { id: "operations", label: "Bãi xe", items: [
      { text: "Tổng quan", icon: "dashboard", path: "/", role: "staff", scoped: true },
      { text: "Vận hành", icon: "parking", path: "/sites", role: "staff", scoped: true },
      { text: "Bãi đỗ", icon: "zone", path: "/parking-slots", role: "staff", aliases: ["/zones"] },
      { text: "Lịch sử gửi xe", icon: "history", path: "/history", role: "staff", scoped: true, aliases: ["/sessions"] },
      { text: "Khách & vé", icon: "people", path: "/customers", role: "staff", aliases: ["/vehicles", "/monthly-passes", "/portal-admin"] },
      { text: "Thu chi & báo cáo", icon: "reports", path: "/reports", role: analytics ? "staff" : "manager", scoped: analytics, aliases: ["/ai", "/finance"] },
      { text: "Loại xe & bảng giá", icon: "type", path: "/vehicle-types", role: "staff", aliases: ["/price-configs"] },
    ] },
    { id: "management", label: "Quản trị", items: [
      { text: "Tài khoản nhân sự", icon: "people", path: "/users", role: "manager", aliases: ["/roles"] },
      { text: "Vai trò", icon: "roles", path: "/roles", role: "manager" },
      { text: "Cấu hình bãi", icon: "settings", path: "/site-settings", role: "admin", scoped: true },
      { text: "Nhật ký hoạt động", icon: "history", path: "/audit-logs", role: "manager" },
    ] },
    { id: "extensions", label: "Công cụ khác", collapsible: true, items: [
      { text: "Cấu hình camera", icon: "camera", path: "/vision", role: "staff", scoped: true },
      { text: "Quan sát chỗ đỗ", icon: "parking", path: "/occupancy", role: "staff", scoped: true },
      { text: "Dự báo & điều hành", icon: "reports", path: "/insights", role: "staff", scoped: true },
      ...(!capabilities?.legacy_workspace_allowed ? [{ text: "Đơn vé & hỗ trợ", icon: "pass", path: "/portal-admin", role: "manager", scoped: true }] : []),
    ] },
  ];
  return sections.map((section) => ({ ...section,
    items: section.items.filter((item) => canShowMenuItem(item, role, capabilities, singleSiteMode)),
  })).filter((section) => section.items.length);
}

export function navigationItemSelected(location, item) {
  if (item.path.startsWith("/portal?")) {
    if (location.pathname !== "/portal") return false;
    const params = new URLSearchParams(location.search);
    const tab = params.has("order") ? "tickets" : params.get("tab") || "fees";
    const actual = ["purchase", "vehicles", "profile", "notifications"].includes(tab) ? "tickets" : tab;
    return new URLSearchParams(item.path.split("?")[1]).get("tab") === actual;
  }
  return [item.path, ...(item.aliases || [])].some((path) => path === "/"
    ? location.pathname === "/" : location.pathname === path || location.pathname.startsWith(`${path}/`));
}
