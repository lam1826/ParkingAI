import { Container, Typography } from "@mui/material";

export default function MonthlyPassPage() {
  return (
    <Container maxWidth="xl" sx={{ mt: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Quản lý Vé tháng
      </Typography>
    </Container>
  );
}