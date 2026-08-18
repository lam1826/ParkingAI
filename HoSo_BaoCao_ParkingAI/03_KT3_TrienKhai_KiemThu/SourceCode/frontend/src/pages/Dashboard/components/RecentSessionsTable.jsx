// File: src/pages/Dashboard/components/RecentSessionsTable.jsx
import { Card, CardContent, Typography, Box, Chip } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";

const RecentSessionsTable = ({ data, loading }) => {
  const columns = [
    { field: "plate", headerName: "Biển số", flex: 1, minWidth: 120 },
    { field: "vehicleType", headerName: "Loại xe", flex: 1, minWidth: 120 },
    { 
      field: "timeIn", 
      headerName: "Thời gian vào", 
      flex: 1.5,
      minWidth: 160,
      // MUI DataGrid v9: valueFormatter nhận trực tiếp value
      valueFormatter: (value) => {
        if (!value) return "";
        return new Date(value).toLocaleString("vi-VN");
      }
    },
    {
      field: "status",
      headerName: "Trạng thái",
      flex: 1,
      minWidth: 120,
      renderCell: (params) => {
        const isParked = params.row.status === "Đang đỗ";
        return (
          <Chip
            label={params.row.status}
            color={isParked ? "success" : "default"}
            size="small"
            variant={isParked ? "filled" : "outlined"}
          />
        );
      },
    },
  ];

  return (
    <Card elevation={0} sx={{ border: "1px solid #e0e0e0", height: "100%" }}>
      <CardContent>
        <Typography variant="h6" fontWeight="bold" gutterBottom>
          Phiên gửi xe gần đây
        </Typography>
        <Box sx={{ height: 350, width: "100%", mt: 2 }}>
          <DataGrid
            rows={data || []}
            columns={columns}
            loading={loading}
            pageSizeOptions={[5]}
            initialState={{
              pagination: { paginationModel: { pageSize: 5 } },
            }}
            disableRowSelectionOnClick
            sx={{
              "& .MuiDataGrid-columnHeaders": {
                backgroundColor: "#f5f7fb", // Trùng với màu nền theme Commit 6
                borderBottom: "none",
              },
              border: "none",
            }}
          />
        </Box>
      </CardContent>
    </Card>
  );
};

export default RecentSessionsTable;