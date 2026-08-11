import { useState } from "react";
import {
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogContentText,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import LogoutIcon from "@mui/icons-material/Logout";
import formatDate from "../../../utils/formatDate";

const SessionTable = ({ sessions, loading, onCheckOut }) => {
  const [selectedPlate, setSelectedPlate] = useState(null);

  const handleConfirmCheckOut = () => {
    if (selectedPlate) {
      onCheckOut(selectedPlate);
      setSelectedPlate(null);
    }
  };

  const columns = [
    { field: "id", headerName: "ID", width: 90 },
    {
      field: "licensePlate",
      headerName: "Biển số",
      flex: 1,
      minWidth: 150,
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
      minWidth: 150,
      valueGetter: (params) => params.row.parking_slot?.slot_number || "Chưa xếp",
    },
    {
      field: "checkInTime",
      headerName: "Thời gian vào",
      flex: 1.5,
      minWidth: 200,
      valueFormatter: (params) =>
        params.value ? formatDate(params.value, "HH:mm:ss - DD/MM/YYYY") : "",
    },
    {
      field: "actions",
      headerName: "Thao tác",
      width: 150,
      sortable: false,
      renderCell: (params) => (
        <Button
          variant="contained"
          color="error"
          size="small"
          startIcon={<LogoutIcon />}
          onClick={() => setSelectedPlate(params.row.vehicle?.license_plate)}
        >
          Check Out
        </Button>
      ),
    },
  ];

  return (
    <>
      <Card elevation={0} sx={{ border: "1px solid #e0e0e0" }}>
        <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
          <Typography variant="h6" fontWeight="bold" gutterBottom sx={{ mb: 2 }}>
            Danh sách xe đang đỗ trong bãi
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
