import api from "../../../services/api";

const monthlyPassService = {
  getAll: async () => {
    const response = await api.get("/api/v1/monthly-passes");
    return response.data;
  },

  create: async (data) => {
    const response = await api.post("/api/v1/monthly-passes", data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/monthly-passes/${id}`, data);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/v1/monthly-passes/${id}`);
    return response.data;
  },

  // API mở rộng: Gia hạn vé tháng
  extendPass: async (id, months) => {
    const response = await api.post(`/api/v1/monthly-passes/${id}/extend`, { months });
    return response.data;
  }
};

export default monthlyPassService;