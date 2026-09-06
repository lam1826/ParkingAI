export async function requestCheckoutQuote(apiClient, sessionId) {
  const { data } = await apiClient.get(
    `/api/v1/parking-sessions/${encodeURIComponent(sessionId)}/checkout-quote`,
  );
  return data;
}

export async function requestSessionCheckout(apiClient, sessionId, confirmation) {
  if (!confirmation?.quote_token || confirmation.payment_confirmed !== true
      || !["cash", "transfer", null].includes(confirmation.payment_method)) {
    throw new Error("Vui lòng xem phí và xác nhận thu tiền trước khi cho xe ra.");
  }
  const { data } = await apiClient.put(
    `/api/v1/parking-sessions/${encodeURIComponent(sessionId)}/check-out`,
    confirmation,
  );
  return data;
}
