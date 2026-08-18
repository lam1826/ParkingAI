import api from "../../../services/api";

export const zoneService = {
  getAll: async () => (await api.get("/api/v1/zones")).data,
  create: async (data) => (await api.post("/api/v1/zones", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/zones/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/zones/${id}`)).data,
};