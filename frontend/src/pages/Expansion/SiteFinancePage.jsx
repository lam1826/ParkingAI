import { useState } from "react";
import { Alert } from "@mui/material";
import SiteFinance from "./SiteFinance";
import { SitePicker, useSites, Workspace } from "./shared";

export default function SiteFinancePage() {
  const sites = useSites();
  const [revision, setRevision] = useState(0);
  const site = sites.sites.find((row) => String(row.id) === String(sites.siteId));
  // Header 'Làm mới' (#73) reloads the site list and then remounts the finance sections, so shifts,
  // receipts and revenue are fetched again (the same pattern as the overview page). An unconfirmed
  // refund's idempotency key (#24) lives outside SiteFinance (siteFinanceRefund.js), so the remount keeps it.
  const remote = { ...sites, reload: async () => { await sites.reload(); setRevision((value) => value + 1); } };
  return <Workspace title="Thu chi & ca làm việc" description="Tra cứu chứng từ, quản lý thu tiền và chốt ca tại bãi." remote={remote}>
    <SitePicker sites={sites} />
    {site ? <SiteFinance key={`${site.id}-${revision}`} site={site} /> : !sites.loading && <Alert severity="info">Chưa có bãi được cấp quyền.</Alert>}
  </Workspace>;
}
