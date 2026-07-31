import { useState, useEffect, useCallback } from "react";
import parkingSessionService from "../services/parkingSessionService";
import vehicleService from "../../Vehicle/services/vehicleService";

const useParkingSession = () => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [licensePlate, setLicensePlate] = useState("");

  // Snackbar Notification State
  const [notify, setNotify] = useState({ open: false, message: "", severity: "info" });

  const showNotify = (message, severity = "info") => {
    setNotify({ open: true, message, severity });
  };

  const closeNotify = () => {
    setNotify((prev) => ({ ...prev, open: false }));
  };

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await parkingSessionService.getAllSessions();
      const list = data.data || data || [];
      // Backend chưa hỗ trợ lọc theo status, nên lọc "active" ngay tại client
      setSessions(list.filter((s) => s.status === "active"));
    } catch (err) {
      console.error("Lỗi lấy dữ liệu phiên đỗ:", err);
      showNotify("Không thể tải danh sách xe đang đỗ", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleCheckIn = async (e) => {
    e.preventDefault();
    const plate = licensePlate.trim();
    if (!plate) return;

    setSubmitting(true);
    try {
      // Backend check-in cần vehicle_id, nên phải tra biển số ra xe trước
      const vehiclesRes = await vehicleService.getAllVehicles();
      const vehicles = vehiclesRes.data || vehiclesRes || [];
      const vehicle = vehicles.find(
        (v) => v.license_plate?.toUpperCase() === plate.toUpperCase()
      );

      if (!vehicle) {
        showNotify("Không tìm thấy xe với biển số này. Vui lòng đăng ký xe trước.", "error");
        return;
      }

      await parkingSessionService.checkIn(vehicle.id);
      showNotify("Ghi nhận xe vào thành công!", "success");
      setLicensePlate("");
      fetchSessions();
    } catch (err) {
      showNotify(err.response?.data?.detail || "Lỗi khi check-in xe", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCheckOut = async (sessionId) => {
    try {
      const res = await parkingSessionService.checkOut(sessionId);
      const fee = res.parking_fee ? new Intl.NumberFormat("vi-VN").format(res.parking_fee) : 0;
      showNotify(`Xe ra thành công! Phí đỗ xe: ${fee} VNĐ`, "success");
      fetchSessions();
    } catch (err) {
      showNotify(err.response?.data?.detail || "Lỗi khi check-out xe", "error");
    }
  };

  return {
    sessions,
    loading,
    submitting,
    licensePlate,
    setLicensePlate,
    notify,
    handleCheckIn,
    handleCheckOut,
    fetchSessions,
    closeNotify,
  };
};

export default useParkingSession;