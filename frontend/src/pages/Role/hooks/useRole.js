import { useState, useEffect, useCallback } from "react";
import { roleService } from "../services/roleService";

export default function useRole() {
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchRoles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await roleService.getAll();
      setRoles(data);
    } catch (error) {
      console.error("Lỗi tải danh sách quyền:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

  return { roles, loading, fetchRoles };
}