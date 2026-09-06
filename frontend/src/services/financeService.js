import api from "./api";

const financeService = {
  async getPayments(params = {}) {
    return (await api.get("/api/v1/payments", { params })).data;
  },
  async getShifts(params = {}) {
    return (await api.get("/api/v1/cash-shifts", { params })).data;
  },
  async openShift(openingCash) {
    return (await api.post("/api/v1/cash-shifts", { opening_cash: openingCash })).data;
  },
  async closeShift(id, countedCash) {
    return (await api.post(`/api/v1/cash-shifts/${id}/close`, { counted_cash: countedCash })).data;
  },
  async refund(id, payload) {
    return (await api.post(`/api/v1/payments/${id}/refund`, payload)).data;
  },
};

export default financeService;
