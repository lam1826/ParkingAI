const formatCurrency = (value) =>
  new Intl.NumberFormat("vi-VN").format(value);

export const formatParkingFee = (value, fallback = "—") =>
  value === null || value === undefined ? fallback : formatCurrency(value);

export default formatCurrency;
