import { useState } from "react";
import {
  Card,
  CardContent,
  Grid,
  TextField,
  MenuItem,
  Button,
  Box,
  Stack,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import RestartAltIcon from "@mui/icons-material/RestartAlt";

const SessionFilter = ({ filters, onSearch, onReset }) => {
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
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <TextField
                fullWidth
                size="small"
                label="Biển số xe"
                name="plateNumber"
                placeholder="Ví dụ: 30A-12345"
                value={form.plateNumber}
                onChange={handleChange}
              />
            </Grid>

            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <TextField
                fullWidth
                select
                size="small"
                label="Trạng thái"
                name="status"
                value={form.status}
                onChange={handleChange}
              >
                <MenuItem value="ALL">Tất cả trạng thái</MenuItem>
                <MenuItem value="PARKING">Đang đỗ trong bãi</MenuItem>
                <MenuItem value="COMPLETED">Đã ra bãi</MenuItem>
              </TextField>
            </Grid>

            <Grid size={{ xs: 12, sm: 6, md: 2.5 }}>
              <TextField
                fullWidth
                size="small"
                type="date"
                label="Từ ngày"
                name="startDate"
                InputLabelProps={{ shrink: true }}
                value={form.startDate}
                onChange={handleChange}
              />
            </Grid>

            <Grid size={{ xs: 12, sm: 6, md: 2.5 }}>
              <TextField
                fullWidth
                size="small"
                type="date"
                label="Đến ngày"
                name="endDate"
                InputLabelProps={{ shrink: true }}
                value={form.endDate}
                onChange={handleChange}
              />
            </Grid>

            <Grid size={{ xs: 12, md: 1 }}>
              <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
                <Button
                  variant="contained"
                  type="submit"
                  sx={{ minWidth: "40px", p: "8px" }}
                >
                  <SearchIcon />
                </Button>
                <Button
                  variant="outlined"
                  color="inherit"
                  onClick={handleReset}
                  sx={{ minWidth: "40px", p: "8px" }}
                >
                  <RestartAltIcon />
                </Button>
              </Stack>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </Card>
  );
};

export default SessionFilter;