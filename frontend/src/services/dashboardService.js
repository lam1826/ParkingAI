import api from "./api";

const dashboardService = {
  getSummary: async () => {
    const response = await api.get("/dashboard");
    return response.data;
  },
  
  // Gọi endpoint mới được tách riêng
  getAIInsight: async () => {
    const response = await api.get("/dashboard/ai-insight");
    return response.data;
  }
};

export default dashboardService;