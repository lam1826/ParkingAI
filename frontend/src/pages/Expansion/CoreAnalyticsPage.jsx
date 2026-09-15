import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, MenuItem, Stack, TextField, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import DownloadIcon from "@mui/icons-material/Download";
import AIResultContent from "../../components/ai/AIResultContent";
import api from "../../services/api";
import { AI_REQUEST_TIMEOUT_MS } from "../../services/aiReportService";
import { toBusinessDateString } from "../../utils/businessDate";
import { analysisPayload, canViewReportRevenue, reportStatistics } from "../../utils/coreAnalytics";
import { requestId } from "../../utils/requestId";
import { extractReportDownloadErrorMessage } from "../Report/services/reportDownloadError";
import { dateTime, money, read, Records, RemoteSection, Section, SitePicker, useAction, useRemote, useSites, Workspace } from "./shared";

const kinds = { report: "Báo cáo AI", question: "Hỏi đáp", staff: "Gợi ý nhân sự" };

function AnalysisWorkspace({ site, mode, onBusy }) {
  const [period, setPeriod] = useState("day");
  const [anchorDate, setAnchorDate] = useState(toBusinessDateString);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const retry = useRef(null);
  const prefix = `/sites/${site.id}`;
  const loadSummary = useCallback(() => read(`${prefix}/reports/summary`, { period, anchor_date: anchorDate }), [prefix, period, anchorDate]);
  const report = useRemote(loadSummary);
  const loadStatus = useCallback(() => read(`${prefix}/ai/status`), [prefix]);
  const status = useRemote(loadStatus);
  const loadHistory = useCallback(() => read(`${prefix}/ai/analyses`, { limit: 20 }), [prefix]);
  const history = useRemote(loadHistory);
  const action = useAction(history.reload);
  useEffect(() => { onBusy(action.busy || exporting); return () => onBusy(false); }, [action.busy, exporting, onBusy]);
  const setFilter = (setter) => (event) => { setter(event.target.value); setResult(null); setExportError(""); retry.current = null; };
  const exportReport = async () => {
    if (exporting || report.loading || report.error || !report.data) return;
    setExporting(true);
    setExportError("");
    try {
      const response = await api.get(`/api/v2${prefix}/reports/export`, {
        params: { period: report.data.period, anchor_date: report.data.end_date }, responseType: "blob",
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `parking-report-${site.id}-${report.data.period}-${report.data.end_date}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(await extractReportDownloadErrorMessage(error, "Không thể xuất báo cáo. Hãy thử lại."));
    } finally {
      setExporting(false);
    }
  };
  const generate = (kind) => {
    if (action.busy) return;
    const signature = JSON.stringify([kind, period, anchorDate, kind === "question" ? question.trim() : ""]);
    if (retry.current?.signature !== signature) retry.current = { signature, requestId: requestId() };
    const body = analysisPayload({ kind, period, anchorDate, question, requestId: retry.current.requestId });
    setResult(null);
    void action.run(async () => (await api.post(`/api/v2${prefix}/ai/analyses`, body, { timeout: AI_REQUEST_TIMEOUT_MS })).data,
      "Đã lưu kết quả vào lịch sử phân tích.", (row) => { setResult(row); retry.current = null; });
  };
  const unavailable = !status.data?.enabled;
  const disabled = action.busy || report.loading || !!report.error || unavailable || !anchorDate;
  return <Stack spacing={3}>
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
      <TextField select label="Kỳ báo cáo" value={period} onChange={setFilter(setPeriod)} disabled={action.busy || exporting} sx={{ minWidth: 170 }}>
        <MenuItem value="day">Theo ngày</MenuItem><MenuItem value="week">7 ngày</MenuItem>
      </TextField>
      <TextField type="date" label={period === "week" ? "Ngày kết thúc" : "Ngày báo cáo"} value={anchorDate} required
        disabled={action.busy || exporting} onChange={setFilter(setAnchorDate)} slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: "0001-01-07", max: "9998-12-31" } }} />
      {mode === "reports" && <Button variant="outlined" startIcon={exporting ? <CircularProgress size={16} /> : <DownloadIcon />}
        disabled={exporting || action.busy || report.loading || !!report.error || !report.data} onClick={exportReport}>Xuất CSV</Button>}
    </Box>
    {exportError && <Alert severity="error">{exportError}</Alert>}
    <RemoteSection remote={report} title="Số liệu bãi xe" description="Giờ Việt Nam. Kỳ 7 ngày bao gồm ngày kết thúc đã chọn.">
      {(data) => <Stack spacing={2}>
        <Typography>Kỳ: {data.start_date} — {data.end_date}. {data.demo_mode ? "Dữ liệu trình diễn đồ án." : "Số liệu từ hệ thống."}</Typography>
        <Records rows={reportStatistics(data, site.role)} columns={[{ key: "label", label: "Chỉ tiêu" }, { key: "value", label: "Trong kỳ", render: (row) => row.currency ? money(row.value) : row.value }]} />
        <Typography><strong>Giờ đông nhất theo lượt vào:</strong> {data.peak_hours.length ? data.peak_hours.join(", ") : "Chưa có lượt xe vào trong kỳ."}</Typography>
        {data.peak_movement_hours && <Typography><strong>Giờ nhiều lượt vào và ra nhất:</strong> {data.peak_movement_hours.length ? data.peak_movement_hours.join(", ") : "Chưa có lượt vào hoặc ra trong kỳ."}</Typography>}
        {mode === "reports" && <>
          <Records rows={data.daily_traffic.map((row) => ({ ...row, id: row.date }))} columns={[{ key: "date", label: "Ngày" }, { key: "arrivals", label: "Lượt vào" }, { key: "departures", label: "Lượt ra", render: (row) => row.departures ?? "Chưa có số liệu" }]} />
          <Records rows={data.hourly_traffic.filter((row) => row.arrivals > 0 || row.departures > 0).map((row) => ({ ...row, id: row.hour }))} columns={[{ key: "hour", label: "Khung giờ" }, { key: "arrivals", label: "Lượt vào trong kỳ" }, { key: "departures", label: "Lượt ra trong kỳ", render: (row) => row.departures ?? "Chưa có số liệu" }]} empty="Chưa có dữ liệu lưu lượng theo giờ." />
        </>}
        {canViewReportRevenue(data, site.role)
          ? <Typography color="text.secondary">Doanh thu tính theo chứng từ thu/hoàn trong kỳ. Thu QR mô phỏng: {money(data.revenue.demo_receipts)}; hoàn mô phỏng: {money(data.revenue.demo_refunds)}, hiển thị riêng.</Typography>
          : <Typography color="text.secondary">Bạn đang xem lưu lượng và chỗ trống. Báo cáo doanh thu dành cho quản lý.</Typography>}
        <Typography component="h2" variant="h6">Chỗ trống hiện tại</Typography>
        <Typography color="text.secondary">Cập nhật {dateTime(data.current_availability.as_of)}. Đây là tình trạng hiện tại, không phải tỷ lệ lấp đầy của kỳ lịch sử.</Typography>
        {data.current_availability.capacity_total != null && <Typography>Tổng vị trí {data.current_availability.capacity_total} · Đang phục vụ {data.current_availability.total} · Tạm ngừng {data.current_availability.inactive_slots ?? 0}</Typography>}
        <Records rows={data.current_availability.zones.map((zone) => ({ ...zone, id: zone.zone_id }))} columns={[
          { key: "name", label: "Khu vực" }, { key: "total", label: "Tổng" }, { key: "occupied", label: "Có xe" },
          { key: "reserved_slots", label: "Đã giữ" }, { key: "available_now", label: "Còn nhận xe" },
        ]} />
      </Stack>}
    </RemoteSection>
    {mode === "ai" && <>
      <Section title="Trợ lý phân tích" description="AI nhận số liệu của bãi và kỳ đã chọn. Kiểm tra câu trả lời trước khi dùng để quyết định nhân sự.">
        {status.error && <Alert severity="error">{status.error}</Alert>}
        {!status.loading && unavailable && <Alert severity="info">AI chưa được bật hoặc chưa cấu hình kết nối. Bạn vẫn xem được số liệu và lịch sử.</Alert>}
        {status.data?.enabled && <Typography color="text.secondary">Gemini · {status.data.model}</Typography>}
        <TextField label="Câu hỏi về bãi xe" multiline minRows={2} value={question} disabled={action.busy}
          placeholder="Khu nào còn chỗ? Khung giờ nào đông nhất trong kỳ đã chọn?" onChange={(event) => setQuestion(event.target.value)}
          slotProps={{ htmlInput: { maxLength: 2000 } }} helperText={`${question.length}/2000 ký tự`} />
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          <Button variant="contained" startIcon={<AutoAwesomeIcon />} disabled={disabled} onClick={() => generate("report")}>Sinh báo cáo {period === "week" ? "tuần" : "ngày"}</Button>
          <Button variant="outlined" disabled={disabled || !question.trim()} onClick={() => generate("question")}>Hỏi AI</Button>
          <Button variant="outlined" disabled={disabled} onClick={() => generate("staff")}>Gợi ý nhân sự</Button>
        </Stack>
        {action.busy && <Stack direction="row" spacing={1} role="status"><CircularProgress size={20} /><Typography>Đang phân tích dữ liệu, vui lòng đợi…</Typography></Stack>}
        {action.error && <Alert severity="error">{action.error} Nếu đã đợi lâu, hãy làm mới lịch sử trước khi thử lại.</Alert>}
        {action.notice && <Alert severity="success">{action.notice}</Alert>}
        {result && <Box aria-live="polite"><Typography variant="h6">Kết quả {kinds[result.kind].toLowerCase()}</Typography>
          <Typography color="text.secondary">Kỳ {result.start_date} — {result.end_date} · Tạo lúc {dateTime(result.created_at)}</Typography>
          <AIResultContent content={result.content} /></Box>}
      </Section>
      <RemoteSection remote={history} title="Lịch sử phân tích" description="20 kết quả gần nhất được phép xem. Nhân viên xem kết quả của mình; quản lý xem kết quả của bãi."
        actions={<Button disabled={history.loading || action.busy} onClick={history.reload}>Làm mới lịch sử</Button>}>
        {(rows) => <Records rows={rows} columns={[
          { key: "created_at", label: "Thời gian", render: (row) => dateTime(row.created_at) },
          { key: "kind", label: "Nội dung", render: (row) => kinds[row.kind] },
          { key: "period", label: "Kỳ dữ liệu", render: (row) => `${row.start_date} — ${row.end_date}` },
          { key: "view", label: "Kết quả", render: (row) => <Button disabled={action.busy} onClick={() => setResult(row)}>Xem kết quả</Button> },
        ]} empty="Chưa có phân tích AI." />}
      </RemoteSection>
    </>}
  </Stack>;
}

export default function CoreAnalyticsPage({ mode = "reports" }) {
  const sites = useSites();
  const [busy, setBusy] = useState(false);
  const site = sites.sites.find((item) => String(item.id) === String(sites.siteId));
  return <Workspace title={mode === "ai" ? "AI báo cáo & hỏi đáp" : "Báo cáo bãi xe"}
    description={mode === "ai" ? "Báo cáo ngày/tuần, hỏi đáp chỗ trống và gợi ý bố trí nhân sự." : "Lưu lượng, doanh thu và khung giờ cao điểm theo dữ liệu của bãi."} remote={sites}>
    <SitePicker sites={sites} disabled={busy} />
    {site ? <AnalysisWorkspace key={`${site.id}:${mode}`} site={site} mode={mode} onBusy={setBusy} />
      : !sites.loading && <Alert severity="info">Chưa có bãi được cấp quyền. Liên hệ quản trị viên để được phân công.</Alert>}
  </Workspace>;
}
