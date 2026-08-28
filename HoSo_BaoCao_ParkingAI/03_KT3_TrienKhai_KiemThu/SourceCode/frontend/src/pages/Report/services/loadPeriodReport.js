import { toBusinessDateString } from "../../../utils/businessDate.js";

export async function loadPeriodReport(reportClient, period, now = new Date()) {
  const anchorDate = toBusinessDateString(now);
  const params = { period, anchor_date: anchorDate };
  const [revenue, traffic] = await Promise.all([
    reportClient.getRevenueReport(params),
    reportClient.getTrafficReport(params),
  ]);
  return { revenue, traffic, anchorDate };
}
