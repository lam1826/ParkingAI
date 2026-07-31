import { useState } from "react";
import { Box, Typography, Paper, TextField, Button, Stack } from "@mui/material";

export default function SettingPage() {
  const [settings, setSettings] = useState({
    parkingName: "ParkingAI Central Hub",
    gracePeriodMinutes: 15,
    autoCheckout: true,
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setSettings(prev => ({ ...prev, [name]: value }));
  };

  const handleSave = () => {
    // Gọi API lưu cấu hình
    alert("Đã lưu cấu hình hệ thống thành công!");
  };

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Typography variant="h5" fontWeight="bold">Cài đặt Hệ thống</Typography>
      <Paper sx={{ p: 4, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <TextField 
          label="Tên bãi đỗ xe" 
          name="parkingName"
          value={settings.parkingName} 
          onChange={handleChange}
          fullWidth 
        />
        <TextField 
          label="Thời gian ân hạn miễn phí (phút)" 
          name="gracePeriodMinutes"
          type="number"
          value={settings.gracePeriodMinutes} 
          onChange={handleChange}
          fullWidth 
        />
        <Stack direction="row" sx={{ justifyContent: "flex-end" }}>
          <Button variant="contained" size="large" onClick={handleSave}>
            Lưu thay đổi
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
}