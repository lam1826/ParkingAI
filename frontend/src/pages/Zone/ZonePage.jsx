import CrudPage from "../../components/common/CrudPage";
import { zoneService } from "./services/zoneService";
import useCorePermissions from "../../hooks/useCorePermissions";

export default function ZonePage() {
  const { canManageConfiguration } = useCorePermissions();
  return <CrudPage title="Quản lý khu vực bãi xe" service={zoneService} canEdit={canManageConfiguration}
    readOnlyMessage="Bạn có thể tra cứu khu vực. Quản lý phụ trách thay đổi cấu hình bãi." fields={[
    { name: "name", label: "Tên khu vực", required: true },
    { name: "capacity", label: "Sức chứa", type: "number", required: true },
    { name: "is_active", label: "Đang hoạt động", type: "boolean" },
  ]} />;
}
