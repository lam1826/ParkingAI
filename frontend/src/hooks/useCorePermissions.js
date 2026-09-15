import { useContext } from "react";
import { AuthContext } from "../context/AuthContext";
import { corePermissions } from "../constants/corePermissions";

export default function useCorePermissions() {
  const { user } = useContext(AuthContext);
  return corePermissions(user?.role);
}
