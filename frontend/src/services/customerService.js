import api from "./api";

const customerService = {
  getAll: async () => {
    const response = await api.get("/api/v1/customers");
    return response.data;
  },
};

export default customerService;
