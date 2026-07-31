import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Skeleton,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";

const AIInsightCard = ({ loading, insight }) => {
  return (
    <Card
      sx={{
        height: "100%",
        borderRadius: 3,
        boxShadow: 3,
        transition: "0.3s",
        "&:hover": {
          transform: "translateY(-3px)",
          boxShadow: 6,
        },
      }}
    >
      <CardContent sx={{ height: "100%" }}>
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          mb={2}
        >
          <Box display="flex" alignItems="center" gap={1}>
            <AutoAwesomeIcon color="secondary" />
            <Typography
              variant="h6"
              fontWeight={700}
            >
              AI Insight
            </Typography>
          </Box>

          <Chip
            label="Gemini AI"
            size="small"
            color="secondary"
            variant="outlined"
          />
        </Box>

        {loading ? (
          <>
            <Skeleton height={28} />
            <Skeleton height={28} />
            <Skeleton width="80%" height={28} />
            <Skeleton width="70%" height={28} />
          </>
        ) : (
          <Typography
            variant="body1"
            color="text.secondary"
            sx={{
              mt: 2,
              lineHeight: 1.8,
              textAlign: "justify",
              whiteSpace: "pre-line",
            }}
          >
            {insight?.insight ??
              "Chưa có dữ liệu AI để phân tích."}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default AIInsightCard;