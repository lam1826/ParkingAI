// Canonical authorization roles (same set as backend core/roles.py). The Roles
// page lets an Admin restore a missing one through POST /api/v1/roles.
export const CANONICAL_ROLES = [
  { name: "admin", description: "Quản trị viên hệ thống" },
  { name: "manager", description: "Quản lý bãi đỗ xe" },
  { name: "staff", description: "Nhân viên vận hành bãi" },
  { name: "customer", description: "Khách hàng" },
];

export function missingCanonicalRoles(roles) {
  const present = new Set((Array.isArray(roles) ? roles : []).map((role) => String(role?.name ?? "").trim().toLowerCase()));
  return CANONICAL_ROLES.filter((role) => !present.has(role.name)).map((role) => ({ ...role }));
}
