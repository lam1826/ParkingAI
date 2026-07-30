import React, { useState, useEffect } from "react";
import { 
  Box, Grid, Typography, Snackbar, Alert, Card, CardContent,
  Skeleton, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip
} from "@mui/material";
import dashboardService from "../services/dashboardService";
import SummaryCard from "./Dashboard/components/SummaryCard";

const Dashboard = () => {
  // State cho dữ liệu chính
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // State tách biệt cho AI
  const [aiData, setAiData] = useState(null);
  const [aiLoading, setAiLoading] = useState(true);
  
  const [error, setError] = useState({ open: false, message: "" });

  // Gọi dữ liệu Dashboard chính
  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        const response = await dashboardService.getSummary();
        setData(response);
      } catch (err) {
        setError({
          open: true,
          message: err.response?.data?.detail || "Lỗi khi tải dữ liệu tổng quan.",
        });
      } finally {
        setLoading(false);
      }
    };
    fetchDashboardData();
  }, []);

  // Gọi dữ liệu AI độc lập
  useEffect(() => {
    const fetchAIInsight = async () => {
      try {
        setAiLoading(true);
        const response = await dashboardService.getAIInsight();
        setAiData(response);
      } catch (err) {
        console.error("AI Insight Error:", err);
        // Không quăng lỗi ra Snackbar để tránh spam UI, chỉ hiển thị fallback text ở Card
        setAiData({ insight: "Không thể kết nối đến máy chủ AI lúc này." });
      } finally {
        setAiLoading(false);
      }
    };
    fetchAIInsight();
  }, []);

  const handleCloseError = (event, reason) => {
    if (reason === 'clickaway') return;
    setError({ ...error, open: false });
  };

  return (
    <Box sx={{ flexGrow: 1, p: 3 }}>
      <Typography variant="h4" fontWeight="bold" gutterBottom sx={{ mb: 4 }}>
        Tổng quan hệ thống
      </Typography>

      <Grid container spacing={3}>
        {/* Hàng 1: 4 Summary Cards (Giữ nguyên) */}
        <Grid  xs={12} sm={6} md={3}>
          <SummaryCard title="Doanh thu hôm nay" value={data?.total_revenue_today?.toLocaleString()} unit="VNĐ" loading={loading} />
        </Grid>
        <Grid  xs={12} sm={6} md={3}>
          <SummaryCard title="Lượt xe hôm nay" value={data?.total_vehicles_today} unit="Xe" loading={loading} />
        </Grid>
        <Grid  xs={12} sm={6} md={3}>
          <SummaryCard title="Xe đang trong bãi" value={data?.vehicles_currently_inside} unit="Xe" loading={loading} />
        </Grid>
        <Grid  xs={12} sm={6} md={3}>
          <SummaryCard title="Tỷ lệ lấp đầy" value={data?.occupancy_rate_percentage} unit="%" loading={loading} />
        </Grid>

        {/* Hàng 2 */}
        <Grid  xs={12} md={6}>
          <Card sx={{ height: "100%", boxShadow: 3, display: 'flex', flexDirection: 'column' }}>
            <CardContent sx={{ flexGrow: 1 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6" color="secondary" fontWeight="bold">
                  ✨ AI Insight
                </Typography>
                <Chip label="Powered by Gemini" size="small" color="secondary" variant="outlined" />
              </Box>
              
              {/* Sử dụng state aiLoading riêng */}
              {aiLoading ? (
                <Box sx={{ mt: 2 }}>
                  <Skeleton variant="text" width="100%" height={30} />
                  <Skeleton variant="text" width="100%" height={30} />
                  <Skeleton variant="text" width="80%" height={30} />
                </Box>
              ) : (
                <Typography variant="body1" sx={{ mt: 2, fontStyle: 'italic', color: 'text.secondary', lineHeight: 1.6 }}>
                  {aiData?.insight}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid  xs={12} md={6}>
          <Card sx={{ height: "100%", boxShadow: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom fontWeight="bold">
                Top 5 khung giờ cao điểm
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" width="100%" height={200} sx={{ mt: 2, borderRadius: 1 }} />
              ) : (
                <TableContainer sx={{ mt: 1 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell><strong>Khung giờ</strong></TableCell>
                        <TableCell align="right"><strong>Lượng xe check-in</strong></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {data?.top_peak_hours && data.top_peak_hours.length > 0 ? (
                        data.top_peak_hours.map((row, index) => (
                          <TableRow key={index} hover>
                            <TableCell>{row.hour}</TableCell>
                            <TableCell align="right">
                              <Chip label={row.count} size="small" color="primary" />
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={2} align="center">Chưa có dữ liệu giao dịch trong ngày</TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Snackbar open={error.open} autoHideDuration={6000} onClose={handleCloseError} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
        <Alert onClose={handleCloseError} severity="error" variant="filled" sx={{ width: '100%' }}>
          {error.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default Dashboard;