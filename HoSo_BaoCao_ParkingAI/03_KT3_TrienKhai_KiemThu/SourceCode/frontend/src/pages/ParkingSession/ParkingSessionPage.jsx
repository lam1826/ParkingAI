import {
  Box,
  Typography,
  Button,
  Stack,
  Snackbar,
  Alert,
  TextField,
  MenuItem,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

import CheckInCard from "./components/CheckInCard";
import SessionTable from "./components/SessionTable";
import useParkingSession from "./hooks/useParkingSession";

export default function ParkingSessionPage() {
  const {
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
  } = useParkingSession();

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5" fontWeight="bold">
          Quản lý Xe Vào / Ra
        </Typography>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={fetchSessions}
          disabled={loading}
        >
          Làm mới
        </Button>
      </Stack>

      {/* Check In Form */}
      <CheckInCard
        licensePlate={licensePlate}
        onChangePlate={setLicensePlate}
        vehicleTypeId={vehicleTypeId}
        onChangeVehicleType={setVehicleTypeId}
        zoneId={zoneId}
        onChangeZone={setZoneId}
        slotId={slotId}
        onChangeSlot={setSlotId}
        vehicleTypes={vehicleTypes}
        zones={zones}
        availableSlots={availableSlots}
        onSubmit={handleCheckIn}
        submitting={submitting}
      />

      {/* Bộ lọc lịch sử gửi xe */}
      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label="Trạng thái"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          sx={{ minWidth: 170 }}
        >
          <MenuItem value="active">Đang gửi trong bãi</MenuItem>
          <MenuItem value="completed">Đã rời bãi</MenuItem>
          <MenuItem value="">Tất cả</MenuItem>
        </TextField>
        <TextField
          size="small"
          label="Tìm theo biển số"
          value={searchPlate}
          onChange={(e) => setSearchPlate(e.target.value)}
          sx={{ minWidth: 220 }}
        />
      </Stack>

      {/* Table lịch sử/danh sách phiên gửi xe */}
      <SessionTable
        sessions={sessions}
        loading={loading}
        onCheckOut={handleCheckOut}
        title={
          statusFilter === "active"
            ? "Danh sách xe đang đỗ trong bãi"
            : statusFilter === "completed"
              ? "Lịch sử xe đã rời bãi"
              : "Toàn bộ lịch sử gửi xe"
        }
      />

      {/* Notification Snackbar */}
      <Snackbar
        open={notify.open}
        autoHideDuration={4000}
        onClose={closeNotify}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert severity={notify.severity} variant="filled" onClose={closeNotify} sx={{ width: "100%" }}>
          {notify.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
