import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Grid,
  Typography,
  Box,
  Divider,
  CircularProgress,
  Chip,
} from "@mui/material";
import formatCurrency from "../../../utils/formatCurrency";
import formatDate from "../../../utils/formatDate";

const SessionDetailModal = ({ open, onClose, session, loading }) => {
  if (!session && !loading) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ fontWeight: "bold", borderBottom: "1px solid #eee" }}>
        Chi tiết phiên gửi xe {session?.id ? `#${session.id}` : ""}
      </DialogTitle>

      <DialogContent sx={{ pt: 3 }}>
        {loading ? (
          <Box display="flex" justifyContent="center" py={5}>
            <CircularProgress />
          </Box>
        ) : (
          <Grid container spacing={3}>
            {/* Thông tin thông thường */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="subtitle2" color="textSecondary">
                Biển số xe
              </Typography>
              <Typography variant="h6" color="primary" fontWeight="bold">
                {session?.plateNumber}
              </Typography>

              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" color="textSecondary">
                  Loại xe: <strong>{session?.vehicleType}</strong>
                </Typography>
                <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
                  Vị trí đỗ: <strong>{session?.zoneName}</strong>
                </Typography>
                <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
                  Trạng thái:{" "}
                  <Chip
                    label={session?.status === "PARKING" ? "Đang đỗ" : "Đã ra"}
                    color={session?.status === "PARKING" ? "warning" : "success"}
                    size="small"
                  />
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Typography variant="body2">
                Thời gian vào: <strong>{formatDate(session?.checkInTime)}</strong>
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                Thời gian ra:{" "}
                <strong>
                  {session?.checkOutTime
                    ? formatDate(session.checkOutTime)
                    : "Chưa ra"}
                </strong>
              </Typography>
              <Typography variant="h6" color="error" sx={{ mt: 2 }}>
                Thành tiền: {formatCurrency(session?.totalAmount || 0)} đ
              </Typography>
            </Grid>

            {/* Hình ảnh camera AI chụp */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="subtitle2" gutterBottom>
                Ảnh chụp camera lúc vào:
              </Typography>
              <Box
                component="img"
                src={session?.inImageUrl || "https://via.placeholder.com/300x200?text=Anh+Xe+Vao"}
                alt="Ảnh vào"
                sx={{
                  width: "100%",
                  height: 160,
                  objectFit: "cover",
                  borderRadius: 1,
                  border: "1px solid #ddd",
                }}
              />

              <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
                Ảnh chụp camera lúc ra:
              </Typography>
              <Box
                component="img"
                src={session?.outImageUrl || "https://via.placeholder.com/300x200?text=Anh+Xe+Ra"}
                alt="Ảnh ra"
                sx={{
                  width: "100%",
                  height: 160,
                  objectFit: "cover",
                  borderRadius: 1,
                  border: "1px solid #ddd",
                }}
              />
            </Grid>
          </Grid>
        )}
      </DialogContent>

      <DialogActions sx={{ p: 2, borderTop: "1px solid #eee" }}>
        <Button onClick={onClose} variant="outlined">
          Đóng
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SessionDetailModal;