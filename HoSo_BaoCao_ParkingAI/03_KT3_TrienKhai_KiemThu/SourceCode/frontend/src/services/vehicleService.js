import api from "./api";

const vehicleService = {
  getAll: async () => {
    const response = await api.get("/api/vehicles");
    return response.data;
  },

  create: async (vehicleData) => {
    const response = await api.post("/api/vehicles", vehicleData);
    return response.data;
  },

  update: async (id, vehicleData) => {
    const response = await api.put(`/api/vehicles/${id}`, vehicleData);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/vehicles/${id}`);
    return response.data;
  },
};

export default vehicleService;