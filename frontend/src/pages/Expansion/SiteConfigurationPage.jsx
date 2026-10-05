import { useState } from "react";
import { Alert } from "@mui/material";
import PublicProfileForm from "./PublicProfileForm";
import { SitePicker, useAction, useSites, Workspace } from "./shared";

export default function SiteConfigurationPage() {
  const sites = useSites();
  const [revision, setRevision] = useState(0);
  // Which mounted profile form has unsaved edits (#73): the header 'Làm mới' re-fetches the
  // profile by remounting the form, so it asks before discarding typed changes.
  const [edited, setEdited] = useState(null);
  const action = useAction(async () => { setEdited(null); await sites.reload(); });
  const site = sites.sites.find(row => String(row.id) === String(sites.siteId));
  const formKey = site ? `${site.id}-${revision}` : null;
  const remote = { ...sites, reload: async () => {
    if (edited !== null && edited === formKey && !window.confirm("Thông tin bãi có thay đổi chưa lưu. Bỏ các thay đổi này và tải lại?")) return;
    setEdited(null);
    await sites.reload();
    setRevision((value) => value + 1);
  } };
  return <Workspace title="Cấu hình bãi" description="Thông tin giới thiệu, liên hệ và vị trí công khai của bãi đỗ." remote={remote} action={action}>
    <SitePicker sites={sites} disabled={action.busy} />
    {site ? <div style={{ display: "contents" }} onChange={() => setEdited(formKey)}>
      <PublicProfileForm key={formKey} siteId={site.id} action={action} />
    </div>
      : !sites.loading && <Alert severity="info">Chưa có bãi được cấp quyền. Liên hệ quản trị viên để được phân công.</Alert>}
  </Workspace>;
}
