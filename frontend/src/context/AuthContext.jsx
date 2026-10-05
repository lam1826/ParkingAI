import { createContext, useCallback, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import authService from "../services/authService";
import { clearAIChat } from "../utils/aiChatStorage";
import { getErrorMessage } from "../utils/errorMessage";
import { createAuthSessionBoundary, loginFailureLogDetails, loginWithSession } from "../services/authSessionBoundary";
import { postLoginDestination } from "../pages/Login/loginDestination";
import { bindPendingRefundsAccount } from "../pages/Expansion/siteFinanceRefund";

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionVersion, setSessionVersion] = useState(0);
  // Kept outside the keyed subtree: survive the remount caused by a session reset.
  const [profileError, setProfileError] = useState(null);
  const [loginFailure, setLoginFailure] = useState(null);
  const navigate = useNavigate();
  const [session] = useState(() => createAuthSessionBoundary({
    storage: localStorage,
    eventTarget: window,
    fetchProfile: authService.getProfile,
    onReset: () => {
      clearAIChat();
      // Unconfirmed Site Finance refunds belong to the account that sent them (#24, round 3).
      bindPendingRefundsAccount(null);
      setUser(null);
      setSessionVersion((version) => version + 1);
    },
    onUser: (profile) => {
      // Another account signing in on this tab drops the previous account's refund drafts.
      bindPendingRefundsAccount(profile?.id ?? null);
      setUser(profile);
    },
    onLoading: setLoading,
    onProfileError: setProfileError,
  }));
  const refreshUser = useCallback(() => session.refresh(), [session]);

  useEffect(() => {
    void session.start();
    return () => session.stop();
  }, [session]);

  const clearLoginFailure = useCallback(() => setLoginFailure(null), []);

  const login = async (credentials, next = null) => {
    setLoginFailure(null);
    const result = await loginWithSession({
      session,
      storage: localStorage,
      authenticate: authService.login,
      credentials,
      // A failure after the token was issued already remounted the login page;
      // the provider keeps message + username for the new page (see LoginPage).
      onFailure: setLoginFailure,
      describeError: (error, { afterToken }) => {
        // Axios timeouts/network drops carry a request but no response.
        const message = !error?.response && error?.request
          ? "Chưa kết nối được hệ thống. Vui lòng thử lại."
          : getErrorMessage(error, "Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin!");
        return afterToken ? `Đăng nhập chưa hoàn tất vì chưa tải được thông tin tài khoản: ${message}` : message;
      },
    });
    if (!result.success) {
      // Status/code only: the error's request config holds the password or the issued token.
      console.error("Login failed:", loginFailureLogDetails(result.error));
      return { success: false, message: result.message };
    }
    // A validated same-origin continuation the role can use (e.g. a customer buying a
    // ticket from the public page) wins over the role default; internal roles never
    // land on the customer-only portal.
    navigate(postLoginDestination(next, result.profile.role), { replace: true });
    return { success: true };
  };

  const logout = () => {
    setLoginFailure(null);
    session.end();
    navigate("/login");
  };

  const changePassword = async (passwords) => {
    const requestToken = localStorage.getItem("token");
    const result = await authService.changePassword(passwords);
    if (session.end(requestToken)) {
      navigate("/login", { replace: true, state: {
        message: result.message || "Đổi mật khẩu thành công. Vui lòng đăng nhập lại.",
      } });
    }
    return result;
  };

  if (loading) {
    return <div>Đang tải hệ thống...</div>; // Bạn có thể thay bằng Spinner của MUI
  }

  return (
    <AuthContext.Provider key={sessionVersion} value={{ user, login, logout, refreshUser, changePassword, profileError, loginFailure, clearLoginFailure }}>
      {children}
    </AuthContext.Provider>
  );
};
