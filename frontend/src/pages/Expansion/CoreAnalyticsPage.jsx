import { useCallback, useEffect, useRef, useState } from "react";
import { Alert } from "@mui/material";
import AIResultContent from "../../components/ai/AIResultContent";
import api from "../../services/api";
import { AI_REQUEST_TIMEOUT_MS } from "../../services/aiReportService";
import { toBusinessDateString } from "../../utils/businessDate";
import { analysisPayload, canViewReportRevenue, reportStatistics } from "../../utils/coreAnalytics";
import { requestId } from "../../utils/requestId";
import { extractReportDownloadErrorMessage } from "../Report/services/reportDownloadError";
import { dateTime, money, read, Records, SitePicker, useAction, useRemote, useSites, Workspace } from "./shared";

const kinds = { report: "Báo cáo AI", question: "Hỏi đáp", staff: "Gợi ý nhân sự" };

function AnalysisWorkspace({ site, mode, onBusy }) {
  const [period, setPeriod] = useState("day");
  const [anchorDate, setAnchorDate] = useState(toBusinessDateString);
  const [question, setQuestion] = useState("");
  const [kind, setKind] = useState("report");
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
  const data = report.data;
  const days = (data?.daily_traffic || []).map(row => ({ ...row, id: row.date, movements: row.departures == null ? null : row.arrivals + row.departures }));
  const highest = Math.max(1, ...days.map(row => row.movements || 0));
  const periodField = <label className="field">Kỳ phân tích<select value={period} onChange={setFilter(setPeriod)} disabled={action.busy || exporting}><option value="day">Một ngày</option><option value="week">7 ngày đến ngày chọn</option></select></label>;
  const dateField = <label className="field">{period === "week" ? "Ngày kết thúc" : "Ngày báo cáo"}<input type="date" value={anchorDate} required min="0001-01-07" max="9998-12-31" disabled={action.busy || exporting} onChange={setFilter(setAnchorDate)} /></label>;
  return <>
    {mode === "reports" && <>
      <section className="surface"><div className="section-head"><h2>Khoảng thời gian</h2><div className="form-actions"><button className="button quiet small" disabled={action.busy || exporting} onClick={() => { setPeriod("day"); setAnchorDate(toBusinessDateString()); }}>Hôm nay</button><button className="button quiet small" disabled={action.busy || exporting} onClick={() => { setPeriod("week"); setAnchorDate(toBusinessDateString()); }}>7 ngày</button></div></div>
        <form className="form-grid" onSubmit={event => { event.preventDefault(); void report.reload(); }}>{periodField}{dateField}<div className="form-actions core-wide"><button className="button primary" disabled={report.loading}>Xem báo cáo</button><button type="button" className="button secondary" disabled={exporting || report.loading || !!report.error || !data} onClick={exportReport}>{exporting ? "Đang xuất…" : "Xuất CSV"}</button></div></form>
        <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>Giờ Việt Nam. Kỳ 7 ngày bao gồm ngày kết thúc đã chọn.</p>
      </section>
      {exportError && <p className="form-error" role="alert">{exportError}</p>}
      {report.error && <Alert severity="error" action={<button className="button quiet small" onClick={report.reload}>Thử lại</button>}>{report.error}</Alert>}
      {report.loading && <p className="inline-note" role="status">Đang tải số liệu bãi xe…</p>}
      {data && <>
        <section className="surface"><div className="section-head"><h2>Lượt xe trong kỳ</h2><span className="badge neutral">Giờ Việt Nam</span></div>
          <div className="stat-strip"><span className="stat-item"><strong>{data.total_arrivals}</strong>lượt vào</span><span className="stat-item"><strong>{data.total_departures ?? "—"}</strong>lượt ra</span><span className="stat-item"><strong>{data.total_movements ?? "—"}</strong>tổng vào + ra</span></div>
          <p className="inline-note">Cao điểm theo tổng lượt vào + ra: {data.peak_movement_hours?.length ? data.peak_movement_hours.join(", ") : "Chưa có dữ liệu trong kỳ."}</p>
          <div className="chart-bars" role="img" aria-label="Tổng lượt vào và ra theo ngày; số liệu chi tiết ở bảng bên dưới">{days.map(row => <div className="chart-column" key={row.date}><span>{row.movements ?? "—"}</span><div className={`chart-bar ${row.movements === highest ? "peak" : ""}`} style={{ height: `${Math.max(2, (row.movements || 0) * 120 / highest)}px` }} /><span className="chart-label">{row.date.slice(5).split("-").reverse().join("/")}</span></div>)}</div>
          <Records rows={days} columns={[{ key: "date", label: "Ngày" }, { key: "arrivals", label: "Lượt vào" }, { key: "departures", label: "Lượt ra", render: row => row.departures ?? "Chưa có số liệu" }, { key: "movements", label: "Tổng", render: row => row.movements ?? "—" }]} />
          <details className="demo-help"><summary>Xem lưu lượng theo khung giờ</summary><p className="inline-note">Cao điểm theo lượt vào: {data.peak_hours?.length ? data.peak_hours.join(", ") : "Chưa có lượt xe vào trong kỳ."}</p><Records rows={data.hourly_traffic.map(row => ({ ...row, id: row.hour }))} columns={[{ key: "hour", label: "Khung giờ" }, { key: "arrivals", label: "Vào" }, { key: "departures", label: "Ra", render: row => row.departures ?? "Chưa có số liệu" }, { key: "movements", label: "Tổng", render: row => row.departures == null ? "—" : row.arrivals + row.departures }]} empty="Chưa có dữ liệu lưu lượng theo giờ." /></details>
          <p className="muted" style={{ fontSize: 12, marginTop: 16 }}>Kỳ {data.start_date} — {data.end_date}. {data.demo_mode ? "Dữ liệu trình diễn đồ án." : "Số liệu từ hệ thống."}</p>
        </section>
        {canViewReportRevenue(data, site.role) && <section className="surface"><div className="section-head"><h2>Thu tiền trong kỳ</h2></div><Records rows={reportStatistics(data, site.role).filter(row => row.currency)} columns={[{ key: "label", label: "Khoản thu / hoàn" }, { key: "value", label: "Số tiền", render: row => money(row.value) }]} /><p className="inline-note">Doanh thu tính theo chứng từ thu/hoàn trong kỳ. Thu QR mô phỏng: {money(data.revenue.demo_receipts)}; hoàn mô phỏng: {money(data.revenue.demo_refunds)}, hiển thị riêng.</p></section>}
        <section className="surface"><div className="section-head"><h2>Chỗ trống hiện tại</h2><span className="badge neutral">{dateTime(data.current_availability.as_of)}</span></div>
          <p className="inline-note">Đây là tình trạng hiện tại, không phải tỷ lệ lấp đầy của kỳ lịch sử. {data.current_availability.capacity_total != null && <>Tổng vị trí {data.current_availability.capacity_total} · Đang phục vụ {data.current_availability.total} · Tạm ngừng {data.current_availability.inactive_slots ?? 0}.</>}</p>
          <Records rows={data.current_availability.zones.map(zone => ({ ...zone, id: zone.zone_id }))} columns={[{ key: "name", label: "Khu vực" }, { key: "occupied", label: "Có xe" }, { key: "available_now", label: "Nhận xe ngay" }, { key: "reserved_slots", label: "Giữ trước" }, { key: "total", label: "Đang phục vụ" }]} />
          {!canViewReportRevenue(data, site.role) && <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>Bạn đang xem lưu lượng và chỗ trống. Báo cáo doanh thu dành cho quản lý.</p>}
        </section>
      </>}
    </>}
    {mode === "ai" && <>
      <section className="surface"><div className="section-head"><h2>Phân tích bãi đỗ</h2>{status.data?.enabled && <span className="badge neutral">Gemini · {status.data.model}</span>}</div>
        <p className="inline-note">AI nhận số liệu của bãi và kỳ đã chọn. Mỗi kết quả lưu cả dữ liệu đầu vào để đối chiếu. Kiểm tra câu trả lời trước khi dùng để quyết định nhân sự.</p>
        {status.error && <Alert severity="error">{status.error}</Alert>}
        {!status.loading && unavailable && <p className="inline-note warning">AI chưa được bật hoặc chưa cấu hình kết nối. Bạn vẫn xem được số liệu và lịch sử.</p>}
        <form className="form-grid" onSubmit={event => { event.preventDefault(); if (!disabled && (kind !== "question" || question.trim())) generate(kind); }}>
          <label className="field">Nội dung<select value={kind} disabled={action.busy} onChange={event => { setKind(event.target.value); setResult(null); retry.current = null; }}>{Object.entries(kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {periodField}{dateField}
          <label className="field">Câu hỏi (cho mục Hỏi đáp)<input value={question} disabled={action.busy || kind !== "question"} required={kind === "question"} maxLength={2000} placeholder="Khung giờ nào đông nhất?" onChange={event => setQuestion(event.target.value)} /></label>
          <div className="form-actions core-wide"><button className="button primary" disabled={disabled || (kind === "question" && !question.trim())}>Tạo phân tích</button></div>
        </form>
        {report.error && <p className="form-error" role="alert">{report.error}</p>}
        {action.busy && <p className="inline-note" role="status">Đang phân tích dữ liệu, vui lòng đợi…</p>}
        {action.error && <p className="form-error" role="alert">{action.error} Nếu đã đợi lâu, hãy làm mới lịch sử trước khi thử lại.</p>}
        {action.notice && <p className="inline-note success" role="status">{action.notice}</p>}
      </section>
      <section className="surface" aria-live="polite"><div className="section-head"><h2>Kết quả đã lưu</h2>{result && <span className="muted">{dateTime(result.created_at)}</span>}</div>
        {result ? <><p className="muted">{kinds[result.kind]} · Kỳ {result.start_date} — {result.end_date}</p><div className="chat-message assistant"><AIResultContent content={result.content} /></div>{result.input && <details className="demo-help"><summary>Xem dữ liệu đầu vào đã chốt</summary><p className="inline-note">Dữ liệu lưu cùng kết quả; thao tác mới không thay đổi báo cáo cũ.</p><Records rows={reportStatistics(result.input, site.role)} columns={[{ key: "label", label: "Chỉ tiêu" }, { key: "value", label: "Giá trị", render: row => row.currency ? money(row.value) : row.value }]} /><p className="muted">Chỗ trống tại {dateTime(result.input.current_availability?.as_of)}: {result.input.current_availability?.available_now ?? "Chưa có dữ liệu"}</p></details>}</> : <div className="empty">Chọn kỳ ngày hoặc tuần rồi bấm Tạo phân tích, hoặc mở một kết quả trong lịch sử.</div>}
      </section>
      <section className="surface"><div className="section-head"><h2>Lịch sử phân tích</h2><button className="button quiet small" disabled={history.loading || action.busy} onClick={history.reload}>Làm mới lịch sử</button></div>
        <p className="muted" style={{ fontSize: 12 }}>20 kết quả gần nhất được phép xem. Nhân viên xem kết quả của mình; quản lý xem kết quả của bãi.</p>
        {history.error && <p className="form-error" role="alert">{history.error}</p>}{history.loading && <p role="status">Đang tải lịch sử…</p>}
        {history.data?.map(row => <div className="list-row" key={row.id}><div><strong>{kinds[row.kind]}</strong><p>{row.start_date} — {row.end_date} · {dateTime(row.created_at)}</p></div><button className="button quiet small" disabled={action.busy} onClick={() => setResult(row)}>{result?.id === row.id ? "Đang xem" : "Xem lại"}</button></div>)}
        {!history.loading && !history.error && !history.data?.length && <div className="empty">Chưa có phân tích AI.</div>}
      </section>
    </>}
  </>;
}

export default function CoreAnalyticsPage({ mode = "reports" }) {
  const sites = useSites();
  const [busy, setBusy] = useState(false);
  const site = sites.sites.find((item) => String(item.id) === String(sites.siteId));
  return <Workspace title="Báo cáo & AI"
    description="Lưu lượng, chỗ trống và tiền đã thu từ dữ liệu của bãi." remote={sites}>
    <SitePicker sites={sites} disabled={busy} />
    {site ? <AnalysisWorkspace key={`${site.id}:${mode}`} site={site} mode={mode} onBusy={setBusy} />
      : !sites.loading && <Alert severity="info">Chưa có bãi được cấp quyền. Liên hệ quản trị viên để được phân công.</Alert>}
  </Workspace>;
}
