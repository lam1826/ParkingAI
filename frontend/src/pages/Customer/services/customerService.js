import api from "../../../services/api"; // Import instance axios đã cấu hình interceptors

export const customerService = {
  getAllCustomers: async () => {
    const response = await api.get("/api/v1/customers");
    return response.data;
  },
  
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