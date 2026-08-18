import CrudPage from "../../components/common/CrudPage";
import customerService from "./services/customerService";

const service = {
  getAll: customerService.getAllCustomers,
  create: customerService.createCustomer,
  update: customerService.updateCustomer,
  delete: customerService.deleteCustomer,
};

export default function CustomerPage() {
  return <CrudPage title="Quản lý khách hàng thân thiết" service={service} fields={[
    { name: "full_name", label: "Họ và tên", required: true },
    { name: "phone_number", label: "Số điện thoại", required: true },
    { name: "email", label: "Email", type: "email" },
  ]} />;
}
