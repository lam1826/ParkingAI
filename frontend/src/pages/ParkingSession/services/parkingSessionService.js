import api from "../../../services/api";

const parkingSessionService = {
  // Lấy danh sách toàn bộ phiên đỗ (lọc active ở phía hook)
  getAllSessions: async () => {
    const response = await api.get("/api/v1/parking-sessions");
    return response.data;
  },

  // Ghi nhận xe vào (backend yêu cầu vehicle_id, không nhận license_plate trực tiếp)
  checkIn: async (vehicleId) => {
    const response = await api.post("/api/v1/parking-sessions/check-in", {
      vehicle_id: vehicleId,
    });
    return response.data;
  },

  // Ghi nhận xe ra
  checkOut: async (sessionId) => {
    const response = await api.put(`/api/v1/parking-sessions/${sessionId}/check-out`, {});
    return response.data;
  },
};

export default parkingSessionService;