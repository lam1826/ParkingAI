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
import { useState } from "react";
import api from "../../services/api";
import TicketDialog from "./components/TicketDialog";

import CheckInCard from "./components/CheckInCard";
import SessionTable from "./components/SessionTable";
import useParkingSession from "./hooks/useParkingSession";

export default function ParkingSessionPage() {
  const [ticketId, setTicketId] = useState(null);
  const [scan, setScan] = useState("");
  const [scanError, setScanError] = useState("");
  const [scanning, setScanning] = useState(false);
  const resolveScan = async (event) => {
    event.preventDefault();
    if (scanning || !scan.trim()) return;
    setScanning(true); setScanError("");
    try {
      const { data } = await api.get("/api/v1/parking-sessions/tickets/resolve", { params: { token: scan.trim() } });
      setTicketId(data.session_id); setScan("");
    } catch (error) {
      const detail = error.response?.data?.detail;
      setScanError(typeof detail === "string" ? detail : "Không tra được vé. Kiểm tra lại mã QR và thử lại.");
    } finally { setScanning(false); }
  };
  const {
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
    setStatusFilter,
    searchPlate,
    setSearchPlate,
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    page,
    pageSize,
    handlePaginationModelChange,
    notify,
    handleCheckIn,
    handleCheckOut,
    fetchSessions,
    closeNotify,
  } = useParkingSession();
  const invalidDateRange = Boolean(dateFrom && dateTo && dateFrom > dateTo);

  return (
    <Box sx={{ p: { xs: 0.5, sm: 1.5, md: 3 } }}>
      {/* Header */}
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        sx={{ justifyContent: "space-between", alignItems: { xs: "flex-start", sm: "center" }, mb: 3 }}
      >
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
        onSubmit={async (...args) => { const id = await handleCheckIn(...args); if (id) setTicketId(id); }}
        submitting={submitting}
      />

      <Stack component="form" onSubmit={resolveScan} direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 3 }}>
        <TextField fullWidth size="small" label="Quét hoặc dán mã vé QR" helperText={scanError || "Dùng máy quét mã như bàn phím, hoặc dán nội dung QR rồi tra vé."} error={Boolean(scanError)} value={scan} onChange={event => setScan(event.target.value)} slotProps={{ htmlInput: { maxLength: 128 } }} />
        <Button type="submit" variant="outlined" disabled={scanning || !scan.trim()} sx={{ whiteSpace: "nowrap", alignSelf: "flex-start" }}>Tra vé</Button>
      </Stack>
      <TicketDialog sessionId={ticketId} onClose={() => setTicketId(null)} onCheckOut={handleCheckOut} />

      {/* Bộ lọc lịch sử gửi xe */}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
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
          <MenuItem value="cancelled">Đã hủy</MenuItem>
          <MenuItem value="">Tất cả</MenuItem>
        </TextField>
        <TextField
          size="small"
          label="Tìm theo biển số"
          value={searchPlate}
          onChange={(e) => setSearchPlate(e.target.value)}
          sx={{ minWidth: 220 }}
        />
        <TextField
          size="small"
          type="date"
          label="Từ ngày"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          error={invalidDateRange}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ minWidth: 165 }}
        />
        <TextField
          size="small"
          type="date"
          label="Đến ngày"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          error={invalidDateRange}
          helperText={invalidDateRange ? "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc" : ""}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ minWidth: 165 }}
        />
      </Stack>

      {/* Table lịch sử/danh sách phiên gửi xe */}
      <SessionTable
        sessions={sessions}
        total={total}
        loading={loading}
        page={page}
        pageSize={pageSize}
        onPaginationModelChange={handlePaginationModelChange}
        onCheckOut={handleCheckOut}
        onTicket={setTicketId}
        title={
          statusFilter === "active"
            ? "Danh sách xe đang đỗ trong bãi"
            : statusFilter === "completed"
              ? "Lịch sử xe đã rời bãi"
              : statusFilter === "cancelled"
                ? "Danh sách phiên đã hủy"
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
