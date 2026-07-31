import { Card, CardContent, Box, IconButton, Tooltip, Chip, Button } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";

const UserTable = ({ users, loading, canManage, onAdd, onEdit, onDelete }) => {
  // Cấu hình các cột mặc định
  const columns = [
    { field: "username", headerName: "Tên đăng nhập", flex: 1, minWidth: 150, renderCell: (p) => <strong>{p.value}</strong> },
    { field: "full_name", headerName: "Họ và tên", flex: 1.5, minWidth: 180 },
    { field: "email", headerName: "Email", flex: 1.5, minWidth: 200 },
    {
      field: "role",
      headerName: "Vai trò",
      flex: 1,
      minWidth: 130,
      valueGetter: (params) => params.row.role?.name || params.row.role || "N/A",
      renderCell: (params) => (
        <Chip label={params.value} color="primary" size="small" variant="outlined" />
      ),
    },
    {
      field: "is_active",
      headerName: "Trạng thái",
      flex: 1,
      minWidth: 130,
      renderCell: (params) => (
        <Chip
          label={params.value !== false ? "Hoạt động" : "Khóa"}
          color={params.value !== false ? "success" : "default"}
          size="small"
        />
      ),
    },
  ];

  // Chỉ thêm cột thao tác nếu có quyền quản lý
  if (canManage) {
    columns.push({
      field: "actions",
      headerName: "Thao tác",
      width: 120,
      sortable: false,
      renderCell: (params) => (
        <Box>
          <Tooltip title="Chỉnh sửa">
            <IconButton color="primary" size="small" onClick={() => onEdit(params.row)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Xóa tài khoản">
            <IconButton color="error" size="small" onClick={() => onDelete(params.row)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      ),
    });
  }

  return (
    <Card elevation={0} sx={{ border: "1px solid #e0e0e0" }}>
      <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
        {canManage && (
          <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
            <Button variant="contained" startIcon={<AddIcon />} onClick={onAdd}>
              Thêm người dùng
            </Button>
          </Box>
        )}
        <Box sx={{ height: 500, width: "100%" }}>
          <DataGrid
            rows={users}
            columns={columns}
            loading={loading}
            pageSizeOptions={[10, 20, 50]}
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            disableRowSelectionOnClick
            sx={{ border: "none", "& .MuiDataGrid-columnHeaders": { backgroundColor: "#f5f7fb" } }}
          />
        </Box>
      </CardContent>
    </Card>
  );
};

export default UserTable;