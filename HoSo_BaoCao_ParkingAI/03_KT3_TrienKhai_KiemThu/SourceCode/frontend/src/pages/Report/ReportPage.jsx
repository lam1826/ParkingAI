import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Grid, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { reportService } from "./services/reportService";
import { loadPeriodReport } from "./services/loadPeriodReport";
import { extractReportDownloadErrorMessage } from "./services/reportDownloadError";
import { createLatestRequestGate } from "../../utils/latestRequestGate";

export default function ReportPage() {
  const reportRequestGate = useRef(null);
  if (reportRequestGate.current === null) {
    reportRequestGate.current = createLatestRequestGate();
  }

  const [period, setPeriod] = useState("week");
  const [revenue, setRevenue] = useState(null);
  const [traffic, setTraffic] = useState([]);
  const [reportAnchor, setReportAnchor] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState("");
  useEffect(() => {
    const requestGate = reportRequestGate.current;
    const requestGeneration = requestGate.begin();
    setLoading(true);
    setError("");
    setRevenue(null);
    setTraffic([]);
    setReportAnchor("");
    loadPeriodReport(reportService, period)
      .then(({ revenue: revenueData, traffic: trafficData, anchorDate }) => {
        if (!requestGate.isCurrent(requestGeneration)) return;
        setRevenue(revenueData);
        setTraffic(trafficData.traffic_by_hour || []);
        setReportAnchor(anchorDate);
      })
      .catch((requestError) => {
        if (!requestGate.isCurrent(requestGeneration)) return;
        setError(requestError.response?.data?.detail || "Không thể tải báo cáo.");
      })
      .finally(() => {
        if (requestGate.isCurrent(requestGeneration)) setLoading(false);
      });
    return () => requestGate.invalidate();
  }, [period]);

  const exportReport = async (format) => {
    setExporting(format);
    setError("");
    try {
      const response = await reportService.downloadReport(format, period, reportAnchor);
      const disposition = response.headers["content-disposition"] || "";
      const filename = disposition.match(/filename="?([^";]+)"?/)?.[1]
        || `parking-report-${period}-${reportAnchor}.${format}`;
      const url = window.URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(await extractReportDownloadErrorMessage(
        requestError,
        `Không thể xuất báo cáo ${format.toUpperCase()}.`,
      ));
    } finally {
      setExporting("");
    }
  };
  if (loading) return <CircularProgress />;
  return <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <Typography variant="h5" fontWeight="bold">Báo cáo lưu lượng và doanh thu</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField select size="small" label="Kỳ báo cáo" value={period} onChange={(event) => {
          setReportAnchor("");
          setPeriod(event.target.value);
        }} sx={{ width: 160 }}>
          <MenuItem value="day">Hôm nay</MenuItem><MenuItem value="week">Tuần này</MenuItem>
          <MenuItem value="month">Tháng này</MenuItem><MenuItem value="year">Năm nay</MenuItem>
        </TextField>
        <Button variant="outlined" startIcon={exporting === "xlsx" ? <CircularProgress size={16} /> : <DownloadIcon />} disabled={Boolean(exporting) || !reportAnchor} onClick={() => exportReport("xlsx")}>Excel</Button>
        <Button variant="outlined" startIcon={exporting === "pdf" ? <CircularProgress size={16} /> : <DownloadIcon />} disabled={Boolean(exporting) || !reportAnchor} onClick={() => exportReport("pdf")}>PDF</Button>
      </Stack>
    </Box>
    {error && <Alert severity="error">{error}</Alert>}
    {revenue && <Grid container spacing={2}>
      {[['Tổng lượt xe', revenue.total_trips], ['Doanh thu', `${Number(revenue.total_revenue).toLocaleString('vi-VN')} ₫`],
        ['Phí trung bình', `${Number(revenue.average_fee).toLocaleString('vi-VN')} ₫`], ['Loại xe phổ biến', revenue.most_frequent_vehicle_type]].map(([label, value]) =>
        <Grid key={label} size={{ xs: 12, sm: 6, lg: 3 }}><Paper sx={{ p: 2 }}><Typography color="text.secondary">{label}</Typography><Typography variant="h6">{value}</Typography></Paper></Grid>)}
    </Grid>}
    <Paper sx={{ p: 3, height: 420 }}><Typography variant="h6" gutterBottom>Lưu lượng theo giờ</Typography>
      <ResponsiveContainer width="100%" height="90%"><BarChart data={traffic}><CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="time_label" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="total_vehicles" name="Lượt xe" fill="#1976d2" /></BarChart></ResponsiveContainer>
    </Paper>
  </Box>;
}
