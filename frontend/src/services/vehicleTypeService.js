import api from "./api";

const vehicleTypeService = {
  getAll: async () => {
    const response = await api.get("/api/v1/vehicle-types");
    return response.data;
  },
};

export default vehicleTypeService;
