import api from "./api";

const monthlyPassService = {
  // Lấy danh sách vé tháng
  getAll: async () => {
    const response = await api.get("/api/monthlypasses");
    return response.data;
  },

  // Đăng ký vé tháng mới
  create: async (passData) => {
    const response = await api.post("/api/monthlypasses", passData);
    return response.data;
  },

  // Gia hạn vé tháng
  renew: async (id, renewalData) => {
    const response = await api.put(`/api/monthlypasses/renew/${id}`, renewalData);
    return response.data;
  },

  // Hủy / Khóa vé tháng
  delete: async (id) => {
    const response = await api.delete(`/api/monthlypasses/${id}`);
    return response.data;
  },
};

export default monthlyPassService;