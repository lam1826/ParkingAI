const DEFAULT_PAGE_SIZE = 10;
const MAX_PAGE_SIZE = 100;


function positivePageSize(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= MAX_PAGE_SIZE
    ? parsed
    : DEFAULT_PAGE_SIZE;
}


export function buildParkingSearchParams(filters = {}) {
  const dateFrom = filters.dateFrom || "";
  const dateTo = filters.dateTo || "";
  if (dateFrom && dateTo && dateFrom > dateTo) {
    throw new RangeError("Ngày bắt đầu không được sau ngày kết thúc.");
  }

  const uiPage = Number(filters.page);
  const params = {
    page: Number.isInteger(uiPage) && uiPage >= 0 ? uiPage + 1 : 1,
    size: positivePageSize(filters.pageSize),
  };

  if (filters.status) params.status = filters.status;
  if (filters.licensePlate?.trim()) params.license_plate = filters.licensePlate.trim();
  if (dateFrom) params.date_from = `${dateFrom}T00:00:00`;
  if (dateTo) params.date_to = `${dateTo}T23:59:59.999999`;
  if (filters.zoneId) params.zone_id = filters.zoneId;
  if (filters.vehicleTypeId) params.vehicle_type_id = filters.vehicleTypeId;
  return params;
}


function mapSession(item) {
  return {
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
  };
}


export function mapParkingSearchResponse(data = {}) {
  const apiPage = Number(data.page);
  return {
    items: Array.isArray(data.items) ? data.items.map(mapSession) : [],
    total: Number.isFinite(Number(data.total)) ? Number(data.total) : 0,
    page: Number.isInteger(apiPage) && apiPage >= 1 ? apiPage - 1 : 0,
    pageSize: positivePageSize(data.size),
  };
}


export async function requestParkingSessionSearch(apiClient, filters = {}) {
  const params = buildParkingSearchParams(filters);
  const { data } = await apiClient.get("/parking/search", { params });
  return mapParkingSearchResponse(data);
}
