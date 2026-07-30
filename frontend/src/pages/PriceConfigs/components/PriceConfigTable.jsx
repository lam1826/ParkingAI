import React, { useState } from "react";
import { Box, TextField, Button, IconButton, Tooltip, Chip } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";

const TICKET_TYPE_LABELS = {
  HOURLY: "Theo giờ",
  DAILY: "Theo ngày",
  MONTHLY: "Theo tháng",
};

const formatCurrency = (value) =>
  new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(value ?? 0);

const PriceConfigTable = ({ data, loading, vehicleTypes, onAdd, onEdit, onDelete }) => {
  const [searchText, setSearchText] = useState("");

  const vehicleTypeNameById = (id) => {
    const vt = vehicleTypes.find((v) => v.id === id);
    return vt ? vt.name : id;
  };

  const filteredData = data.filter((item) => {
    const query = searchText.toLowerCase();
    return vehicleTypeNameById(item.vehicle_type_id).toLowerCase().includes(query);
  });

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    {
      field: "vehicle_type_id",
      headerName: "Loại xe",
      width: 150,
      renderCell: (params) => <Chip label={vehicleTypeNameById(params.value)} size="small" color="primary" variant="outlined" />,
    },
    {
      field: "ticket_type",
      headerName: "Hình thức",
      width: 130,
      renderCell: (params) => TICKET_TYPE_LABELS[params.value] || params.value,
    },
    {
      field: "price",
      headerName: "Đơn giá",
      width: 150,
      renderCell: (params) => formatCurrency(params.value),
    },
    { field: "effective_date", headerName: "Ngày áp dụng", width: 140 },
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
          placeholder="Tìm kiếm theo loại xe..."
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
          Thêm bảng giá
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

export default PriceConfigTable;
