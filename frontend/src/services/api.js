import axios from "axios";
import { resolveApiBaseUrl } from "../utils/apiBaseUrl";
import { clearAIChat } from "../utils/aiChatStorage";
import { isCurrentAuthFailure, notifyAuthSessionChanged } from "./authSessionBoundary";
import { shouldAttachAuthorization } from "./credentialRequestPolicy";

// Khởi tạo instance của axios
const api = axios.create({
  // Runtime config keeps the hashed application artifact identical between
  // staging and production. The CDN deployment only replaces config.js.
  baseURL: resolveApiBaseUrl({
    runtimeUrl: globalThis.__PARKINGAI_CONFIG__?.API_URL,
    buildUrl: import.meta.env.VITE_API_URL,
    isDevelopment: import.meta.env.DEV,
    locationOrigin: globalThis.location?.origin,
  }),
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
    
    if (token && shouldAttachAuthorization(config.url)) {
      config.headers.Authorization = `Bearer ${token}`;
    } else if (!shouldAttachAuthorization(config.url)) {
      delete config.headers.Authorization;
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
          // A late failure from a previous login must not sign out the next user.
          if (!isCurrentAuthFailure(error.config?.headers?.Authorization, localStorage.getItem("token"))) break;
          // Lỗi 401 Unauthorized: Token hết hạn hoặc không hợp lệ
          console.warn("Phiên đăng nhập hết hạn. Đang đăng xuất...");
          
          // Xóa thông tin auth
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          clearAIChat();
          notifyAuthSessionChanged();
          
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
