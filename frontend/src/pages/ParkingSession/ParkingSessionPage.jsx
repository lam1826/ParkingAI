import { Box, Typography, Button, Stack, Snackbar, Alert } from "@mui/material";
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
        onSubmit={handleCheckIn}
        submitting={submitting}
      />

      {/* Table danh sách xe đang đỗ */}
      <SessionTable
        sessions={sessions}
        loading={loading}
        onCheckOut={handleCheckOut}
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