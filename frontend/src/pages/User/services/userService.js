import api from "../../../services/api";
import { requestAllOffsetPages } from "../../../services/paginatedLookup";

const userService = {
  getAllUsers: async () => requestAllOffsetPages(api, "/api/v1/users"),

  getRoles: async () => requestAllOffsetPages(api, "/api/v1/roles"),

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

  // API Đổi trạng thái (Active/Inactive) nhanh
  toggleStatus: async (id, isActive) => {
    const response = await api.patch(`/api/v1/users/${id}/status`, { is_active: isActive });
    return response.data;
  }
};

export default userService;
