import api from "../../../services/api";

const parkingSessionService = {
  getAllSessions: async () => {
    const { data } = await api.get("/parking/search", { params: { status: "active", size: 100 } });
    return (data.items || []).map((item) => ({
      id: item.session_id,
      vehicle: item.vehicle,
      parking_slot: { slot_number: item.slot_id ? `#${item.slot_id}` : "Chưa xếp" },
      checkInTime: item.check_in_time,
      status: item.status,
    }));
  },
  checkIn: async ({ licensePlate, vehicleTypeId }) => (
    await api.post("/parking/check-in", { license_plate: licensePlate, vehicle_type_id: vehicleTypeId })
  ).data,
  checkOut: async (licensePlate) => (
    await api.post("/parking/check-out", { license_plate: licensePlate })
  ).data,
};

export default parkingSessionService;
