import api from "../../../services/api";
import { requestCheckoutQuote, requestSessionCheckout } from "./parkingSessionCheckout";
import { requestParkingSessionSearch } from "./parkingSessionSearch";

const parkingSessionService = {
  // Tra cứu lịch sử: status = "active" | "completed" | "cancelled" | ""
  getAllSessions: async (filters = {}) => requestParkingSessionSearch(api, filters),
  // Danh sách vị trí trống theo khu vực (phục vụ chọn chỗ khi check-in)
  getAvailableSlots: async () => (await api.get("/parking/available-slots")).data,
  checkIn: async ({ licensePlate, vehicleTypeId, zoneId, parkingSlotId }) => (
    await api.post("/parking/check-in", {
      license_plate: licensePlate,
      vehicle_type_id: vehicleTypeId,
      zone_id: zoneId || null,
      parking_slot_id: parkingSlotId || null,
    })
  ).data,
  getCheckoutQuote: async (sessionId) => requestCheckoutQuote(api, sessionId),
  checkOut: async (sessionId, confirmation) => requestSessionCheckout(api, sessionId, confirmation),
};

export default parkingSessionService;
