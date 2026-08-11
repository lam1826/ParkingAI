import { Card, CardContent, Box, IconButton, Tooltip, Chip, Button } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";

const VehicleTable = ({ vehicles, loading, onAdd, onEdit, onDelete }) => {
  const columns = [
    { field: "id", headerName: "ID", width: 80 },
    {
      field: "license_plate",
      headerName: "Biển số xe",
      flex: 1.2,
      minWidth: 150,
      renderCell: (params) => (
        <strong style={{ color: "#1976d2" }}>{params.value}</strong>
      ),
    },
    {
      field: "vehicle_type",
      headerName: "Loại xe",
      flex: 1,
      minWidth: 150,
      renderCell: (params) => {
        // Có thể lấy tên từ object vehicle_type nếu backend trả về dạng nested object
        const typeName = params.row.vehicle_type?.name || params.value || "N/A";
        return <Chip label={typeName} size="small" variant="outlined" />;
      },
    },
    {
      field: "customerName",
      headerName: "Chủ sở hữu",
      flex: 1.5,
      minWidth: 180,
      valueGetter: (_value, row) => row.customer?.full_name || "Khách vãng lai",
    },
    {
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
          <Tooltip title="Xóa">
            <IconButton color="error" size="small" onClick={() => onDelete(params.row)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      ),
    },
  ];

  return (
    <Card elevation={0} sx={{ border: "1px solid #e0e0e0" }}>
      <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
          <Button variant="contained" startIcon={<AddIcon />} onClick={onAdd}>
            Thêm phương tiện
          </Button>
        </Box>
        <Box sx={{ height: 500, width: "100%" }}>
          <DataGrid
            rows={vehicles}
            columns={columns}
            loading={loading}
            pageSizeOptions={[10, 20, 50]}
            initialState={{
              pagination: { paginationModel: { pageSize: 10 } },
            }}
            disableRowSelectionOnClick
            sx={{
              border: "none",
              "& .MuiDataGrid-columnHeaders": { backgroundColor: "#f5f7fb" },
            }}
          />
        </Box>
      </CardContent>
    </Card>
  );
};

export default VehicleTable;
