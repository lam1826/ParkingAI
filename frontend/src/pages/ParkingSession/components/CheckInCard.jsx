import { Card, CardContent, Typography, Box, TextField, Button, CircularProgress } from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";

const CheckInCard = ({ licensePlate, onChangePlate, onSubmit, submitting }) => {
  return (
    <Card elevation={0} sx={{ border: "1px solid #e0e0e0", mb: 3 }}>
      <CardContent>
        <Typography variant="h6" fontWeight="bold" gutterBottom>
          Ghi nhận Xe Vào
        </Typography>
        <Box component="form" onSubmit={onSubmit} sx={{ display: "flex", gap: 2, mt: 2 }}>
          <TextField
            fullWidth
            size="small"
            placeholder="Nhập biển số xe (VD: 30A-12345)"
            value={licensePlate}
            onChange={(e) => onChangePlate(e.target.value)}
            required
            disabled={submitting}
          />
          <Button
            type="submit"
            variant="contained"
            color="success"
            startIcon={submitting ? <CircularProgress size={20} color="inherit" /> : <LoginIcon />}
            disabled={submitting || !licensePlate.trim()}
            sx={{ minWidth: 140, fontWeight: "bold" }}
          >
            Check In
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
};

export default CheckInCard;