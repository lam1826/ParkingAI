import { useState, useEffect, useCallback } from "react";
import parkingSessionService from "../services/parkingSessionService";
import { vehicleTypeService } from "../../VehicleType/services/vehicleTypeService";
import { zoneService } from "../../Zone/services/zoneService";

const useParkingSession = () => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Form check-in
  const [licensePlate, setLicensePlate] = useState("");
  const [vehicleTypeId, setVehicleTypeId] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [slotId, setSlotId] = useState("");

  // Dữ liệu tham chiếu
  const [vehicleTypes, setVehicleTypes] = useState([]);
  const [zones, setZones] = useState([]);
  const [availableSlots, setAvailableSlots] = useState([]);

  // Bộ lọc lịch sử: "active" | "completed" | "" (tất cả)
  const [statusFilter, setStatusFilter] = useState("active");
  const [searchPlate, setSearchPlate] = useState("");

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
      const data = await parkingSessionService.getAllSessions({
        status: statusFilter,
        licensePlate: searchPlate.trim() || undefined,
      });
      setSessions(data || []);
    } catch (err) {
      console.error("Lỗi lấy dữ liệu phiên đỗ:", err);
      showNotify("Không thể tải danh sách phiên gửi xe", "error");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchPlate]);

  const fetchAvailableSlots = useCallback(async () => {
    try {
      const data = await parkingSessionService.getAvailableSlots();
      // Trải phẳng danh sách slot trống của từng khu vực
      const slots = (data.zones || []).flatMap((z) =>
        (z.available_slots_list || []).map((s) => ({
          ...s,
          zone_id: z.zone_id,
          zone_name: z.zone_name,
        }))
      );
      setAvailableSlots(slots);
    } catch (err) {
      console.error("Lỗi lấy danh sách chỗ trống:", err);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    (async () => {
      try {
        const [types, zoneList] = await Promise.all([
          vehicleTypeService.getAll(),
          zoneService.getAll(),
        ]);
        setVehicleTypes(types || []);
        setZones(zoneList || []);
      } catch (err) {
        console.error("Lỗi tải dữ liệu tham chiếu:", err);
      }
    })();
    fetchAvailableSlots();
  }, [fetchAvailableSlots]);

  const handleCheckIn = async (e) => {
    e.preventDefault();
    const plate = licensePlate.trim();
    if (!plate) return;
    if (!vehicleTypeId) {
      showNotify("Vui lòng chọn loại phương tiện.", "warning");
      return;
    }

    setSubmitting(true);
    try {
      // Backend tự đăng ký xe mới nếu biển số chưa tồn tại
      const res = await parkingSessionService.checkIn({
        licensePlate: plate,
        vehicleTypeId,
        zoneId: zoneId || null,
        parkingSlotId: slotId || null,
      });
      showNotify(
        `Ghi nhận xe vào thành công! Vị trí: ${res.slot_name || res.slot_id}`,
        "success"
      );
      setLicensePlate("");
      setSlotId("");
      fetchSessions();
      fetchAvailableSlots();
    } catch (err) {
      showNotify(err.response?.data?.detail || "Lỗi khi check-in xe", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCheckOut = async (plate) => {
    try {
      const res = await parkingSessionService.checkOut(plate);
      const fee = res.parking_fee ? new Intl.NumberFormat("vi-VN").format(res.parking_fee) : 0;
      showNotify(`Xe ra thành công! Phí đỗ xe: ${fee} VNĐ`, "success");
      fetchSessions();
      fetchAvailableSlots();
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
    vehicleTypeId,
    setVehicleTypeId,
    zoneId,
    setZoneId,
    slotId,
    setSlotId,
    vehicleTypes,
    zones,
    availableSlots,
    statusFilter,
    setStatusFilter,
    searchPlate,
    setSearchPlate,
    notify,
    handleCheckIn,
    handleCheckOut,
    fetchSessions,
    closeNotify,
  };
};

export default useParkingSession;
