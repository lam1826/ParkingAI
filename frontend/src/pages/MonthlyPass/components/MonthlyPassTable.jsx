import { Card, CardContent, Box, IconButton, Tooltip, Chip, Button } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import formatDate from "../../../utils/formatDate";
import dayjs from "dayjs";

const MonthlyPassTable = ({ passes, loading, onAdd, onEdit, onDelete }) => {
  // Lưu ý: MUI DataGrid v9 — valueGetter/valueFormatter nhận (value, row) thay vì params
  const columns = [
    { field: "pass_code", headerName: "Mã thẻ", width: 120, renderCell: ({ value }) => <strong>{value || "—"}</strong> },
    {
      field: "license_plate",
      headerName: "Biển số xe",
      flex: 1,
      minWidth: 130,
      valueGetter: (_value, row) => row.vehicle?.license_plate || "N/A",
    },
    {
      field: "customerName",
      headerName: "Chủ sở hữu",
      flex: 1.5,
      minWidth: 180,
      valueGetter: (_value, row) => row.customer?.full_name || "N/A",
    },
    {
      field: "start_date",
      headerName: "Ngày bắt đầu",
      flex: 1,
      minWidth: 120,
      valueFormatter: (value) => (value ? formatDate(value) : "--"),
    },
    {
      field: "end_date",
      headerName: "Ngày hết hạn",
      flex: 1,
      minWidth: 120,
      valueFormatter: (value) => (value ? formatDate(value) : "--"),
    },
    {
      field: "status",
      headerName: "Trạng thái",
      flex: 1,
      minWidth: 130,
      renderCell: ({ row }) => {
        if (!row.is_active) {
          return <Chip label="Ngừng hoạt động" color="default" size="small" />;
        }
        // Vé còn hiệu lực đến HẾT ngày end_date (23:59:59), khớp cách backend tính phí
        const isExpired = dayjs().isAfter(dayjs(row.end_date).endOf("day"));
        return (
          <Chip
            label={isExpired ? "Hết hạn" : "Đang hoạt động"}
            color={isExpired ? "error" : "success"}
            size="small"
          />
        );
      },
    },
    {
      field: "actions",
      headerName: "Thao tác",
      width: 100,
      sortable: false,
      renderCell: (params) => (
        <Box>
          <Tooltip title="Chỉnh sửa / Gia hạn">
            <IconButton color="primary" size="small" onClick={() => onEdit(params.row)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Hủy vé">
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
            Đăng ký vé tháng
          </Button>
        </Box>
        <Box sx={{ height: 500, width: "100%" }}>
          <DataGrid
            rows={passes}
            columns={columns}
            loading={loading}
            pageSizeOptions={[10, 20, 50]}
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            disableRowSelectionOnClick
            sx={{ border: "none", "& .MuiDataGrid-columnHeaders": { backgroundColor: "#f5f7fb" } }}
          />
        </Box>
      </CardContent>
    </Card>
  );
};

export default MonthlyPassTable;