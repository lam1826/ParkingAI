import api from "../../../services/api";

const vehicleService = {
  getAllVehicles: async () => {
    const response = await api.get("/api/v1/vehicles");
    return response.data;
  },
  
  // Lấy dữ liệu phụ trợ cho Form
  getVehicleTypes: async () => {
    const response = await api.get("/api/v1/vehicle-types");
    return response.data;
  },
  
  getCustomers: async () => {
    const response = await api.get("/api/v1/customers");
    return response.data;
  },

  create: async (data) => {
    const response = await api.post("/api/v1/vehicles", data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/vehicles/${id}`, data);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/v1/vehicles/${id}`);
    return response.data;
  },
};

export default vehicleService;