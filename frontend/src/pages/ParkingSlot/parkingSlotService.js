import api from "../../services/api";
import { requestAllOffsetPages } from "../../services/paginatedLookup";

export const parkingSlotService = {
  getAll: async () => requestAllOffsetPages(api, "/api/v1/parking-slots"),
  create: async (data) => (await api.post("/api/v1/parking-slots", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/parking-slots/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/parking-slots/${id}`)).data,
};
