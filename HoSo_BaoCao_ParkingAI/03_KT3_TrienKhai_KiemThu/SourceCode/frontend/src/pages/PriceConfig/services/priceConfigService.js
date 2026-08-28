import api from "../../../services/api";
import { requestAllOffsetPages } from "../../../services/paginatedLookup";

export const priceConfigService = {
  getAll: async () => requestAllOffsetPages(api, "/api/v1/price-configs"),
  create: async (data) => (await api.post("/api/v1/price-configs", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/price-configs/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/price-configs/${id}`)).data,
};
