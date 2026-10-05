// Pure helpers for onboarding operator accounts to a parking lot. Grants are
// made by account (name/username), never by asking for a hidden numeric ID.

const SITE_ROLES = new Set(["staff", "manager"]);

export const roleName = (user) => String(user?.role?.name ?? user?.role ?? "").toLowerCase();

/** The lot permission a new account of this role receives, or null. */
export function siteAssignmentRole(name) {
  const normalized = String(name ?? "").toLowerCase();
  return SITE_ROLES.has(normalized) ? normalized : null;
}

/** Preselect a lone role (e.g. a Manager may only create staff), never "admin". */
export function autoSelectedRoleId(roles) {
  const list = Array.isArray(roles) ? roles : [];
  return list.length === 1 && String(list[0]?.name ?? "").toLowerCase() !== "admin" ? list[0].id : "";
}

/** Preselect the only lot, or the configured single-site lot when it is listed. */
export function defaultAssignmentSiteId(sites, preferredId = null) {
  const list = Array.isArray(sites) ? sites : [];
  if (list.length === 1) return String(list[0].id);
  const preferred = list.find((site) => String(site.id) === String(preferredId ?? ""));
  return preferred ? String(preferred.id) : "";
}

/** Body for POST /api/v1/users: site_id only for staff/manager with a chosen lot. */
export function createAccountBody(form, roles) {
  const body = { ...form, role_id: Number(form.role_id) };
  const role = (roles || []).find((item) => item.id === body.role_id);
  delete body.site_id;
  if (siteAssignmentRole(role?.name) && form.site_id) body.site_id = Number(form.site_id);
  return body;
}

export function accountLabel(user) {
  const name = user?.full_name || user?.username || "Tài khoản";
  return user?.username && user.username !== name ? `${name} (${user.username})` : name;
}

/** Active staff/manager accounts that can be granted a lot permission. */
export function eligibleSiteMembers(users) {
  return (Array.isArray(users) ? users : [])
    .filter((user) => user?.is_active !== false && SITE_ROLES.has(roleName(user)))
    .map((user) => ({ id: user.id, role: roleName(user), label: `${accountLabel(user)} · ${roleName(user) === "manager" ? "Quản lý" : "Nhân viên"}` }))
    .sort((a, b) => a.label.localeCompare(b.label, "vi"));
}

/** Name shown for a membership row; falls back to the account code. */
export function memberDisplayName(userId, users) {
  const user = (Array.isArray(users) ? users : []).find((item) => item.id === userId);
  return user ? accountLabel(user) : `Tài khoản #${userId}`;
}

/** Lot the backend assigns: the chosen one, else the only active lot listed. */
export function expectedAssignmentSite(body, roles, sites) {
  const role = (roles || []).find((item) => item.id === Number(body?.role_id));
  if (!siteAssignmentRole(role?.name)) return null;
  const list = Array.isArray(sites) ? sites : [];
  if (body?.site_id) return list.find((site) => String(site.id) === String(body.site_id)) || null;
  return list.length === 1 ? list[0] : null;
}

export function createdAccountNotice(created, site) {
  const label = created?.username ? `${created.username} (mã #${created.id})` : "mới";
  return `Tạo tài khoản ${label} thành công!${site ? ` Đã phân công vào bãi ${site.name}.` : ""}`;
}
