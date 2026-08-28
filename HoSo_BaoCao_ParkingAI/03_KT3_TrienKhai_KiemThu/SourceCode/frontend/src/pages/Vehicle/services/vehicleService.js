import api from "../../../services/api";
import { requestAllOffsetPages } from "../../../services/paginatedLookup";

const vehicleService = {
  getAllVehicles: async () => requestAllOffsetPages(api, "/api/v1/vehicles"),
  
  // Lấy dữ liệu phụ trợ cho Form
  getVehicleTypes: async () => requestAllOffsetPages(api, "/api/v1/vehicle-types"),
  
  getCustomers: async () => requestAllOffsetPages(api, "/api/v1/customers"),

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
