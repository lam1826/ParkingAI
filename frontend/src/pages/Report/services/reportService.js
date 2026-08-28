import api from "../../../services/api";

export const reportService = {
  getRevenueReport: async (params) => (await api.get("/reports/revenue", { params })).data,
  getTrafficReport: async (params) => (await api.get("/reports/traffic", { params })).data,
  downloadReport: async (format, period, anchorDate) => api.get(`/reports/export/${format}`, {
    params: { period, anchor_date: anchorDate },
    responseType: "blob",
  }),
};
