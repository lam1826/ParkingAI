import api from "./api";

const userService = {
  getAll: async () => {
    const response = await api.get("/api/v1/users");
    return response.data;
  },

  create: async (data) => {
    const response = await api.post("/api/v1/users", data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/users/${id}`, data);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/v1/users/${id}`);
    return response.data;
  },
};

export default userService;
