import api from "./api";

const roleService = {
  getAll: async () => {
    const response = await api.get("/api/v1/roles");
    return response.data;
  },

  create: async (data) => {
    const response = await api.post("/api/v1/roles", data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/roles/${id}`, data);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/v1/roles/${id}`);
    return response.data;
  },
};

export default roleService;
