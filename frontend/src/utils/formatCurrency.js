const formatCurrency = (value) =>
  new Intl.NumberFormat("vi-VN").format(value);

export default formatCurrency;