// File: src/services/dashboardService.js (hoặc src/pages/Dashboard/services/dashboardService.js)
import api from "../../../services/api"; // Đảm bảo đường dẫn import file api đúng với cấu trúc thực tế

const dashboardService = {
  getSummary: async () => {
    const response = await api.get("/dashboard");
    return response.data;
  },

  getAIInsight: async () => {
    const response = await api.get("/dashboard/ai-insight");
    return response.data;
  },

  getRecentSessions: async () => {
    const response = await api.get("/dashboard/recent-sessions");
    return response.data;
  },

  getRevenueChart: async () => {
    const response = await api.get("/dashboard/revenue-chart");
    return response.data;
  },

  getTrafficChart: async () => {
    const response = await api.get("/reports/traffic");
    // Backend trả về { traffic_by_hour: [{ time_label, total_vehicles }], ... }
    // Chart cần dạng [{ hour, count }]
    const byHour = response.data?.traffic_by_hour || [];
    return byHour.map((item) => ({ hour: item.time_label, count: item.total_vehicles }));
  },
};

export default dashboardService;