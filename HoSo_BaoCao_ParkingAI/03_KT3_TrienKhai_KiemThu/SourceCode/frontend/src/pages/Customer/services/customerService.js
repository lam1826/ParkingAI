import api from "../../../services/api"; // Import instance axios đã cấu hình interceptors
import { requestAllOffsetPages } from "../../../services/paginatedLookup";

export const customerService = {
  getAllCustomers: async () => requestAllOffsetPages(api, "/api/v1/customers"),
  
  createCustomer: async (customerData) => {
    const response = await api.post("/api/v1/customers", customerData);
    return response.data;
  },

  updateCustomer: async (id, customerData) => {
    const response = await api.put(`/api/v1/customers/${id}`, customerData);
    return response.data;
  },

  deleteCustomer: async (id) => {
    const response = await api.delete(`/api/v1/customers/${id}`);
    return response.data;
  }
};
export default customerService;
