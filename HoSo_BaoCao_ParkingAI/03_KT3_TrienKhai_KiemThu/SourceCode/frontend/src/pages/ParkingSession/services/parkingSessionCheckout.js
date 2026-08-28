export async function requestSessionCheckout(apiClient, sessionId) {
  const { data } = await apiClient.put(
    `/api/v1/parking-sessions/${encodeURIComponent(sessionId)}/check-out`,
    {},
  );
  return data;
}
