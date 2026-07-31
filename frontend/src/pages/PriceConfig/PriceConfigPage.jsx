import { Box, Typography, Paper, Button, Chip } from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import usePriceConfig from "./hooks/usePriceConfig";

export default function PriceConfigPage() {
  const { priceConfigs, loading } = usePriceConfig();

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "name", headerName: "Tên biểu cước", flex: 1, minWidth: 180 },
    { field: "vehicleTypeName", headerName: "Loại xe", width: 130 },
    { 
      field: "hourlyRate", 
      headerName: "Giá theo giờ (VND)", 
      width: 150,
      renderCell: (params) => params.value?.toLocaleString() + " đ" 
    },
    { 
      field: "monthlyRate", 
      headerName: "Giá vé tháng (VND)", 
      width: 160,
      renderCell: (params) => params.value?.toLocaleString() + " đ" 
    },
    { 
      field: "isActive", 
      headerName: "Trạng thái", 
      width: 130,
      renderCell: (params) => (
        <Chip 
          label={params.value ? "Áp dụng" : "Ngưng"} 
          color={params.value ? "success" : "default"} 
          size="small" 
        />
      )
    },
  ];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h5" fontWeight="bold">Cấu hình Bảng giá & Cước phí</Typography>
        <Button variant="contained" startIcon={<AddIcon />}>Thêm bảng giá</Button>
      </Box>
      <Paper sx={{ width: '100%', flexGrow: 1, minHeight: 400 }}>
        <DataGrid
          rows={priceConfigs}
          columns={columns}
          loading={loading}
          slots={{ toolbar: GridToolbar }}
          sx={{ border: 0 }}
        />
      </Paper>
    </Box>
  );
}