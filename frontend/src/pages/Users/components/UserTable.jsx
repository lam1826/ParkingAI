import React, { useState } from "react";
import { Box, TextField, Button, IconButton, Tooltip, Chip } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";

const UserTable = ({ data, loading, roles, onAdd, onEdit, onDelete }) => {
  const [searchText, setSearchText] = useState("");

  // Đã thêm (roles || []) để tránh crash nếu chưa load xong roles
  const roleNameById = (roleId) => {
    const role = (roles || []).find((r) => r.id === roleId);
    return role ? role.name : roleId;
  };

  // Đã thêm (data || []) để fix lỗi "reading 'filter'"
  const filteredData = (data || []).filter((item) => {
    const query = searchText.toLowerCase();
    return (
      (item.username && item.username.toLowerCase().includes(query)) ||
      (item.full_name && item.full_name.toLowerCase().includes(query))
    );
  });

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "username", headerName: "Tên đăng nhập", flex: 1, minWidth: 150 },
    { field: "full_name", headerName: "Họ và tên", flex: 1.3, minWidth: 180 },
    {
      field: "role_id",
      headerName: "Vai trò",
      width: 140,
      renderCell: (params) => <Chip label={roleNameById(params.value)} size="small" color="primary" variant="outlined" />,
    },
    {
      field: "is_active",
      headerName: "Trạng thái",
      width: 130,
      renderCell: (params) => (
        <Chip
          label={params.value ? "Hoạt động" : "Ngừng"}
          color={params.value ? "success" : "default"}
          size="small"
        />
      ),
    },
    {
      field: "actions",
      headerName: "Thao tác",
      width: 130,
      sortable: false,
      renderCell: (params) => (
        <Box>
          <Tooltip title="Chỉnh sửa">
            <IconButton color="primary" onClick={() => onEdit(params.row)} size="small">
              <EditIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Xóa">
            <IconButton color="error" onClick={() => onDelete(params.row)} size="small">
              <DeleteIcon />
            </IconButton>
          </Tooltip>
        </Box>
      ),
    },
  ];

  return (
    <Box sx={{ width: "100%" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 3, gap: 2, flexWrap: "wrap" }}>
        <TextField
          variant="outlined"
          size="small"
          placeholder="Tìm kiếm người dùng..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          sx={{ width: { xs: "100%", sm: "300px" }, backgroundColor: "background.paper", borderRadius: 1 }}
          slotProps={{
            input: {
              startAdornment: <SearchIcon color="action" sx={{ mr: 1 }} />,
            },
          }}
        />
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={onAdd}
          sx={{ fontWeight: "bold" }}
        >
          Thêm người dùng
        </Button>
      </Box>

      <Box sx={{ height: 500, width: "100%", backgroundColor: "background.paper", borderRadius: 2, boxShadow: 1 }}>
        <DataGrid
          rows={filteredData}
          columns={columns}
          loading={loading}
          initialState={{
            pagination: {
              paginationModel: { pageSize: 5, page: 0 },
            },
          }}
          pageSizeOptions={[5, 10, 20]}
          disableRowSelectionOnClick
          getRowId={(row) => row.id}
        />
      </Box>
    </Box>
  );
};

export default UserTable;