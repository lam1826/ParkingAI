import { hasMinimumRole } from "./roles.js";

export function canEditUser(currentUser, target) {
  if (String(currentUser?.role).toLowerCase() === "admin") return true;
  return String(currentUser?.role).toLowerCase() === "manager"
    && String(target?.role?.name || target?.role).toLowerCase() === "staff"
    && currentUser?.id !== target?.id;
}

export function canCreateUser(currentUser) {
  return hasMinimumRole(currentUser?.role, "manager");
}

export function assignableRoles(currentUser, roles) {
  if (String(currentUser?.role).toLowerCase() === "admin") return roles;
  return String(currentUser?.role).toLowerCase() === "manager"
    ? roles.filter((role) => String(role.name).toLowerCase() === "staff") : [];
}
