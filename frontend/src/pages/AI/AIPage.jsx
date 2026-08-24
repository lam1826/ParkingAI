import { useState } from "react";
import { Alert, Box, Button, CircularProgress, Paper, Stack, TextField, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "../../services/api";
import { requestDailyReport, requestWeeklyReport } from "../../services/aiReportService";

export default function AIPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async (action) => {
    setLoading(true); setError(""); setResult("");
    try {
      // Backend tự tổng hợp dữ liệu thật từ database trước khi gửi cho AI
      // (luồng: Database -> Aggregation -> Prompt -> AI), client chỉ gửi tham số.
      if (action === "question") {
        const { data } = await api.post("/ai/question", { question });
        setResult(data.content);
      } else if (action === "daily") {
        const { data } = await requestDailyReport(api);
        setResult(data.content);
      } else if (action === "weekly") {
        const { data } = await requestWeeklyReport(api);
        setResult(data.content);
      } else {
        const { data } = await api.post("/ai/staff-suggestion", {});
        setResult(data.content);
      }
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Không thể kết nối dịch vụ AI.");
    } finally { setLoading(false); }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Box><Typography variant="h5" fontWeight="bold">Trợ lý phân tích ParkingAI</Typography>
        <Typography color="text.secondary">Hỏi đáp dữ liệu, sinh báo cáo ngày và gợi ý bố trí nhân sự.</Typography></Box>
      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <TextField multiline minRows={3} label="Câu hỏi quản trị"
            placeholder="Ví dụ: Khung giờ nào đông nhất hôm nay?" value={question}
            onChange={(event) => setQuestion(event.target.value)} />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <Button variant="contained" startIcon={<AutoAwesomeIcon />} disabled={!question.trim() || loading} onClick={() => run("question")}>Hỏi AI</Button>
            <Button variant="outlined" disabled={loading} onClick={() => run("daily")}>Sinh báo cáo ngày</Button>
            <Button variant="outlined" disabled={loading} onClick={() => run("weekly")}>Sinh báo cáo tuần</Button>
            <Button variant="outlined" disabled={loading} onClick={() => run("staff")}>Gợi ý nhân sự</Button>
          </Stack>
        </Stack>
      </Paper>
      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      {result && <Paper sx={{ p: 3, whiteSpace: "pre-wrap" }}><Typography variant="h6" gutterBottom>Kết quả phân tích</Typography>{result}</Paper>}
    </Box>
  );
}
