import {
  Box,
  Typography,
  Button,
  Stack,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { formatBusinessLongDate } from "../../../utils/businessDate";

const DashboardHeader = ({ onRefresh, loading }) => {
  // Ngày nghiệp vụ theo Asia/Ho_Chi_Minh, không theo timezone máy người dùng.
  const today = formatBusinessLongDate();

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