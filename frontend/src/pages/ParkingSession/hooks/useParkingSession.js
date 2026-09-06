import { useState, useEffect, useCallback, useRef } from "react";
import parkingSessionService from "../services/parkingSessionService";
import { vehicleTypeService } from "../../VehicleType/services/vehicleTypeService";
import { zoneService } from "../../Zone/services/zoneService";
import { createLatestRequestGate } from "../../../utils/latestRequestGate";

const useParkingSession = () => {
  const sessionRequestGate = useRef(null);
  if (sessionRequestGate.current === null) {
    sessionRequestGate.current = createLatestRequestGate();
  }
  const slotRequestGate = useRef(null);
  if (slotRequestGate.current === null) {
    slotRequestGate.current = createLatestRequestGate();
  }

  const [sessions, setSessions] = useState([]);
  const [total, setTotal] = useState(0);
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
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);

  // Snackbar Notification State
  const [notify, setNotify] = useState({ open: false, message: "", severity: "info" });

  const showNotify = (message, severity = "info") => {
    setNotify({ open: true, message, severity });
  };

  const closeNotify = () => {
    setNotify((prev) => ({ ...prev, open: false }));
  };

  const fetchSessions = useCallback(async () => {
    const requestGate = sessionRequestGate.current;
    const requestGeneration = requestGate.begin();
    setLoading(true);
    try {
      const data = await parkingSessionService.getAllSessions({
        status: statusFilter,
        licensePlate: searchPlate.trim() || undefined,
        dateFrom,
        dateTo,
        page,
        pageSize,
      });
      if (!requestGate.isCurrent(requestGeneration)) return;
      setSessions(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      if (!requestGate.isCurrent(requestGeneration)) return;
      console.error("Lỗi lấy dữ liệu phiên đỗ:", err);
      setSessions([]);
      setTotal(0);
      showNotify(
        err.message || "Không thể tải danh sách phiên gửi xe",
        "error",
      );
    } finally {
      if (requestGate.isCurrent(requestGeneration)) setLoading(false);
    }
  }, [statusFilter, searchPlate, dateFrom, dateTo, page, pageSize]);

  const changeStatusFilter = useCallback((value) => {
    setPage(0);
    setStatusFilter(value);
  }, []);

  const changeSearchPlate = useCallback((value) => {
    setPage(0);
    setSearchPlate(value);
  }, []);

  const changeDateFrom = useCallback((value) => {
    setPage(0);
    setDateFrom(value);
  }, []);

  const changeDateTo = useCallback((value) => {
    setPage(0);
    setDateTo(value);
  }, []);

  const handlePaginationModelChange = useCallback((model) => {
    if (model.pageSize !== pageSize) {
      setPageSize(model.pageSize);
      setPage(0);
      return;
    }
    setPage(model.page);
  }, [pageSize]);

  const fetchAvailableSlots = useCallback(async () => {
    const requestGeneration = slotRequestGate.current.begin();
    try {
      const data = await parkingSessionService.getAvailableSlots();
      if (!slotRequestGate.current.isCurrent(requestGeneration)) return;
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
      if (!slotRequestGate.current.isCurrent(requestGeneration)) return;
      console.error("Lỗi lấy danh sách chỗ trống:", err);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
    return () => sessionRequestGate.current.invalidate();
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
    return () => slotRequestGate.current.invalidate();
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
      return res.session_id || res.id;
    } catch (err) {
      const detail = err.response?.data?.detail;
      showNotify(typeof detail === "string" ? detail : "Lỗi khi check-in xe. Kiểm tra dữ liệu và thử lại.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCheckoutCompleted = (result) => {
    const fee = new Intl.NumberFormat("vi-VN").format(result.parking_fee);
    showNotify(`Xe ra thành công! Phí đỗ xe: ${fee} VND`, "success");
    fetchSessions();
    fetchAvailableSlots();
  };

  return {
    sessions,
    total,
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
    setStatusFilter: changeStatusFilter,
    searchPlate,
    setSearchPlate: changeSearchPlate,
    dateFrom,
    setDateFrom: changeDateFrom,
    dateTo,
    setDateTo: changeDateTo,
    page,
    pageSize,
    handlePaginationModelChange,
    notify,
    handleCheckIn,
    handleCheckoutCompleted,
    fetchSessions,
    closeNotify,
  };
};

export default useParkingSession;
