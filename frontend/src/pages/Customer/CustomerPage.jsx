import { useState } from "react";
import { Box, Typography, Paper, Button } from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import CustomerDialog from "./CustomerDialog";
import ConfirmDeleteDialog from "../../components/ConfirmDeleteDialog";// Import Dialog dùng chung

export default function CustomerPage() {
  // Dữ liệu danh sách khách hàng
  const [customers, setCustomers] = useState([
    { id: 1, fullName: "Nguyễn Văn A", phone: "0901234567", email: "nva@gmail.com", status: "Active" },
    { id: 2, fullName: "Trần Thị B", phone: "0987654321", email: "ttb@gmail.com", status: "Inactive" },
  ]);

  // Quản lý trạng thái của Dialog Thêm/Sửa
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState(null);

  // Quản lý trạng thái của Dialog Xóa
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [customerToDeleteId, setCustomerToDeleteId] = useState(null);

  // Mở Form Thêm mới
  const handleAddClick = () => {
    setSelectedCustomer(null);
    setDialogOpen(true);
  };

  // Mở Form Sửa
  const handleEditClick = (customer) => {
    setSelectedCustomer(customer);
    setDialogOpen(true);
  };

  // Đóng Form Thêm/Sửa
  const handleCloseDialog = () => {
    setDialogOpen(false);
    setSelectedCustomer(null);
  };

  // Lưu dữ liệu Thêm/Sửa
  const handleSaveCustomer = (formData) => {
    if (selectedCustomer) {
      setCustomers((prev) =>
        prev.map((c) => (c.id === selectedCustomer.id ? { ...c, ...formData } : c))
      );
    } else {
      const newCustomer = {
        ...formData,
        id: Date.now(),
      };
      setCustomers((prev) => [newCustomer, ...prev]);
    }
    handleCloseDialog();
  };

  // Mở Dialog Xác nhận Xóa
  const handleDeleteClick = (id) => {
    setCustomerToDeleteId(id);
    setDeleteDialogOpen(true);
  };

  // Thực hiện Xóa khi người dùng bấm "Xác nhận Xóa"
  const handleConfirmDelete = () => {
    setCustomers((prev) => prev.filter((c) => c.id !== customerToDeleteId));
    setDeleteDialogOpen(false);
    setCustomerToDeleteId(null);
  };

  const columns = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "fullName", headerName: "Họ và Tên", flex: 1, minWidth: 200 },
    { field: "phone", headerName: "Số điện thoại", width: 150 },
    { field: "email", headerName: "Email", flex: 1, minWidth: 200 },
    { 
      field: "status", 
      headerName: "Trạng thái", 
      width: 130,
      renderCell: (params) => (
        <Typography 
          color={params.value === "Active" ? "success.main" : "error.main"}
          sx={{ display: 'flex', alignItems: 'center', height: '100%', fontWeight: 500 }}
        >
          {params.value}
        </Typography>
      )
    },
    {
      field: "actions",
      headerName: "Thao tác",
      width: 160,
      sortable: false,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', height: '100%' }}>
          <Button 
            size="small" 
            variant="outlined" 
            onClick={() => handleEditClick(params.row)}
          >
            Sửa
          </Button>
          <Button 
            size="small" 
            variant="outlined" 
            color="error"
            onClick={() => handleDeleteClick(params.row.id)}
          >
            Xóa
          </Button>
        </Box>
      )
    }
  ];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h5" fontWeight="bold">
          Quản lý Khách hàng
        </Typography>
        <Button 
          variant="contained" 
          startIcon={<AddIcon />}
          sx={{ textTransform: 'none' }}
          onClick={handleAddClick}
        >
          Thêm khách hàng
        </Button>
      </Box>

      <Paper sx={{ width: '100%', flexGrow: 1, minHeight: 400 }}>
        <DataGrid
          rows={customers}
          columns={columns}
          initialState={{
            pagination: {
              paginationModel: { page: 0, pageSize: 10 },
            },
          }}
          pageSizeOptions={[5, 10, 25]}
          disableRowSelectionOnClick
          slots={{ toolbar: GridToolbar }}
          slotProps={{
            toolbar: {
              showQuickFilter: true,
              quickFilterProps: { debounceMs: 500 },
            },
          }}
          sx={{ border: 0 }}
        />
      </Paper>

      {/* Modal Thêm/Sửa Khách hàng */}
      <CustomerDialog 
        open={dialogOpen} 
        onClose={handleCloseDialog} 
        onSave={handleSaveCustomer} 
        customer={selectedCustomer} 
      />

      {/* Dialog Xác nhận Xóa dùng chung */}
      <ConfirmDeleteDialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={handleConfirmDelete}
        title="Xóa khách hàng"
        message="Bạn có chắc chắn muốn xóa khách hàng này khỏi hệ thống? Thao tác này không thể khôi phục."
      />
    </Box>
  );
}