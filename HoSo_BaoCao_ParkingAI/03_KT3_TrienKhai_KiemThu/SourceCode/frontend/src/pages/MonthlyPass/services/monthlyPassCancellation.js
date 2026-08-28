export async function requestMonthlyPassDeactivation(apiClient, passId) {
  const { data } = await apiClient.put(
    `/api/v1/monthly-passes/${encodeURIComponent(passId)}`,
    { is_active: false },
  );
  return data;
}
