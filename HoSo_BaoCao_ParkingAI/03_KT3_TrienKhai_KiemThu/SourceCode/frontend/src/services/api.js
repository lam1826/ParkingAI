import axios from "axios";

// Khởi tạo instance của axios
const api = axios.create({
  // Sử dụng biến môi trường của Vite, nếu không có thì fallback về localhost
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  timeout: 10000, // Timeout 10s
  headers: {
    "Content-Type": "application/json",
  },
});

// 1. REQUEST INTERCEPTOR: Tự động đính kèm Token
api.interceptors.request.use(
  (config) => {
    // Lấy token từ localStorage (hoặc sessionStorage/cookies tùy bạn lưu)
    const token = localStorage.getItem("token");
    
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 2. RESPONSE INTERCEPTOR: Xử lý lỗi toàn cục
api.interceptors.response.use(
  (response) => {
    // Nếu request thành công, trả về response bình thường
    return response;
  },
  (error) => {
    if (error.response) {
      const { status } = error.response;

      switch (status) {
        case 401:
          // Lỗi 401 Unauthorized: Token hết hạn hoặc không hợp lệ
          console.warn("Phiên đăng nhập hết hạn. Đang đăng xuất...");
          
          // Xóa thông tin auth
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          
          // Chuyển hướng về trang Login. 
          // (Dùng window.location vì useNavigate không hoạt động ngoài React Components)
          if (window.location.pathname !== "/login") {
            window.location.href = "/login";
          }
          break;

        case 403:
          // Lỗi 403 Forbidden: Đã đăng nhập nhưng không có quyền truy cập resource này
          console.error("Lỗi phân quyền: Bạn không có quyền thao tác!");
          break;

        case 404:
          console.error("Không tìm thấy tài nguyên (404)!");
          break;

        case 500:
          console.error("Lỗi máy chủ nội bộ (500)!");
          break;
          
        default:
          break;
      }
    } else if (error.request) {
      // Lỗi Network (Server sập, mất mạng...)
      console.error("Lỗi kết nối mạng. Không thể liên lạc với máy chủ.");
    }

    // Ném lỗi tiếp để Catch block bên trong các component (như hook useUser) có thể bắt được và show Snackbar
    return Promise.reject(error);
  }
);

export default api;