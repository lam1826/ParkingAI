import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import CrudPage from "../../components/common/CrudPage";
import { zoneService } from "./services/zoneService";
import useCorePermissions from "../../hooks/useCorePermissions";

export default function ZonePage() {
  const { canManageConfiguration } = useCorePermissions();
  // This form cannot choose a site, so with several sites the server always refuses a new zone (409).
  // Ask first instead of offering a button that can never succeed (#71). Until the answer arrives the
  // button stays hidden; if the question itself fails, keep the button (the server still guards).
  const [scope, setScope] = useState(null);
  useEffect(() => {
    if (!canManageConfiguration) return undefined;
    let active = true;
    zoneService.getCreationScope().then(
      (value) => { if (active) setScope(value); },
      () => { if (active) setScope({ legacy_create_allowed: true }); },
    );
    return () => { active = false; };
  }, [canManageConfiguration]);
  const canCreate = canManageConfiguration && scope?.legacy_create_allowed === true;
  const createNote = scope?.legacy_create_allowed === false && <>
    {scope.detail || "Hệ thống có nhiều bãi nên trang này không tạo được khu vực mới."}{" "}
    Mở <RouterLink to="/sites">Vận hành bãi</RouterLink> → Công cụ vận hành khác → Cấu hình bãi để thêm khu vực cho đúng bãi. Khu vực hiện có vẫn sửa được tại đây.
  </>;
  return <CrudPage title="Quản lý khu vực bãi xe" service={zoneService} canEdit={canManageConfiguration}
    canCreate={canCreate} createNote={createNote}
    readOnlyMessage="Bạn có thể tra cứu khu vực. Quản lý phụ trách thay đổi cấu hình bãi." fields={[
    { name: "name", label: "Tên khu vực", required: true },
    { name: "capacity", label: "Sức chứa", type: "number", required: true },
    { name: "is_active", label: "Đang hoạt động", type: "boolean" },
  ]} />;
}
