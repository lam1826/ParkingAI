import { createContext, useContext, useEffect } from "react";
import { Alert, Box, Button, CircularProgress } from "@mui/material";
import { read, useRemote } from "../pages/Expansion/shared";

const ExpansionContext = createContext(null);
const load = () => read("/system/capabilities");

export function ExpansionProvider({ children }) {
  const remote = useRemote(load);
  const { reload } = remote;
  useEffect(() => {
    const update = () => { void reload(); };
    window.addEventListener("parkingai:sites-changed", update);
    return () => window.removeEventListener("parkingai:sites-changed", update);
  }, [reload]);
  if (!remote.data) return <Box sx={{ p: 3 }}>{remote.error ? <Alert severity="error" action={<Button onClick={remote.reload}>Thử lại</Button>}>{remote.error}</Alert> : <CircularProgress aria-label="Đang tải quyền sử dụng" />}</Box>;
  return <ExpansionContext.Provider value={remote.data}>{children}</ExpansionContext.Provider>;
}

export const useExpansion = () => useContext(ExpansionContext);
