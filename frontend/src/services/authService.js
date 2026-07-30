import api from "./api";

/**
 * Đăng nhập
 * @param {string} username
 * @param {string} password
 * @returns {Promise<Object>}
 */
const login = async (username, password) => {
  const formData = new URLSearchParams();

  formData.append("username", username);
  formData.append("password", password);
  formData.append("grant_type", "password");

  try {
    const response = await api.post("/auth/login", formData, {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
    });

    console.log("Login Response:", response.data);

    if (response.data?.access_token) {
      localStorage.setItem(
        "access_token",
        response.data.access_token
      );

      console.log(
        "Token saved:",
        localStorage.getItem("access_token")
      );
    } else {
      throw new Error("Không nhận được access_token từ server.");
    }

    return response.data;
  } catch (error) {
    console.error("Login Error:", error.response?.data || error.message);
    throw error;
  }
};

/**
 * Đăng xuất
 */
const logout = async () => {
  try {
    await api.post("/auth/logout");
  } catch (error) {
    console.warn("Logout Error:", error.response?.data || error.message);
  } finally {
    localStorage.removeItem("access_token");
  }
};

/**
 * Lấy thông tin người dùng hiện tại
 */
const getCurrentUser = async () => {
  const response = await api.get("/auth/me");
  return response.data;
};

export default {
  login,
  logout,
  getCurrentUser,
};