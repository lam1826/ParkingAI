import api from "./api";

const priceConfigService = {
  getAll: async () => {
    const response = await api.get("/api/v1/price-configs");
    return response.data;
  },

  create: async (data) => {
    const response = await api.post("/api/v1/price-configs", data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/price-configs/${id}`, data);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/v1/price-configs/${id}`);
    return response.data;
  },
};

export default priceConfigService;
