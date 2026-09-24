import { Alert } from "@mui/material";
import PublicProfileForm from "./PublicProfileForm";
import { SitePicker, useAction, useSites, Workspace } from "./shared";

export default function SiteConfigurationPage() {
  const sites = useSites();
  const action = useAction(sites.reload);
  const site = sites.sites.find(row => String(row.id) === String(sites.siteId));
  return <Workspace title="Cấu hình bãi" description="Thông tin giới thiệu, liên hệ và vị trí công khai của bãi đỗ." remote={sites} action={action}>
    <SitePicker sites={sites} disabled={action.busy} />
    {site ? <PublicProfileForm key={site.id} siteId={site.id} action={action} />
      : !sites.loading && <Alert severity="info">Chưa có bãi được cấp quyền. Liên hệ quản trị viên để được phân công.</Alert>}
  </Workspace>;
}
