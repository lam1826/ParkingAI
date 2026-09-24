export function canStartCameraAutomation(camera, policy, canManage) {
  return Boolean(camera?.is_active && policy && (policy.enabled || canManage));
}

export function automationPolicyUpdate(policy, enabled) {
  return {
    enabled,
    minimum_confidence: policy.minimum_confidence,
    max_age_seconds: policy.max_age_seconds,
  };
}

// Source permission and server permission must both succeed before live capture.
// A failed reload is not confirmation, even if the preceding write succeeded.
export async function startCameraAutomation({ policy, canManage, hasSource, openSource, enablePolicy, reloadPolicy, isActive }) {
  if (!policy || (!policy.enabled && !canManage)) {
    throw new Error("Cần Admin hoặc Manager cho phép tự động ở camera này.");
  }
  if (!isActive()) return false;
  if (!hasSource && !await openSource()) {
    throw new Error("Chưa mở được webcam. Kiểm tra quyền camera rồi thử lại.");
  }
  if (!isActive()) return false;
  if (!policy.enabled) {
    const updated = await enablePolicy(automationPolicyUpdate(policy, true));
    if (!updated?.enabled) throw new Error("Máy chủ chưa cho phép tự động. Hãy thử lại.");
  }
  if (!isActive()) return false;
  const confirmed = await reloadPolicy();
  if (!isActive()) return false;
  if (!confirmed?.enabled) throw new Error("Chưa xác nhận được quyền tự động từ máy chủ. Hãy tải lại cài đặt rồi thử lại.");
  return true;
}
