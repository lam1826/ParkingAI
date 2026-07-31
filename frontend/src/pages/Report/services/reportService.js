import api from "../../../services/api";

export const reportService = {
  getRevenueReport: async (params) => (await api.get("/reports/revenue", { params })).data,
  getTrafficReport: async (params) => (await api.get("/reports/traffic", { params })).data,
};