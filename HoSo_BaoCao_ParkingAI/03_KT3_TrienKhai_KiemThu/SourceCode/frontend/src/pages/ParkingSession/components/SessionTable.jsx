import { useState } from "react";
import {
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogContentText,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import LogoutIcon from "@mui/icons-material/Logout";
import formatDate from "../../../utils/formatDate";

const SessionTable = ({ sessions, loading, onCheckOut, title = "Danh sách phiên gửi xe" }) => {
  const [selectedPlate, setSelectedPlate] = useState(null);

  const handleConfirmCheckOut = () => {
    if (selectedPlate) {
      onCheckOut(selectedPlate);
      setSelectedPlate(null);
    }
  };

  // Lưu ý: MUI DataGrid v9 — valueGetter/valueFormatter nhận (value, row) thay vì params
  const columns = [
    {
      field: "licensePlate",
      headerName: "Biển số",
      flex: 1,
      minWidth: 130,
      renderCell: (params) => (
        <strong style={{ color: "#1976d2" }}>
          {params.row.vehicle?.license_plate || "N/A"}
        </strong>
      ),
    },
    {
      field: "slotNumber",
      headerName: "Vị trí đỗ",
      flex: 1,
      minWidth: 130,
      valueGetter: (value, row) => row.parking_slot?.slot_number || "Chưa xếp",
    },
    {
      field: "checkInTime",
      headerName: "Thời gian vào",
      flex: 1.2,
      minWidth: 170,
      valueFormatter: (value) =>
        value ? formatDate(value, "HH:mm:ss - DD/MM/YYYY") : "",
    },
    {
      field: "checkOutTime",
      headerName: "Thời gian ra",
      flex: 1.2,
      minWidth: 170,
      valueFormatter: (value) =>
        value ? formatDate(value, "HH:mm:ss - DD/MM/YYYY") : "—",
    },
    {
      field: "parkingFee",
      headerName: "Phí (VNĐ)",
      flex: 0.8,
      minWidth: 110,
      valueFormatter: (value) =>
        value ? new Intl.NumberFormat("vi-VN").format(value) : "—",
    },
    {
      field: "status",
      headerName: "Trạng thái",
      width: 120,
      renderCell: (params) => (
        <Chip
          label={params.row.status === "active" ? "Đang gửi" : "Đã ra"}
          color={params.row.status === "active" ? "success" : "default"}
          size="small"
          variant={params.row.status === "active" ? "filled" : "outlined"}
        />
      ),
    },
    {
      field: "actions",
      headerName: "Thao tác",
      width: 150,
      sortable: false,
      renderCell: (params) =>
        params.row.status === "active" ? (
          <Button
            variant="contained"
            color="error"
            size="small"
            startIcon={<LogoutIcon />}
            onClick={() => setSelectedPlate(params.row.vehicle?.license_plate)}
          >
            Check Out
          </Button>
        ) : null,
    },
  ];

  return (
    <>
      <Card elevation={0} sx={{ border: "1px solid #e0e0e0" }}>
        <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
          <Typography variant="h6" fontWeight="bold" gutterBottom sx={{ mb: 2 }}>
            {title}
          </Typography>
          <Box sx={{ height: 420, width: "100%" }}>
            <DataGrid
              rows={sessions}
              columns={columns}
              loading={loading}
              pageSizeOptions={[5, 10, 20]}
              initialState={{
                pagination: { paginationModel: { pageSize: 10 } },
              }}
              disableRowSelectionOnClick
              sx={{
                border: "none",
                "& .MuiDataGrid-columnHeaders": {
                  backgroundColor: "#f5f7fb",
                },
              }}
            />
          </Box>
        </CardContent>
      </Card>

      {/* Dialog xác nhận cho xe ra */}
      <Dialog open={Boolean(selectedPlate)} onClose={() => setSelectedPlate(null)}>
        <DialogTitle fontWeight="bold">Xác nhận Check-out</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Bạn có chắc chắn muốn cho xe này ra khỏi bãi không? Hệ thống sẽ tính phí đỗ xe tự động.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setSelectedPlate(null)} variant="outlined">
            Hủy
          </Button>
          <Button onClick={handleConfirmCheckOut} color="error" variant="contained" autoFocus>
            Xác nhận
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default SessionTable;
