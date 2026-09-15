import { useEffect, useState } from "react";
import { Alert, Stack } from "@mui/material";
import CrudPage from "../../components/common/CrudPage";
import { vehicleTypeService } from "../VehicleType/services/vehicleTypeService";
import { priceConfigService } from "./services/priceConfigService";
import useCorePermissions from "../../hooks/useCorePermissions";

export default function PriceConfigPage() {
  const { canManageConfiguration } = useCorePermissions();
  const [types, setTypes] = useState([]);
  useEffect(() => {
    vehicleTypeService.getAll().then((data) => setTypes(data));
  }, []);
  return <Stack spacing={2}>
    <Alert severity="info">Xe vãng lai giữ đơn giá lúc vào; vé giờ/ngày trả trước giữ giá phụ trội khi tạo đơn. Thay đổi bảng giá áp dụng cho giao dịch mới; căn cứ giá đã chốt vẫn được giữ trong lịch sử. Lượt cũ chưa lưu giá có thể khiến hệ thống tạm khóa thay đổi bảng giá đang sử dụng.</Alert>
    <CrudPage title="Cấu hình bảng giá" service={priceConfigService} canEdit={canManageConfiguration}
    readOnlyMessage="Bạn có thể tra cứu đơn giá. Quản lý phụ trách thay đổi bảng giá." fields={[
    { name: "vehicle_type_id", label: "Loại xe", type: "select", required: true,
      formatter: (value) => types.find((type) => type.id === value)?.name || value,
      options: types.map((item) => ({ value: item.id, label: item.name })) },
    { name: "ticket_type", label: "Cách tính", type: "select", required: true,
      options: [{ value: "HOURLY", label: "Theo giờ" }, { value: "DAILY", label: "Theo ngày" }] },
    { name: "price", label: "Đơn giá (VND)", type: "number", required: true,
      formatter: (value) => Number(value || 0).toLocaleString("vi-VN") },
    { name: "effective_date", label: "Ngày áp dụng", type: "date", required: true },
    { name: "is_active", label: "Đang áp dụng", type: "boolean", formatter: (value) => value ? "Đang áp dụng" : "Ngừng áp dụng" },
  ]} /></Stack>;
}
