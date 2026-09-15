import CrudPage from "../../components/common/CrudPage";
import { vehicleTypeService } from "./services/vehicleTypeService";
import useCorePermissions from "../../hooks/useCorePermissions";

export default function VehicleTypePage() {
  const { canManageConfiguration } = useCorePermissions();
  return <CrudPage title="Quản lý loại phương tiện" service={vehicleTypeService} canEdit={canManageConfiguration}
    readOnlyMessage="Bạn có thể tra cứu loại xe. Quản lý phụ trách thay đổi danh mục." fields={[
    { name: "name", label: "Tên loại xe", required: true },
    { name: "description", label: "Mô tả" },
    { name: "is_active", label: "Đang hoạt động", type: "boolean", defaultValue: true,
      formatter: (value) => value === false ? "Ngừng dùng" : "Đang dùng" },
  ]} />;
}
