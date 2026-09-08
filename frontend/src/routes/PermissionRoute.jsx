import { useContext } from "react";
import { Alert } from "@mui/material";
import { AuthContext } from "../context/AuthContext";
import { hasMinimumRole } from "../constants/roles";
import { Navigate } from "react-router-dom";
import { useExpansion } from "../context/ExpansionContext";

export default function PermissionRoute({ children, minimumRole = "staff", legacy = true }) {
  const { user } = useContext(AuthContext);
  const capabilities = useExpansion();
  if (!hasMinimumRole(user?.role, minimumRole)) {
    return <Alert severity="warning">Bạn không có quyền truy cập chức năng này.</Alert>;
  }
  if (legacy && capabilities && !capabilities.legacy_workspace_allowed) return <Navigate to="/sites" replace />;
  return children;
}
