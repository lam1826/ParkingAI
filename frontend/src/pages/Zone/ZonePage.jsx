import { Box, Typography, Paper, Button } from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import useZone from "./hooks/useZone";

export default function ZonePage() {
  const { zones, loading } = useZone();

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "name", headerName: "Tên khu vực", flex: 1, minWidth: 150 },
    { field: "code", headerName: "Mã Zone", width: 130 },
    { field: "capacity", headerName: "Sức chứa tối đa", width: 150 },
    { field: "currentParked", headerName: "Đang đỗ", width: 130 },
  ];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h5" fontWeight="bold">Quản lý Khu vực bãi xe (Zone)</Typography>
        <Button variant="contained" startIcon={<AddIcon />}>Thêm khu vực</Button>
      </Box>
      <Paper sx={{ width: '100%', flexGrow: 1, minHeight: 400 }}>
        <DataGrid
          rows={zones}
          columns={columns}
          loading={loading}
          slots={{ toolbar: GridToolbar }}
          sx={{ border: 0 }}
        />
      </Paper>
    </Box>
  );
}