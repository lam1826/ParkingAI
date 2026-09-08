import { createContext, useCallback, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import authService from "../services/authService";
import { clearAIChat } from "../utils/aiChatStorage";
import { getErrorMessage } from "../utils/errorMessage";
import { createAuthSessionBoundary } from "../services/authSessionBoundary";

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionVersion, setSessionVersion] = useState(0);
  const navigate = useNavigate();
  const [session] = useState(() => createAuthSessionBoundary({
    storage: localStorage,
    eventTarget: window,
    fetchProfile: authService.getProfile,
    onReset: () => {
      clearAIChat();
      setUser(null);
      setSessionVersion((version) => version + 1);
    },
    onUser: setUser,
    onLoading: setLoading,
  }));
  const refreshUser = useCallback(() => session.refresh(), [session]);

  useEffect(() => {
    void session.start();
    return () => session.stop();
  }, [session]);

  const login = async (credentials) => {
    const isCurrentAttempt = session.beginLogin();
    let issuedToken = null;
    try {
      const data = await authService.login(credentials);
      if (!isCurrentAttempt()) {
        throw new Error("Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.");
      }

      // Backend trả về { access_token, token_type }
      const token = data.access_token;
      issuedToken = token;
      // Lưu token trước để interceptor của axios đính kèm Authorization
      localStorage.setItem("token", token);

      // Lấy thông tin user hiện tại từ /api/auth/me
      const userData = await refreshUser();
      
      navigate(userData.role === "customer" ? "/portal" : "/");
      return { success: true };
    } catch (error) {
      if (issuedToken && localStorage.getItem("token") === issuedToken) {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        await session.refresh();
      }
      console.error("Login failed:", error);
      return { 
        success: false, 
        message: getErrorMessage(error, "Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin!")
      };
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    void session.refresh().catch(() => {});
    navigate("/login");
  };

  if (loading) {
    return <div>Đang tải hệ thống...</div>; // Bạn có thể thay bằng Spinner của MUI
  }

  return (
    <AuthContext.Provider key={sessionVersion} value={{ user, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};
