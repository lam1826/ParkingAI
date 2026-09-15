import { hasMinimumRole } from "./roles.js";

// Presentation permissions mirror the API; the server still authorizes every request.
export function corePermissions(role) {
  return {
    canManageConfiguration: hasMinimumRole(role, "manager"),
    canManageMonthlyPasses: hasMinimumRole(role, "manager"),
    canDeleteCustomerRecords: hasMinimumRole(role, "manager"),
  };
}
