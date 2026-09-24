import { hasMinimumRole } from "../constants/roles.js";

export function canShowMenuItem(item, role, capabilities, singleSiteMode) {
  if (item.role && !hasMinimumRole(role, item.role)) return false;
  if (item.role && !item.scoped && !capabilities?.legacy_workspace_allowed) return false;
  // The scoped workspace already supplies entry/exit and finance. All other
  // core screens remain reachable when the backend authorizes this workspace.
  if (singleSiteMode && item.path === "/" && !item.scoped) return false;
  if (singleSiteMode && item.path === "/sessions") return false;
  if (singleSiteMode && item.path === "/finance" && capabilities?.site_finance_enabled) return false;
  return true;
}
