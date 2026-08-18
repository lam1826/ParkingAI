import api from "./api";

const authService = {
  login: async (credentials) => {
    // credentials thường bao gồm username và password
    const response = await api.post("/api/auth/login", credentials);
    return response.data;
  },

  register: async (account) => {
    const response = await api.post("/api/auth/register", account);
    return response.data;
  },
  
  // Lấy thông tin user hiện tại dựa trên token
  getProfile: async () => {
    const response = await api.get("/api/auth/me");
    return response.data;
  },

  updateProfile: async (profile) => {
    const response = await api.put("/api/auth/me", profile);
    return response.data;
  },

  changePassword: async (passwords) => {
    const response = await api.put("/api/auth/me/password", passwords);
    return response.data;
  },
};

export default authService;
