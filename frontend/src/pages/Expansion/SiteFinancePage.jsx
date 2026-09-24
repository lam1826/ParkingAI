import { Alert } from "@mui/material";
import SiteFinance from "./SiteFinance";
import { SitePicker, useSites, Workspace } from "./shared";

export default function SiteFinancePage() {
  const sites = useSites();
  const site = sites.sites.find((row) => String(row.id) === String(sites.siteId));
  return <Workspace title="Thu chi & ca làm việc" description="Tra cứu chứng từ, quản lý thu tiền và chốt ca tại bãi." remote={sites}>
    <SitePicker sites={sites} />
    {site ? <SiteFinance key={site.id} site={site} /> : !sites.loading && <Alert severity="info">Chưa có bãi được cấp quyền.</Alert>}
  </Workspace>;
}
