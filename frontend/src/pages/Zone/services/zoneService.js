import api from "../../../services/api";
import { requestAllOffsetPages } from "../../../services/paginatedLookup";

export const zoneService = {
  getAll: async () => requestAllOffsetPages(api, "/api/v1/zones"),
  create: async (data) => (await api.post("/api/v1/zones", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/zones/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/zones/${id}`)).data,
};
