import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import GridViewIcon from "@mui/icons-material/GridView";
import TableRowsIcon from "@mui/icons-material/TableRows";
import RefreshIcon from "@mui/icons-material/Refresh";
import CrudPage from "../../components/common/CrudPage";
import { getParkingSlotVisualStatus } from "../../utils/parkingSlotStatus";
import { vehicleTypeService } from "../VehicleType/services/vehicleTypeService";
import { zoneService } from "../Zone/services/zoneService";
import { parkingSlotService } from "./parkingSlotService";

const slotColors = {
  available: { background: "#e8f5e9", border: "#43a047", text: "#1b5e20", label: "Còn trống" },
  occupied: { background: "#ffebee", border: "#e53935", text: "#b71c1c", label: "Đang có xe" },
  inactive: { background: "#eceff1", border: "#90a4ae", text: "#455a64", label: "Bảo trì / ngừng dùng" },
};

export default function ParkingSlotPage() {
  const [view, setView] = useState("map");
  const [zones, setZones] = useState([]);
  const [types, setTypes] = useState([]);
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [zoneFilter, setZoneFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const loadMapData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [zoneList, typeList, slotList] = await Promise.all([
        zoneService.getAll(),
        vehicleTypeService.getAll(),
        parkingSlotService.getAll(),
      ]);
      setZones(zoneList);
      setTypes(typeList);
      setSlots(slotList);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Không thể tải sơ đồ chỗ đỗ.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMapData();
  }, [loadMapData, view]);

  const enrichedSlots = useMemo(() => {
    const zoneMap = new Map(zones.map((item) => [item.id, item]));
    const typeMap = new Map(types.map((item) => [item.id, item]));
    return slots.map((slot) => {
      const zone = zoneMap.get(slot.zone_id);
      return {
        ...slot,
        zone,
        vehicleType: typeMap.get(slot.vehicle_type_id),
        visualStatus: getParkingSlotVisualStatus(slot, zone),
      };
    });
  }, [slots, types, zones]);

  const filteredSlots = useMemo(() => enrichedSlots.filter((slot) => (
    (zoneFilter === "all" || slot.zone_id === Number(zoneFilter))
    && (typeFilter === "all" || slot.vehicle_type_id === Number(typeFilter))
    && (statusFilter === "all" || slot.visualStatus === statusFilter)
  )), [enrichedSlots, statusFilter, typeFilter, zoneFilter]);

  const groupedSlots = useMemo(() => {
    const groups = new Map();
    filteredSlots.forEach((slot) => {
      const key = slot.zone_id;
      if (!groups.has(key)) groups.set(key, { zone: slot.zone, slots: [] });
      groups.get(key).slots.push(slot);
    });
    return [...groups.values()].sort((left, right) => (left.zone?.name || "").localeCompare(right.zone?.name || ""));
  }, [filteredSlots]);

  const totals = useMemo(() => enrichedSlots.reduce((result, slot) => {
    result[slot.visualStatus] += 1;
    return result;
  }, { available: 0, occupied: 0, inactive: 0 }), [enrichedSlots]);

  const fields = [
    { name: "slot_name", label: "Mã vị trí", required: true },
    {
      name: "zone_id",
      label: "Khu vực",
      type: "select",
      required: true,
      options: zones.map((item) => ({ value: item.id, label: item.name })),
    },
    {
      name: "vehicle_type_id",
      label: "Loại xe",
      type: "select",
      required: true,
      options: types.map((item) => ({ value: item.id, label: item.name })),
    },
    { name: "is_active", label: "Đang hoạt động", type: "boolean" },
  ];

  return (
    <Stack spacing={2.5}>
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "stretch", sm: "center" }} gap={2}>
        <Box>
          <Typography variant="h5" fontWeight="bold">Quản lý vị trí đỗ</Typography>
          <Typography color="text.secondary">Theo dõi trực quan tình trạng từng vị trí theo khu vực.</Typography>
        </Box>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={view}
          onChange={(_, nextView) => nextView && setView(nextView)}
        >
          <ToggleButton value="map"><GridViewIcon sx={{ mr: 1 }} />Sơ đồ</ToggleButton>
          <ToggleButton value="table"><TableRowsIcon sx={{ mr: 1 }} />Danh sách</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {view === "table" ? (
        <CrudPage title="Danh sách vị trí đỗ" service={parkingSlotService} fields={fields} />
      ) : (
        <>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip color="success" label={`Còn trống: ${totals.available}`} />
            <Chip color="error" label={`Đang có xe: ${totals.occupied}`} />
            <Chip label={`Bảo trì / ngừng dùng: ${totals.inactive}`} />
            <Chip variant="outlined" label={`Tổng vị trí: ${enrichedSlots.length}`} />
          </Stack>

          <Paper sx={{ p: 2 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
              <TextField select size="small" label="Khu vực" value={zoneFilter} onChange={(event) => setZoneFilter(event.target.value)} sx={{ minWidth: 180 }}>
                <MenuItem value="all">Tất cả khu vực</MenuItem>
                {zones.map((zone) => <MenuItem key={zone.id} value={zone.id}>{zone.name}</MenuItem>)}
              </TextField>
              <TextField select size="small" label="Loại xe" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} sx={{ minWidth: 180 }}>
                <MenuItem value="all">Tất cả loại xe</MenuItem>
                {types.map((type) => <MenuItem key={type.id} value={type.id}>{type.name}</MenuItem>)}
              </TextField>
              <TextField select size="small" label="Trạng thái" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} sx={{ minWidth: 190 }}>
                <MenuItem value="all">Tất cả trạng thái</MenuItem>
                <MenuItem value="available">Còn trống</MenuItem>
                <MenuItem value="occupied">Đang có xe</MenuItem>
                <MenuItem value="inactive">Bảo trì / ngừng dùng</MenuItem>
              </TextField>
              <Button startIcon={<RefreshIcon />} onClick={loadMapData}>Làm mới</Button>
            </Stack>
          </Paper>

          {error && <Alert severity="error">{error}</Alert>}
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}><CircularProgress /></Box>
          ) : groupedSlots.length === 0 ? (
            <Alert severity="info">Không có vị trí phù hợp với bộ lọc.</Alert>
          ) : groupedSlots.map(({ zone, slots: zoneSlots }) => (
            <Paper key={zone?.id || "unknown"} sx={{ p: 2.5 }}>
              <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" sx={{ mb: 2 }}>
                <Typography variant="h6" fontWeight={700}>{zone?.name || "Chưa xác định khu vực"}</Typography>
                <Typography color="text.secondary">
                  {zoneSlots.filter((slot) => slot.visualStatus === "available").length}/{zoneSlots.length} vị trí đang trống
                </Typography>
              </Stack>
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(145px, 1fr))", gap: 1.5 }}>
                {zoneSlots.map((slot) => {
                  const style = slotColors[slot.visualStatus];
                  return (
                    <Box
                      key={slot.id}
                      sx={{
                        minHeight: 105,
                        p: 1.5,
                        borderRadius: 2,
                        border: "2px solid",
                        borderColor: style.border,
                        bgcolor: style.background,
                        color: style.text,
                      }}
                    >
                      <Typography fontWeight={800}>{slot.slot_name}</Typography>
                      <Typography variant="caption" display="block">{slot.vehicleType?.name || "Chưa có loại xe"}</Typography>
                      <Typography variant="caption" fontWeight={700}>{style.label}</Typography>
                    </Box>
                  );
                })}
              </Box>
            </Paper>
          ))}
        </>
      )}
    </Stack>
  );
}
