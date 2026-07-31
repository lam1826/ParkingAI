import { Box, Typography, Paper, Button } from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import useRole from "./hooks/useRole";

export default function RolePage() {
  const { roles, loading } = useRole();

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "roleName", headerName: "Tên vai trò (Role)", width: 180 },
    { field: "description", headerName: "Mô tả quyền hạn", flex: 1, minWidth: 250 },
    { field: "userCount", headerName: "Số lượng tài khoản", width: 150, align: "center", headerAlign: "center" },
  ];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h5" fontWeight="bold">Quản lý Vai trò & Phân quyền (RBAC)</Typography>
        <Button variant="contained" startIcon={<AddIcon />}>Thêm vai trò</Button>
      </Box>
      <Paper sx={{ width: '100%', flexGrow: 1, minHeight: 400 }}>
        <DataGrid
          rows={roles}
          columns={columns}
          loading={loading}
          slots={{ toolbar: GridToolbar }}
          sx={{ border: 0 }}
        />
      </Paper>
    </Box>
  );
}