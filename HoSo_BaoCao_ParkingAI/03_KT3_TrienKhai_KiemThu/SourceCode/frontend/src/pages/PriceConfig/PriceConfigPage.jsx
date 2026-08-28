import { useEffect, useState } from "react";
import CrudPage from "../../components/common/CrudPage";
import { vehicleTypeService } from "../VehicleType/services/vehicleTypeService";
import { priceConfigService } from "./services/priceConfigService";

export default function PriceConfigPage() {
  const [types, setTypes] = useState([]);
  useEffect(() => {
    vehicleTypeService.getAll().then((data) => setTypes(data));
  }, []);
  return <CrudPage title="Cấu hình bảng giá" service={priceConfigService} fields={[
    { name: "vehicle_type_id", label: "Loại xe", type: "select", required: true,
      options: types.map((item) => ({ value: item.id, label: item.name })) },
    { name: "ticket_type", label: "Cách tính", type: "select", required: true,
      options: [{ value: "HOURLY", label: "Theo giờ" }, { value: "DAILY", label: "Theo ngày" }] },
    { name: "price", label: "Đơn giá (VND)", type: "number", required: true,
      formatter: (value) => Number(value || 0).toLocaleString("vi-VN") },
    { name: "effective_date", label: "Ngày áp dụng", type: "date", required: true },
    { name: "is_active", label: "Đang áp dụng", type: "boolean" },
  ]} />;
}
