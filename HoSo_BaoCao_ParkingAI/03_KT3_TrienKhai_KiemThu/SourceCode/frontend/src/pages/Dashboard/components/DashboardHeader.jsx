import {
  Box,
  Typography,
  Button,
  Stack,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

const DashboardHeader = ({ onRefresh, loading }) => {
  const today = new Date().toLocaleDateString("vi-VN", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  return (
    <Box
      sx={{
        mb: 4,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 2,
      }}
    >
      <Box>
        <Typography
          variant="h4"
          fontWeight={700}
        >
          ParkingAI Dashboard
        </Typography>

        <Typography
          variant="body2"
          color="text.secondary"
        >
          {today}
        </Typography>
      </Box>

      <Stack direction="row" spacing={2}>
        <Button
          variant="contained"
          startIcon={<RefreshIcon />}
          onClick={onRefresh}
          disabled={loading}
        >
          Làm mới
        </Button>
      </Stack>
    </Box>
  );
};

export default DashboardHeader;