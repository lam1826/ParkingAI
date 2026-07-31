import { Box, Typography, Paper, Button } from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import useVehicleType from "./hooks/useVehicleType";

export default function VehicleTypePage() {
  const { vehicleTypes, loading } = useVehicleType();

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "typeName", headerName: "Tên loại xe", flex: 1, minWidth: 150 },
    { field: "description", headerName: "Mô tả", flex: 1, minWidth: 200 },
    { 
      field: "defaultRate", 
      headerName: "Giá cơ bản (VND)", 
      width: 160,
      renderCell: (params) => params.value ? params.value.toLocaleString() + " đ" : "---"
    },
  ];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h5" fontWeight="bold">Quản lý Loại phương tiện</Typography>
        <Button variant="contained" startIcon={<AddIcon />}>Thêm loại xe</Button>
      </Box>
      <Paper sx={{ width: '100%', flexGrow: 1, minHeight: 400 }}>
        <DataGrid
          rows={vehicleTypes}
          columns={columns}
          loading={loading}
          slots={{ toolbar: GridToolbar }}
          sx={{ border: 0 }}
        />
      </Paper>
    </Box>
  );
}