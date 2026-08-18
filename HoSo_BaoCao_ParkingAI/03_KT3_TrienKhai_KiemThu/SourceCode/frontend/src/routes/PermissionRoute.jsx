import { useContext } from "react";
import { Alert } from "@mui/material";
import { AuthContext } from "../context/AuthContext";

const levels = { customer: 0, staff: 1, manager: 2, admin: 3 };

export default function PermissionRoute({ children, minimumRole = "staff" }) {
  const { user } = useContext(AuthContext);
  const userLevel = levels[String(user?.role).toLowerCase()];
  const requiredLevel = levels[minimumRole];
  if (userLevel === undefined || requiredLevel === undefined || userLevel < requiredLevel) {
    return <Alert severity="warning">Bạn không có quyền truy cập chức năng này.</Alert>;
  }
  return children;
}
