import api from "../../../services/api";

export const vehicleTypeService = {
  getAll: async () => (await api.get("/api/v1/vehicle-types")).data,
  create: async (data) => (await api.post("/api/v1/vehicle-types", data)).data,
  update: async (id, data) => (await api.put(`/api/v1/vehicle-types/${id}`, data)).data,
  delete: async (id) => (await api.delete(`/api/v1/vehicle-types/${id}`)).data,
};