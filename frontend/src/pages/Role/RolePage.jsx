import CrudPage from "../../components/common/CrudPage";
import { roleService } from "./services/roleService";

export default function RolePage() {
  return <CrudPage title="Quản lý vai trò và phân quyền" service={roleService} fields={[
    { name: "name", label: "Tên vai trò", required: true },
    { name: "description", label: "Mô tả quyền hạn" },
  ]} />;
}
