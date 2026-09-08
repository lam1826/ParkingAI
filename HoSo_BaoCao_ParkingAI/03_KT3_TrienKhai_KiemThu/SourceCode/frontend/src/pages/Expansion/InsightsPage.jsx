import { useCallback, useState } from "react";
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Workspace, Section, Records, useSites, useRemote, useAction, read, send, dateTime, formLayout } from "./shared";

export default function InsightsPage() {
  const sites = useSites();
  const [hours, setHours] = useState(24);
  const [form, setForm] = useState({ service_seconds_per_vehicle: "45", utilization_target: "0.8", min_staff: "1", max_staff: "10" });
  const [staff, setStaff] = useState(null);
  const load = useCallback(async () => {
    if (!sites.siteId) return null;
    const [forecast, anomalies] = await Promise.all([read("/insights/forecast", { site_id: sites.siteId, horizon_hours: hours }), read("/insights/anomalies", { site_id: sites.siteId })]);
    return { forecast, anomalies };
  }, [sites.siteId, hours]);
  const remote = useRemote(load);
  const action = useAction();
  const forecast = remote.data?.forecast;
  const coverage = forecast?.coverage;
  const fingerprint = JSON.stringify([Number(sites.siteId), hours, form]);
  const plan = staff?.fingerprint === fingerprint ? staff.value : null;
  const number = (value) => typeof value === "number" ? value.toFixed(2) : "Chưa có";
  return <Workspace title="Dự báo & điều hành" description="Đọc dự báo từ lịch sử gửi xe, xem các dấu hiệu cần kiểm tra và lập phương án nhân sự với giả định rõ ràng." remote={remote} action={action}>
    {sites.error && <Alert severity="error">{sites.error}</Alert>}
    <Box sx={formLayout}><TextField select label="Bãi xe" value={sites.siteId} onChange={(event) => sites.setSiteId(event.target.value)}>{sites.sites.map((site) => <MenuItem key={site.id} value={site.id}>{site.name}</MenuItem>)}</TextField><TextField select label="Khoảng dự báo" value={hours} onChange={(event) => setHours(event.target.value)}>{[2, 6, 12, 24].map((value) => <MenuItem key={value} value={value}>{value} giờ tới</MenuItem>)}</TextField></Box>
    <Section title="Lưu lượng dự kiến" description="Khoảng dự báo là ước lượng theo dữ liệu lịch sử, không phải số chỗ đã được giữ.">
      {forecast?.status === "insufficient_data" && <Alert severity="info">Chưa đủ dữ liệu lịch sử để dự báo đáng tin cậy. Hệ thống sẽ hiển thị kết quả khi đủ thời gian quan sát; không tự tạo số liệu thay thế.</Alert>}
      {forecast?.warnings?.map((warning, index) => <Alert key={index} severity="info">{warning}</Alert>)}
      {forecast?.predictions?.length > 0 && <>
        <Box sx={{ height: 280, minWidth: 0 }}><ResponsiveContainer width="100%" height="100%"><AreaChart data={forecast.predictions}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="at" tickFormatter={(value) => dateTime(value).slice(0, 5)} minTickGap={32} /><YAxis allowDecimals={false} /><Tooltip labelFormatter={dateTime} /><Area type="monotone" dataKey="upper" name="Giới hạn trên" stroke="#a7c8e9" fill="#e8f1fa" /><Area type="monotone" dataKey="arrivals" name="Xe vào dự kiến" stroke="#1976d2" fill="#90caf9" /></AreaChart></ResponsiveContainer></Box>
        <Records rows={forecast.predictions.map((row) => ({ ...row, id: row.at }))} columns={[{ key: "at", label: "Khung giờ", render: (row) => dateTime(row.at) }, { key: "arrivals", label: "Xe vào dự kiến" }, { key: "departures", label: "Xe ra dự kiến" }, { key: "range", label: "Khoảng xe vào", render: (row) => `${row.lower} – ${row.upper}` }, { key: "samples", label: "Tuần có bản ghi", render: (row) => `${row.samples_observed ?? 0}/${(row.samples_observed ?? 0) + (row.samples_zero_filled ?? 0)}` }]} />
      </>}
      {forecast?.backtest && <Stack direction={{ xs: "column", sm: "row" }} spacing={3} useFlexGap><Typography>Sai số dự báo (MAE): <strong>{number(forecast.backtest.mae)}</strong></Typography><Typography>Sai số phương án đối chiếu: <strong>{number(forecast.backtest.baseline_mae)}</strong></Typography><Typography>Số mẫu kiểm tra: <strong>{forecast.backtest.samples ?? 0}</strong></Typography></Stack>}
      {coverage && <Box>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Độ phủ dữ liệu</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={3} useFlexGap sx={{ flexWrap: "wrap" }}>
          <Typography>Ngày lịch sử: <strong>{coverage.history_days ?? 0}/{coverage.required_days ?? 0}</strong></Typography>
          <Typography>Ngày có xe vào: <strong>{coverage.days_with_arrivals ?? 0}</strong></Typography>
          <Typography>Giờ có bản ghi xe vào: <strong>{coverage.hours_with_arrivals ?? 0}/{coverage.hours_in_window ?? 0}</strong></Typography>
          <Typography>Giờ được điền 0: <strong>{coverage.hours_zero_filled ?? 0}</strong></Typography>
          <Typography>Mức đầy đủ quan sát: <strong>{coverage.observation_completeness === "unknown" || !coverage.observation_completeness ? "Chưa xác định" : coverage.observation_completeness}</strong></Typography>
        </Stack>
        {coverage.completeness_note && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{coverage.completeness_note}</Typography>}
      </Box>}
    </Section>
    <Section title="Các dấu hiệu cần kiểm tra" description="Cảnh báo dựa trên quy tắc và dữ liệu có thật; quản lý kiểm tra bằng chứng trước khi kết luận."><Records rows={remote.data?.anomalies?.items} columns={[{ key: "severity", label: "Mức độ", render: (row) => row.severity === "high" || row.severity === "critical" ? "Ưu tiên kiểm tra" : "Cần lưu ý" }, { key: "message", label: "Phát hiện" }, { key: "session_id", label: "Mã lượt" }]} empty="Không có dấu hiệu cần kiểm tra theo bộ quy tắc hiện tại." /></Section>
    <Section title="Phương án nhân sự" description="Nhập thời gian phục vụ thực tế nếu đã đo. Giá trị ban đầu là giả định để thử nghiệm đồ án.">
      <Box component="form" sx={formLayout} onSubmit={(event) => { event.preventDefault(); const payload = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, Number(value)])); void action.run(() => send("/insights/staff-plan", { ...payload, site_id: Number(sites.siteId), horizon_hours: hours }), "Đã tính phương án theo các giả định đã nhập.", (value) => setStaff({ fingerprint, value })); }}>
        <TextField required type="number" label="Thời gian xử lý mỗi xe (giây)" value={form.service_seconds_per_vehicle} onChange={(event) => setForm((old) => ({ ...old, service_seconds_per_vehicle: event.target.value }))} inputProps={{ min: 5, max: 600 }} />
        <TextField select label="Mức sử dụng năng lực" value={form.utilization_target} onChange={(event) => setForm((old) => ({ ...old, utilization_target: event.target.value }))}>{["0.7", "0.8", "0.9"].map((value) => <MenuItem key={value} value={value}>{Number(value) * 100}%</MenuItem>)}</TextField>
        <TextField required type="number" label="Số nhân viên tối thiểu" value={form.min_staff} onChange={(event) => setForm((old) => ({ ...old, min_staff: event.target.value }))} inputProps={{ min: 1, max: 50 }} />
        <TextField required type="number" label="Số nhân viên tối đa" value={form.max_staff} onChange={(event) => setForm((old) => ({ ...old, max_staff: event.target.value }))} inputProps={{ min: 1, max: 50 }} />
        <Button type="submit" variant="contained" disabled={action.busy || !sites.siteId}>Tính phương án</Button>
      </Box>
      {plan?.warnings?.map((warning, index) => <Alert severity="info" key={index}>{warning}</Alert>)}
      {plan && <Records rows={(plan.plan || []).map((row) => ({ ...row, id: row.at }))} columns={[{ key: "at", label: "Khung giờ", render: (row) => dateTime(row.at) }, { key: "arrivals", label: "Xe vào dự kiến" }, { key: "staff_required", label: "Nhân viên đề xuất" }, { key: "capacity_shortfall", label: "Thiếu năng lực", render: (row) => row.capacity_shortfall ? "Cần xem lại giới hạn nhân sự" : "Không" }]} empty="Chưa đủ dữ liệu để tính phương án nhân sự." />}
    </Section>
  </Workspace>;
}
