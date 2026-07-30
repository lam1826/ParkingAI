import api from "./api";

const zoneService = {
  getAll: async () => {
    const response = await api.get("/zones/");
    return response.data;
  },
  
  create: async (data) => {
    const response = await api.post("/zones/", data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await api.put(`/zones/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await api.delete(`/zones/${id}`);
    return response.data;
  },
};

export default zoneService;