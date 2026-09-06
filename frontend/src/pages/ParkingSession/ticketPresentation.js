import { formatParkingFee } from "../../utils/formatCurrency.js";

export function getTicketPresentation(ticket) {
  switch (ticket?.status) {
    case "active":
      return { title: "Vé gửi xe", summary: "Chưa tính phí · Xe đang trong bãi", canCheckOut: true,
        instruction: "Giữ vé và đối chiếu biển số khi nhận xe." };
    case "completed":
      return { title: "Biên nhận gửi xe", summary: `Phí gửi xe: ${formatParkingFee(ticket.parking_fee)}`, canCheckOut: false,
        instruction: "Lượt gửi xe đã hoàn tất. Giữ biên nhận để đối chiếu." };
    case "cancelled":
      return { title: "Vé gửi xe đã hủy", summary: "Lượt gửi xe đã hủy · Vé không còn hiệu lực", canCheckOut: false,
        instruction: "Mã QR chỉ dùng để tra cứu lượt gửi xe đã hủy." };
    default:
      return { title: "Vé gửi xe", summary: "Chưa xác định trạng thái lượt gửi xe", canCheckOut: false,
        instruction: "Tải lại vé để kiểm tra trạng thái trước khi thao tác." };
  }
}
