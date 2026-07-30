import React, { useState } from "react";
import { Box, TextField, Button, IconButton, Tooltip } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";

// 1. Khai báo thêm 'roles' vào props đề phòng component cha truyền 'roles' thay vì 'data'
const RoleTable = ({ roles, data, loading, onAdd, onEdit, onDelete }) => {
  const [searchText, setSearchText] = useState("");

  // 2. An toàn tuyệt đối: Ưu tiên lấy roles, nếu không có lấy data, cuối cùng là mảng rỗng
  const listData = roles || data || [];

  const filteredData = listData.filter((item) => {
    if (!item) return false; // Bảo vệ trường hợp dữ liệu bên trong mảng bị lỗi (null/undefined)
    
    const query = searchText.toLowerCase();
    return (
      (item.name && item.name.toLowerCase().includes(query)) ||
      (item.description && item.description.toLowerCase().includes(query))
    );
  });

  const columns = [
    { field: "id", headerName: "ID", width: 90 },
    { field: "name", headerName: "Tên vai trò", flex: 1, minWidth: 160 },
    { field: "description", headerName: "Mô tả", flex: 2, minWidth: 220 },
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
          placeholder="Tìm kiếm vai trò..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          sx={{ width: { xs: "100%", sm: "300px" }, backgroundColor: "background.paper", borderRadius: 1 }}
          
          // 3. Sử dụng InputProps thay vì slotProps để icon hiển thị tương thích tốt nhất trên MUI
          InputProps={{
            startAdornment: <SearchIcon color="action" sx={{ mr: 1 }} />,
          }}
        />
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={onAdd}
          sx={{ fontWeight: "bold" }}
        >
          Thêm vai trò
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

export default RoleTable;