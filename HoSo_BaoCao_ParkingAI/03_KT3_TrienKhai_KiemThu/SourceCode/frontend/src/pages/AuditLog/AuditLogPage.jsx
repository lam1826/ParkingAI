import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import api from "../../services/api";
import { requestAllOffsetPages } from "../../services/paginatedLookup";
import formatMetadataTimestamp from "../../utils/formatMetadataTimestamp";
import { createLatestRequestGate } from "../../utils/latestRequestGate";

const actionLabels = {
  CREATE: "Tạo mới",
  UPDATE: "Cập nhật",
  DELETE: "Xóa",
  CHECK_IN: "Xe vào",
  CHECK_OUT: "Xe ra",
  AI_ACTION: "Tác vụ AI",
};

export default function AuditLogPage() {
  const requestGate = useRef(null);
  if (requestGate.current === null) {
    requestGate.current = createLatestRequestGate();
  }
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [username, setUsername] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    const generation = requestGate.current.begin();
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (action) params.action = action;
      if (username.trim()) params.username = username.trim();
      if (success !== "") params.success = success;
      const data = await requestAllOffsetPages(
        api,
        "/api/v1/audit-logs",
        100,
        params,
      );
      if (requestGate.current.isCurrent(generation)) setRows(data);
    } catch (requestError) {
      if (requestGate.current.isCurrent(generation)) {
        setError(requestError.response?.data?.detail || "Không thể tải nhật ký hoạt động.");
      }
    } finally {
      if (requestGate.current.isCurrent(generation)) setLoading(false);
    }
  }, [action, success, username]);

  useEffect(() => {
    load();
    return () => requestGate.current.invalidate();
  }, [load]);

  const columns = [
    { field: "id", headerName: "ID", width: 75 },
    // created_at do SQLite func.now() sinh -> UTC-naive, phải diễn giải là
    // UTC trước khi hiển thị theo giờ VN (xem utils/formatMetadataTimestamp.js).
    { field: "created_at", headerName: "Thời gian", width: 175, valueFormatter: (value) => formatMetadataTimestamp(value) },
    { field: "username", headerName: "Tài khoản", minWidth: 140, flex: 1 },
    { field: "action", headerName: "Hành động", width: 135, renderCell: ({ value }) => <Chip size="small" label={actionLabels[value] || value} /> },
    { field: "resource", headerName: "Đối tượng", minWidth: 140, flex: 1 },
    { field: "resource_id", headerName: "Mã đối tượng", width: 135, valueFormatter: (value) => value || "—" },
    { field: "path", headerName: "API", minWidth: 220, flex: 1.3 },
    { field: "status_code", headerName: "Mã HTTP", width: 100 },
    {
      field: "success",
      headerName: "Kết quả",
      width: 115,
      renderCell: ({ value }) => <Chip size="small" color={value ? "success" : "error"} label={value ? "Thành công" : "Thất bại"} />,
    },
  ];

  return (
    <Stack spacing={2.5}>
      <Box>
        <Typography variant="h5" fontWeight="bold">Nhật ký hoạt động</Typography>
        <Typography color="text.secondary">Theo dõi thao tác thay đổi dữ liệu của nhân viên, quản lý và quản trị viên.</Typography>
      </Box>
      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <TextField select size="small" label="Hành động" value={action} onChange={(event) => setAction(event.target.value)} sx={{ minWidth: 165 }}>
            <MenuItem value="">Tất cả</MenuItem>
            {Object.entries(actionLabels).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
          </TextField>
          <TextField size="small" label="Tên tài khoản" value={username} onChange={(event) => setUsername(event.target.value)} />
          <TextField select size="small" label="Kết quả" value={success} onChange={(event) => setSuccess(event.target.value)} sx={{ minWidth: 150 }}>
            <MenuItem value="">Tất cả</MenuItem>
            <MenuItem value="true">Thành công</MenuItem>
            <MenuItem value="false">Thất bại</MenuItem>
          </TextField>
          <Button startIcon={<RefreshIcon />} onClick={load}>Làm mới</Button>
        </Stack>
      </Paper>
      {error && <Alert severity="error">{error}</Alert>}
      <Box sx={{ height: 610, width: "100%" }}>
        <DataGrid
          rows={rows}
          columns={columns}
          loading={loading}
          disableRowSelectionOnClick
          pageSizeOptions={[25, 50, 100]}
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          slots={{ toolbar: GridToolbar }}
        />
      </Box>
    </Stack>
  );
}
