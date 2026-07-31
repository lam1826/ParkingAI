import { useState } from "react";
import {
  Card,
  CardContent,
  Box,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import formatDate from "../../../utils/formatDate";

const CustomerTable = ({
  customers,
  total,
  loading,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  onEdit,
  onDelete,
}) => {
  const [deleteId, setDeleteId] = useState(null);

  const handleConfirmDelete = () => {
    if (deleteId) {
      onDelete(deleteId);
      setDeleteId(null);
    }
  };

  const columns = [
    { field: "id", headerName: "ID", width: 80 },
    { field: "full_name", headerName: "Họ và tên", flex: 1.2, minWidth: 160 },
    { field: "phone_number", headerName: "Số điện thoại", flex: 1, minWidth: 140 },
    { field: "email", headerName: "Email", flex: 1.2, minWidth: 180 },
    { field: "address", headerName: "Địa chỉ", flex: 1.5, minWidth: 200 },
    {
      field: "created_at",
      headerName: "Ngày đăng ký",
      flex: 1,
      minWidth: 150,
      valueFormatter: (params) =>
        params.value ? formatDate(params.value, "DD/MM/YYYY") : "--",
    },
    {
      field: "actions",
      headerName: "Thao tác",
      width: 120,
      sortable: false,
      renderCell: (params) => (
        <Box>
          <Tooltip title="Chỉnh sửa">
            <IconButton
              color="primary"
              size="small"
              onClick={() => onEdit(params.row)}
            >
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Xóa">
            <IconButton
              color="error"
              size="small"
              onClick={() => setDeleteId(params.row.id)}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      ),
    },
  ];

  return (
    <>
      <Card elevation={0} sx={{ border: "1px solid #e0e0e0" }}>
        <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
          <Box sx={{ height: 480, width: "100%" }}>
            <DataGrid
              rows={customers}
              columns={columns}
              loading={loading}
              rowCount={total}
              paginationMode="server"
              page={page}
              pageSize={pageSize}
              onPageChange={onPageChange}
              onPageSizeChange={onPageSizeChange}
              pageSizeOptions={[10, 20, 50]}
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

      {/* Modal Xác nhận xóa */}
      <Dialog open={Boolean(deleteId)} onClose={() => setDeleteId(null)}>
        <DialogTitle fontWeight="bold">Xác nhận xóa khách hàng</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Bạn có chắc chắn muốn xóa khách hàng này không? Thao tác này không thể hoàn tác.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setDeleteId(null)} variant="outlined">
            Hủy
          </Button>
          <Button onClick={handleConfirmDelete} color="error" variant="contained" autoFocus>
            Xóa
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default CustomerTable;