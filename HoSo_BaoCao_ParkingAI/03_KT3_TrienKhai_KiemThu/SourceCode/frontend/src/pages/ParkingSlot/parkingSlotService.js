import api from "../../services/api";

export const parkingSlotService = {
  getAll: async () => (await api.get("/api/v1/parking-slots")).data,
  create: async (data) => (await api.post("/api/v1/parking-slots", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/parking-slots/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/parking-slots/${id}`)).data,
};
