import api from "../../../services/api";

const parkingSessionService = {
  // Tra cứu lịch sử gửi xe: status = "active" | "completed" | "" (tất cả)
  getAllSessions: async (filters = {}) => {
    const params = { size: 100 };
    if (filters.status) params.status = filters.status;
    if (filters.licensePlate) params.license_plate = filters.licensePlate;
    if (filters.dateFrom) params.date_from = filters.dateFrom;
    if (filters.dateTo) params.date_to = filters.dateTo;
    if (filters.zoneId) params.zone_id = filters.zoneId;
    if (filters.vehicleTypeId) params.vehicle_type_id = filters.vehicleTypeId;

    const { data } = await api.get("/parking/search", { params });
    return (data.items || []).map((item) => ({
      id: item.session_id,
      vehicle: item.vehicle,
      parking_slot: {
        slot_number: item.slot_name
          ? `${item.slot_name}${item.zone_name ? ` (${item.zone_name})` : ""}`
          : "Chưa xếp",
      },
      checkInTime: item.check_in_time,
      checkOutTime: item.check_out_time,
      parkingFee: item.parking_fee,
      status: item.status,
    }));
  },
  // Danh sách vị trí trống theo khu vực (phục vụ chọn chỗ khi check-in)
  getAvailableSlots: async () => (await api.get("/parking/available-slots")).data,
  checkIn: async ({ licensePlate, vehicleTypeId, zoneId, parkingSlotId }) => (
    await api.post("/parking/check-in", {
      license_plate: licensePlate,
      vehicle_type_id: vehicleTypeId,
      zone_id: zoneId || null,
      parking_slot_id: parkingSlotId || null,
    })
  ).data,
  checkOut: async (licensePlate) => (
    await api.post("/parking/check-out", { license_plate: licensePlate })
  ).data,
};

export default parkingSessionService;
