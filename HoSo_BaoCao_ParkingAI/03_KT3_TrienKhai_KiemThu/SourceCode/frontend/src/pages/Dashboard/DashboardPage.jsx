// File: src/pages/Dashboard/Dashboard.jsx
import {
  Box,
  Grid,
  Snackbar,
  Alert,
} from "@mui/material";

import DashboardHeader from "./components/DashboardHeader";
import SummarySection from "./components/SummarySection";
import AIInsightCard from "./components/AIInsightCard";
import PeakHourCard from "./components/PeakHourCard";
import RevenueChart from "./components/RevenueChart";
import TrafficChart from "./components/TrafficChart";
import RecentSessionsTable from "./components/RecentSessionsTable";
import useDashboard from "./hooks/useDashboard";

const Dashboard = () => {
  const {
    data,
    aiData,
    recentSessions,
    revenueData,     // Lấy dữ liệu biểu đồ từ API
    trafficData,     // Lấy dữ liệu biểu đồ từ API
    loading,
    aiLoading,
    sessionsLoading,
    chartsLoading,   // Trạng thái loading biểu đồ
    error,
    closeError,
    refreshDashboard,
  } = useDashboard();

  const handleCloseError = (_, reason) => {
    if (reason === "clickaway") return;
    closeError();
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <DashboardHeader
        loading={loading}
        onRefresh={refreshDashboard}
      />

      {/* Summary */}
      <SummarySection
        data={data}
        loading={loading}
      />

      {/* Charts */}
      <Grid
        container
        spacing={3}
        sx={{ mt: 1 }}
      >
        <Grid size={{ xs: 12, lg: 6 }}>
          <RevenueChart
            data={revenueData}
            loading={chartsLoading}
          />
        </Grid>

        <Grid size={{ xs: 12, lg: 6 }}>
          <TrafficChart
            data={trafficData}
            loading={chartsLoading}
          />
        </Grid>
      </Grid>

      {/* AI + Peak Hour */}
      <Grid
        container
        spacing={3}
        sx={{ mt: 1 }}
      >
        <Grid size={{ xs: 12, lg: 6 }}>
          <AIInsightCard
            loading={aiLoading}
            insight={aiData}
          />
        </Grid>

        <Grid size={{ xs: 12, lg: 6 }}>
          <PeakHourCard
            loading={loading}
            data={data?.top_peak_hours ?? []}
          />
        </Grid>
      </Grid>

      {/* Recent Sessions Table */}
      <Box sx={{ mt: 3 }}>
        <RecentSessionsTable 
          data={recentSessions} 
          loading={sessionsLoading} 
        />
      </Box>

      {/* Error */}
      <Snackbar
        open={error.open}
        autoHideDuration={6000}
        onClose={handleCloseError}
        anchorOrigin={{
          vertical: "bottom",
          horizontal: "right",
        }}
      >
        <Alert
          severity="error"
          variant="filled"
          onClose={handleCloseError}
          sx={{ width: "100%" }}
        >
          {error.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default Dashboard;