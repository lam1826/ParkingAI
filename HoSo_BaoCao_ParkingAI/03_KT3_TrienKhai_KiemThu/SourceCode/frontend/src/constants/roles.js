export const ROLE_LEVELS = Object.freeze({
  customer: 0,
  staff: 1,
  manager: 2,
  admin: 3,
});


export function hasMinimumRole(role, minimumRole) {
  const currentLevel = ROLE_LEVELS[String(role || "").toLowerCase()];
  const requiredLevel = ROLE_LEVELS[String(minimumRole || "").toLowerCase()];
  return currentLevel !== undefined
    && requiredLevel !== undefined
    && currentLevel >= requiredLevel;
}
