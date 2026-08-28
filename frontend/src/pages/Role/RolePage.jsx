import CrudPage from "../../components/common/CrudPage";
import { roleService } from "./services/roleService";

export default function RolePage() {
  return <CrudPage title="Vai trò hệ thống" service={roleService} canEdit={false} fields={[
    { name: "name", label: "Tên vai trò", required: true },
    { name: "description", label: "Mô tả quyền hạn" },
  ]} />;
}
