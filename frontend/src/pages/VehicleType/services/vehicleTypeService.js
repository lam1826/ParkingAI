import api from "../../../services/api";
import { requestAllOffsetPages } from "../../../services/paginatedLookup";

export const vehicleTypeService = {
  getAll: async () => requestAllOffsetPages(api, "/api/v1/vehicle-types"),
  create: async (data) => (await api.post("/api/v1/vehicle-types", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/vehicle-types/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/vehicle-types/${id}`)).data,
};
