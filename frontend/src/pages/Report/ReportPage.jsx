import { Box, Typography, Paper, Grid } from "@mui/material";

export default function ReportPage() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Typography variant="h5" fontWeight="bold">Báo cáo & Thống kê Doanh thu</Typography>
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper sx={{ p: 3, height: 350 }}>
            <Typography variant="h6" gutterBottom>Biểu đồ doanh thu theo tuần</Typography>
            {/* Tích hợp Recharts hoặc bảng dữ liệu ở đây */}
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper sx={{ p: 3, height: 350 }}>
            <Typography variant="h6" gutterBottom>Thống kê lượt xe ra vào</Typography>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}