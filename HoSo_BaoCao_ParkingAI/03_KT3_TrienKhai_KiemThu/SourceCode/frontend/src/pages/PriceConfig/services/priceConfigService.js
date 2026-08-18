import api from "../../../services/api";

export const priceConfigService = {
  getAll: async () => (await api.get("/api/v1/price-configs")).data,
  create: async (data) => (await api.post("/api/v1/price-configs", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/price-configs/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/price-configs/${id}`)).data,
};