import { Component } from "react";
import { Alert, AlertTitle, Box, Button, Stack } from "@mui/material";

/**
 * ErrorBoundary tối giản: chặn lỗi render của cây con để một trang lỗi
 * không làm trắng toàn bộ ứng dụng.
 *
 * - Dùng ở cấp root (main.jsx) làm lưới an toàn cuối cùng.
 * - Dùng quanh <Outlet/> trong MainLayout (kèm key theo pathname để tự reset
 *   khi điều hướng sang trang khác) — lỗi một trang vẫn giữ Header/Sidebar.
 *
 * Lỗi được log ra console phục vụ debug; không hiển thị stack trace cho người dùng.
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // Không nuốt lỗi âm thầm — giữ log đầy đủ cho dev
    console.error("ErrorBoundary bắt được lỗi render:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <Box sx={{ p: 3, display: "flex", justifyContent: "center" }}>
        <Alert severity="error" sx={{ maxWidth: 560, width: "100%" }}>
          <AlertTitle>Đã xảy ra lỗi hiển thị</AlertTitle>
          Rất tiếc, phần nội dung này gặp sự cố khi hiển thị. Bạn có thể thử lại
          hoặc quay về trang Dashboard. Nếu lỗi lặp lại, vui lòng báo cho quản trị viên.
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button variant="contained" size="small" onClick={this.handleRetry}>
              Thử lại
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => { window.location.href = "/"; }}
            >
              Về Dashboard
            </Button>
          </Stack>
        </Alert>
      </Box>
    );
  }
}

export default ErrorBoundary;
