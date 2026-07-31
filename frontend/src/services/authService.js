import api from "./api";

const authService = {
  login: async (credentials) => {
    // credentials thường bao gồm username và password
    const response = await api.post("/api/auth/login", credentials);
    return response.data;
  },
  
  // Lấy thông tin user hiện tại dựa trên token
  getProfile: async () => {
    const response = await api.get("/api/auth/me");
    return response.data;
  }
};

export default authService;