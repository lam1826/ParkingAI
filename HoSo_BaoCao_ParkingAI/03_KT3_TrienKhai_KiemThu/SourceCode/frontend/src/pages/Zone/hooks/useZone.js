import { useState, useEffect, useCallback } from "react";
import { zoneService } from "../services/zoneService";

export default function useZone() {
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchZones = useCallback(async () => {
    try {
      setLoading(true);
      const data = await zoneService.getAll();
      setZones(data);
    } catch (error) {
      console.error("Lỗi tải danh sách khu vực:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchZones();
  }, [fetchZones]);

  return { zones, loading, fetchZones };
}