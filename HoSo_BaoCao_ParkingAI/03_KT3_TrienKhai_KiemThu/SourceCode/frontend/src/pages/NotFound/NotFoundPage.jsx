import { Box, Typography, Button } from "@mui/material";
import { useNavigate } from "react-router-dom";

export default function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <Typography variant="h1" fontWeight="bold" color="primary">404</Typography>
      <Typography variant="h6" sx={{ mb: 3 }}>Trang bạn tìm kiếm không tồn tại.</Typography>
      <Button variant="contained" onClick={() => navigate('/')}>
        Về trang chủ
      </Button>
    </Box>
  );
}