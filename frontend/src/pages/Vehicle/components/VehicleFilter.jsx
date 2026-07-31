import { useState } from "react";
import { Card, CardContent, Grid, TextField, MenuItem, Button, Box } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import RestartAltIcon from "@mui/icons-material/RestartAlt";

const VehicleFilter = ({ filters, onSearch, onReset }) => {
  const [form, setForm] = useState(filters);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSearch(form);
  };

  const handleReset = () => {
    onReset();
  };

  return (
    <Card elevation={0} sx={{ border: "1px solid #e0e0e0", mb: 3 }}>
      <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
        <Box component="form" onSubmit={handleSubmit}>
          <Grid container spacing={2} sx={{ alignItems: "center" }}>
            <Grid size={{ xs: 12, sm: 4, md: 4 }}>
              <TextField
                fullWidth
                size="small"
                label="Biển số xe"
                name="licensePlate"
                placeholder="VD: 30A-12345"
                value={form.licensePlate}
                onChange={handleChange}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4, md: 3 }}>
              <TextField
                fullWidth
                select
                size="small"
                label="Loại xe"
                name="vehicleType"
                value={form.vehicleType}
                onChange={handleChange}
              >
                <MenuItem value="ALL">Tất cả</MenuItem>
                <MenuItem value="CAR">Ô tô</MenuItem>
                <MenuItem value="MOTORBIKE">Xe máy</MenuItem>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 4, md: 5 }}>
              <Box display="flex" gap={1}>
                <Button type="submit" variant="contained" startIcon={<SearchIcon />}>
                  Tìm kiếm
                </Button>
                <Button variant="outlined" color="inherit" onClick={handleReset} startIcon={<RestartAltIcon />}>
                  Đặt lại
                </Button>
              </Box>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </Card>
  );
};

export default VehicleFilter;