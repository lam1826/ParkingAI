import { Container, Typography } from "@mui/material";

export default function CustomerPage() {
  return (
    <Container maxWidth="xl" sx={{ mt: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Quản lý Khách hàng
      </Typography>
    </Container>
  );
}