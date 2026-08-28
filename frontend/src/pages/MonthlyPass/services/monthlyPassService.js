import api from "../../../services/api";
import { requestAllOffsetPages } from "../../../services/paginatedLookup";
import { requestMonthlyPassDeactivation } from "./monthlyPassCancellation";

const monthlyPassService = {
  getAll: async () => requestAllOffsetPages(api, "/api/v1/monthly-passes"),

  create: async (data) => {
    const response = await api.post("/api/v1/monthly-passes", data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/monthly-passes/${id}`, data);
    return response.data;
  },

  deactivate: async (id) => requestMonthlyPassDeactivation(api, id),

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
