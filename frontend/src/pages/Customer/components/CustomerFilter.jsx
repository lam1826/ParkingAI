import { useState } from "react";
import { Card, CardContent, Grid, TextField, Button, Box } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import RestartAltIcon from "@mui/icons-material/RestartAlt";

const CustomerFilter = ({ filters, onSearch, onReset }) => {
  const [keyword, setKeyword] = useState(filters.keyword || "");

  const handleSubmit = (e) => {
    e.preventDefault();
    onSearch({ keyword });
  };

  const handleReset = () => {
    setKeyword("");
    onReset();
  };

  return (
    <Card elevation={0} sx={{ border: "1px solid #e0e0e0", mb: 3 }}>
      <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
        <Box component="form" onSubmit={handleSubmit}>
          <Grid container spacing={2} sx={{ alignItems: "center" }}>
            <Grid size={{ xs: 12, sm: 8, md: 6 }}>
              <TextField
                fullWidth
                size="small"
                label="Tìm kiếm khách hàng"
                placeholder="Nhập tên, số điện thoại hoặc email..."
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4, md: 6 }}>
              <Box display="flex" gap={1}>
                <Button
                  type="submit"
                  variant="contained"
                  startIcon={<SearchIcon />}
                >
                  Tìm kiếm
                </Button>
                <Button
                  variant="outlined"
                  color="inherit"
                  startIcon={<RestartAltIcon />}
                  onClick={handleReset}
                >
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

export default CustomerFilter;