import { useEffect, useRef, useState } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, CircularProgress, Stack, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import api from "../../services/api";
import { getErrorMessage } from "../../utils/errorMessage";
import { readReportContext } from "../../utils/aiContext";
import formatMetadataTimestamp from "../../utils/formatMetadataTimestamp";

const PAGE_SIZE = 20;
const labels = { DAILY_REPORT: "Báo cáo ngày", WEEKLY_REPORT: "Báo cáo tuần", Q_A: "Hỏi đáp", DASHBOARD_QA: "Hỏi đáp bãi xe", STAFF_SCHEDULE: "Gợi ý nhân sự" };

export default function AIReportHistory({ revision }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [reload, setReload] = useState(0);
  const requestVersion = useRef(0);

  useEffect(() => {
    const version = ++requestVersion.current;
    setLoading(true); setError(""); setReports([]); setHasMore(false);
    api.get("/ai/reports", { params: { skip: 0, limit: PAGE_SIZE } })
      .then(({ data }) => {
        if (version !== requestVersion.current) return;
        setReports(data); setHasMore(data.length === PAGE_SIZE);
      })
      .catch((requestError) => {
        if (version === requestVersion.current) setError(getErrorMessage(requestError, "Không thể tải lịch sử AI. Vui lòng thử lại."));
      })
      .finally(() => { if (version === requestVersion.current) setLoading(false); });
    return () => { requestVersion.current += 1; };
  }, [revision, reload]);

  const loadMore = async () => {
    if (loading) return;
    const version = ++requestVersion.current;
    setLoading(true); setError("");
    try {
      const { data } = await api.get("/ai/reports", { params: { skip: reports.length, limit: PAGE_SIZE } });
      if (version !== requestVersion.current) return;
      setReports((current) => [...current, ...data.filter((report) => !current.some((item) => item.id === report.id))]);
      setHasMore(data.length === PAGE_SIZE);
    } catch (requestError) {
      if (version === requestVersion.current) setError(getErrorMessage(requestError, "Không thể tải thêm lịch sử. Vui lòng thử lại."));
    } finally { if (version === requestVersion.current) setLoading(false); }
  };

  return <Box component="section" aria-labelledby="ai-history-title">
    <Stack direction="row" spacing={2} sx={{ mb: 1, justifyContent: "space-between", alignItems: "center" }}>
      <Typography id="ai-history-title" variant="h6">Lịch sử phân tích của tôi</Typography>
      <Button disabled={loading} onClick={() => setReload((current) => current + 1)}>Làm mới</Button>
    </Stack>
    <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>Mở một bản ghi để xem nội dung, kỳ báo cáo và nguồn dữ liệu đã dùng.</Typography>
    {error && <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" onClick={() => reports.length ? loadMore() : setReload((current) => current + 1)}>Thử lại</Button>}>{error}</Alert>}
    {!loading && !error && reports.length === 0 && <Typography color="text.secondary">Chưa có lịch sử phân tích. Hãy đặt câu hỏi hoặc tạo báo cáo ở trên.</Typography>}
    {reports.map((report) => {
      const context = readReportContext(report);
      return <Accordion key={report.id} disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-controls={`ai-report-${report.id}`} id={`ai-report-heading-${report.id}`}>
          <Box sx={{ minWidth: 0 }}>
            <Typography fontWeight={600}>{labels[report.report_type] || "Phân tích AI"} · {formatMetadataTimestamp(report.created_at)}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{context.period} · {context.source}</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails id={`ai-report-${report.id}`}>
          <Typography sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxWidth: "75ch" }}>{report.content}</Typography>
        </AccordionDetails>
      </Accordion>;
    })}
    {loading && <Stack role="status" direction="row" spacing={1} sx={{ py: 2, alignItems: "center" }}><CircularProgress size={20} /><Typography variant="body2">Đang tải lịch sử…</Typography></Stack>}
    {hasMore && !loading && <Button sx={{ mt: 2 }} onClick={loadMore}>Xem thêm</Button>}
  </Box>;
}
