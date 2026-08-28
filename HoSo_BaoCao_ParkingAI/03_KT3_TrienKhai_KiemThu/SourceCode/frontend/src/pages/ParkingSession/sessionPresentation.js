const STATUS_PRESENTATION = Object.freeze({
  active: { label: "Đang gửi", color: "success", variant: "filled" },
  completed: { label: "Đã ra", color: "default", variant: "outlined" },
  cancelled: { label: "Đã hủy", color: "warning", variant: "outlined" },
});

const UNKNOWN_STATUS = Object.freeze({
  label: "Không xác định",
  color: "default",
  variant: "outlined",
});


export function getSessionStatusPresentation(status) {
  return STATUS_PRESENTATION[status] || UNKNOWN_STATUS;
}


export function formatParkingDuration(durationMinutes, status) {
  if (durationMinutes == null) return status === "active" ? "Đang gửi" : "—";
  const minutes = Number(durationMinutes);
  if (!Number.isInteger(minutes) || minutes < 0) return "—";
  if (minutes === 0) return "Dưới 1 phút";

  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (hours && remainder) return `${hours} giờ ${remainder} phút`;
  if (hours) return `${hours} giờ`;
  return `${remainder} phút`;
}
