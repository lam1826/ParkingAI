import { Paper, Typography, Box } from "@mui/material";

export default function SummaryCard({ title, value, icon, color = "primary.main" }) {
  return (
    <Paper sx={{ p: 3, display: "flex", alignItems: "center", justifyContent: "space-between", height: "100%" }}>
      <Box>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          {title}
        </Typography>
        <Typography variant="h5" fontWeight="bold">
          {value}
        </Typography>
      </Box>
      <Box sx={{ color: color, display: "flex", alignItems: "center", fontSize: 40 }}>
        {icon}
      </Box>
    </Paper>
  );
}