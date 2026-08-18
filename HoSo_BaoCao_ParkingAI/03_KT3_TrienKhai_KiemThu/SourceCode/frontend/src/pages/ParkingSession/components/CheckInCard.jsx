import {
  Card,
  CardContent,
  Typography,
  Box,
  TextField,
  MenuItem,
  Button,
  CircularProgress,
} from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";

const CheckInCard = ({
  licensePlate,
  onChangePlate,
  vehicleTypeId,
  onChangeVehicleType,
  zoneId,
  onChangeZone,
  slotId,
  onChangeSlot,
  vehicleTypes = [],
  zones = [],
  availableSlots = [],
  onSubmit,
  submitting,
}) => {
  // Chỉ hiển thị các vị trí trống phù hợp loại xe và khu vực đã chọn
  const filteredSlots = availableSlots.filter((s) => {
    if (vehicleTypeId && s.vehicle_type_id !== vehicleTypeId) return false;
    if (zoneId && s.zone_id !== zoneId) return false;
    return true;
  });

  return (
    <Card elevation={0} sx={{ border: "1px solid #e0e0e0", mb: 3 }}>
      <CardContent>
        <Typography variant="h6" fontWeight="bold" gutterBottom>
          Ghi nhận Xe Vào
        </Typography>
        <Box
          component="form"
          onSubmit={onSubmit}
          sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 2 }}
        >
          <TextField
            size="small"
            placeholder="Nhập biển số xe (VD: 30A-12345)"
            label="Biển số xe"
            value={licensePlate}
            onChange={(e) => onChangePlate(e.target.value)}
            required
            disabled={submitting}
            sx={{ flex: "1 1 200px" }}
          />
          <TextField
            select
            size="small"
            label="Loại xe"
            value={vehicleTypeId}
            onChange={(e) => {
              onChangeVehicleType(e.target.value);
              onChangeSlot("");
            }}
            required
            disabled={submitting}
            sx={{ flex: "1 1 160px" }}
          >
            {vehicleTypes.map((t) => (
              <MenuItem key={t.id} value={t.id}>
                {t.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label="Khu vực (tùy chọn)"
            value={zoneId}
            onChange={(e) => {
              onChangeZone(e.target.value);
              onChangeSlot("");
            }}
            disabled={submitting}
            sx={{ flex: "1 1 160px" }}
          >
            <MenuItem value="">Tự động</MenuItem>
            {zones.map((z) => (
              <MenuItem key={z.id} value={z.id}>
                {z.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label="Vị trí đỗ (tùy chọn)"
            value={slotId}
            onChange={(e) => onChangeSlot(e.target.value)}
            disabled={submitting}
            sx={{ flex: "1 1 180px" }}
            helperText={
              vehicleTypeId && filteredSlots.length === 0
                ? "Không còn vị trí trống phù hợp"
                : ""
            }
          >
            <MenuItem value="">Tự động cấp phát</MenuItem>
            {filteredSlots.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.name} — {s.zone_name}
              </MenuItem>
            ))}
          </TextField>
          <Button
            type="submit"
            variant="contained"
            color="success"
            startIcon={submitting ? <CircularProgress size={20} color="inherit" /> : <LoginIcon />}
            disabled={submitting || !licensePlate.trim() || !vehicleTypeId}
            sx={{ minWidth: 140, fontWeight: "bold" }}
          >
            Check In
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
};

export default CheckInCard;
