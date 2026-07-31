import { createContext, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import authService from "../services/authService";

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // Kiểm tra token khi khởi chạy app
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem("token");
      const storedUser = localStorage.getItem("user");

      if (token && storedUser) {
        setUser(JSON.parse(storedUser));
        // Tùy chọn: Gọi API getProfile() ở đây để cập nhật dữ liệu user mới nhất
      }
      setLoading(false);
    };
    checkAuth();
  }, []);

  const login = async (credentials) => {
    try {
      const data = await authService.login(credentials);

      // Backend trả về { access_token, token_type }
      const token = data.access_token;

      // Lưu token trước để interceptor của axios đính kèm Authorization
      localStorage.setItem("token", token);

      // Lấy thông tin user hiện tại từ /api/auth/me
      const userData = await authService.getProfile();

      localStorage.setItem("user", JSON.stringify(userData));

      // Cập nhật state
      setUser(userData);
      
      // Chuyển hướng vào trang chính (Dashboard)
      navigate("/");
      return { success: true };
    } catch (error) {
      console.error("Login failed:", error);
      return { 
        success: false, 
        message: error.response?.data?.detail || "Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin!" 
      };
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setUser(null);
    navigate("/login");
  };

  if (loading) {
    return <div>Đang tải hệ thống...</div>; // Bạn có thể thay bằng Spinner của MUI
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};