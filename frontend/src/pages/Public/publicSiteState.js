// Pure presentation helpers for the public lot page; no network, no invented data.
const NOT_PUBLISHED = "Chưa cập nhật";

export const notPublished = NOT_PUBLISHED;

export function textOrPlaceholder(value) {
  return typeof value === "string" && value.trim() ? value.trim() : NOT_PUBLISHED;
}

function finiteCoordinate(value, limit) {
  const number = Number(value);
  return Number.isFinite(number) && Math.abs(number) <= limit ? number : null;
}

// Directions and map links come from the published coordinates first, then the
// address. Both use key-free public URLs; nothing is requested from a paid API.
export function mapLinks(profile) {
  const latitude = finiteCoordinate(profile?.location?.latitude, 90);
  const longitude = finiteCoordinate(profile?.location?.longitude, 180);
  if (latitude !== null && longitude !== null) {
    const point = `${latitude},${longitude}`;
    const delta = 0.005;
    const bbox = [longitude - delta, latitude - delta, longitude + delta, latitude + delta].map((n) => n.toFixed(5)).join("%2C");
    return {
      kind: "coordinates",
      directions: `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(point)}`,
      open: `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`,
      embed: `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${latitude}%2C${longitude}`,
    };
  }
  const address = typeof profile?.address === "string" ? profile.address.trim() : "";
  if (address) {
    const query = encodeURIComponent(address);
    return { kind: "address", directions: `https://www.google.com/maps/dir/?api=1&destination=${query}`,
      open: `https://www.google.com/maps/search/?api=1&query=${query}`, embed: null };
  }
  return { kind: "none", directions: null, open: null, embed: null };
}

export const productLabel = (kind) => ({ monthly: "Vé tháng", hourly: "Vé giờ", daily: "Vé ngày" })[kind] || "Gói vé";

export function planDuration(plan) {
  if (plan.product_kind === "monthly") return `${plan.duration_days} ngày`;
  if (plan.product_kind === "daily") return "24 giờ";
  const minutes = Number(plan.duration_minutes);
  return Number.isSafeInteger(minutes) && minutes > 0 ? `${minutes % 60 === 0 ? minutes / 60 + " giờ" : minutes + " phút"}` : NOT_PUBLISHED;
}

export const rateUnit = (ticketType) => (ticketType === "DAILY" ? "/ 24 giờ" : "/ giờ");

export const paymentModeLabel = (mode) => ({ demo: "Thanh toán DEMO (mô phỏng, không chuyển tiền)", manual: "Thu tại quầy",
  payos: "Chuyển khoản QR" })[mode] || mode;

// One continuation per call to action; the login page validates it again.
export function actionTargets(profile, user) {
  const purchase = `/portal?tab=purchase${profile?.plans?.some((plan) => plan.product_kind !== "monthly") ? "&kind=hourly" : ""}`;
  const reserve = "/reservations";
  if (!user) return { purchase: { to: `/login?next=${encodeURIComponent(purchase)}`, label: "Đăng nhập để mua vé" },
    reserve: { to: `/login?next=${encodeURIComponent(reserve)}`, label: "Đăng nhập để đặt chỗ" }, signedIn: false };
  if (user.role === "customer") return { purchase: { to: purchase, label: "Mua vé" }, reserve: { to: reserve, label: "Đặt chỗ" }, signedIn: true };
  return { purchase: { to: "/sites", label: "Vào vận hành bãi" }, reserve: null, signedIn: true };
}
