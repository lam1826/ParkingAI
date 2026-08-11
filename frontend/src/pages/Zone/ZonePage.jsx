import CrudPage from "../../components/common/CrudPage";
import { zoneService } from "./services/zoneService";

export default function ZonePage() {
  return <CrudPage title="Quản lý khu vực bãi xe" service={zoneService} fields={[
    { name: "name", label: "Tên khu vực", required: true },
    { name: "capacity", label: "Sức chứa", type: "number", required: true },
    { name: "is_active", label: "Đang hoạt động", type: "boolean" },
  ]} />;
}
