import { useState, useEffect, useCallback } from "react";
import { roleService } from "../services/roleService";

export default function useRole() {
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchRoles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await roleService.getAll();
      setRoles(data);
      setError(null);
    } catch (error) {
      console.error("Lỗi tải danh sách quyền:", error);
      setError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

  return { roles, loading, error, fetchRoles };
}