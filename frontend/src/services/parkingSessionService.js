import api from "./api";

const parkingSessionService = {
  // Lấy toàn bộ danh sách phiên đỗ xe
  getAll: async () => {
    const response = await api.get("/api/parkingsessions");
    return response.data;
  },

  // Check-in xe vào bãi
  checkIn: async (sessionData) => {
    const response = await api.post("/api/parkingsessions/checkin", sessionData);
    return response.data;
  },

  // Check-out xe ra bãi & tính phí
  checkOut: async (id) => {
    const response = await api.put(`/api/parkingsessions/checkout/${id}`);
    return response.data;
  },

  // Lấy chi tiết phiên đỗ xe theo ID
  getById: async (id) => {
    const response = await api.get(`/api/parkingsessions/${id}`);
    return response.data;
  },
};

export default parkingSessionService;