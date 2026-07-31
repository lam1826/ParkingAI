import { useState, useEffect, useCallback } from "react";
import { vehicleTypeService } from "../services/vehicleTypeService";

export default function useVehicleType() {
  const [vehicleTypes, setVehicleTypes] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchVehicleTypes = useCallback(async () => {
    try {
      setLoading(true);
      const data = await vehicleTypeService.getAll();
      setVehicleTypes(data);
    } catch (error) {
      console.error("Lỗi tải danh sách loại xe:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVehicleTypes();
  }, [fetchVehicleTypes]);

  return { vehicleTypes, loading, fetchVehicleTypes };
}