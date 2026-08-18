import CrudPage from "../../components/common/CrudPage";
import { vehicleTypeService } from "./services/vehicleTypeService";

export default function VehicleTypePage() {
  return <CrudPage title="Quản lý loại phương tiện" service={vehicleTypeService} fields={[
    { name: "name", label: "Tên loại xe", required: true },
    { name: "description", label: "Mô tả" },
  ]} />;
}
