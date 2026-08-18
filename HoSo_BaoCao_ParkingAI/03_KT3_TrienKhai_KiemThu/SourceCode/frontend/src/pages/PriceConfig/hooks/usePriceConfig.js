import { useState, useEffect, useCallback } from "react";
import { priceConfigService } from "../services/priceConfigService";

export default function usePriceConfig() {
  const [priceConfigs, setPriceConfigs] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchPriceConfigs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await priceConfigService.getAll();
      setPriceConfigs(data);
    } catch (error) {
      console.error("Lỗi tải cấu hình giá:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPriceConfigs();
  }, [fetchPriceConfigs]);

  return { priceConfigs, loading, fetchPriceConfigs };
}