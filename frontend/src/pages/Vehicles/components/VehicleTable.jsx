import React, { useState } from "react";
import { Box, TextField, Button, IconButton, Tooltip, Chip } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";

const VehicleTable = ({ data, loading, vehicleTypes, customers, onAdd, onEdit, onDelete }) => {
  const [searchText, setSearchText] = useState("");

  const vehicleTypeNameById = (id) => {
    const vt = vehicleTypes.find((v) => v.id === id);
    return vt ? vt.name : id;
  };

  const customerNameById = (id) => {
    if (!id) return "Khách vãng lai";
    const c = customers.find((c) => c.id === id);
    return c ? c.full_name : id;
  };

  const filteredData = (data || []).filter((item) => {
    const query = searchText.toLowerCase();
    return item.license_plate && item.license_plate.toLowerCase().includes(query);
  });

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "license_plate", headerName: "Biển số xe", flex: 1, minWidth: 150 },
    {
      field: "vehicle_type_id",
      headerName: "Loại xe",
      width: 150,
      renderCell: (params) => <Chip label={vehicleTypeNameById(params.value)} size="small" color="primary" variant="outlined" />,
    },
    {
      field: "customer_id",
      headerName: "Chủ xe",
      flex: 1.2,
      minWidth: 180,
      renderCell: (params) => customerNameById(params.value),
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
          placeholder="Tìm kiếm biển số xe..."
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
          Thêm phương tiện
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

export default VehicleTable;
