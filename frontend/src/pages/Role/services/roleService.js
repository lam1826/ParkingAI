import api from "../../../services/api";
import { requestAllOffsetPages } from "../../../services/paginatedLookup";

export const roleService = {
  getAll: async () => requestAllOffsetPages(api, "/api/v1/roles"),
  create: async (data) => (await api.post("/api/v1/roles", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/roles/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/roles/${id}`)).data,
};
