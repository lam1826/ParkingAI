import { useContext } from "react";
import { Alert } from "@mui/material";
import { AuthContext } from "../context/AuthContext";
import { hasMinimumRole } from "../constants/roles";

export default function PermissionRoute({ children, minimumRole = "staff" }) {
  const { user } = useContext(AuthContext);
  if (!hasMinimumRole(user?.role, minimumRole)) {
    return <Alert severity="warning">Bạn không có quyền truy cập chức năng này.</Alert>;
  }
  return children;
}
