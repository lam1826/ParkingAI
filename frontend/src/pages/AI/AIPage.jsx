import { useContext, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Paper, Stack, TextField, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "../../services/api";
import { requestAI, requestDailyReport, requestWeeklyReport } from "../../services/aiReportService";
import { AuthContext } from "../../context/AuthContext";
import { getErrorMessage } from "../../utils/errorMessage";
import { MAX_AI_QUESTION_CHARS } from "../../utils/aiContext";
import AIReportHistory from "../../components/ai/AIReportHistory";

export default function AIPage() {
  const { user } = useContext(AuthContext);
  return user ? <AccountAIPage key={user.id} /> : null;
}

function AccountAIPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [historyRevision, setHistoryRevision] = useState(0);
  const requestVersion = useRef(0);

  useEffect(() => {
    const clear = () => {
      requestVersion.current += 1;
      setQuestion(""); setResult(""); setError(""); setLoading(false);
    };
    window.addEventListener("parking-ai-clear-chat", clear);
    return () => {
      requestVersion.current += 1;
      window.removeEventListener("parking-ai-clear-chat", clear);
    };
  }, []);

  const run = async (action) => {
    if (loading) return;
    const version = ++requestVersion.current;
    setLoading(true); setError(""); setResult("");
    try {
      // Backend tự tổng hợp dữ liệu thật từ database trước khi gửi cho AI
      // (luồng: Database -> Aggregation -> Prompt -> AI), client chỉ gửi tham số.
      let response;
      if (action === "question") {
        response = await requestAI(api, "/ai/question", { question });
      } else if (action === "daily") {
        response = await requestDailyReport(api);
      } else if (action === "weekly") {
        response = await requestWeeklyReport(api);
      } else {
        response = await requestAI(api, "/ai/staff-suggestion", {});
      }
      if (version !== requestVersion.current) return;
      setResult(response.data.content);
      setHistoryRevision((current) => current + 1);
    } catch (requestError) {
      if (version === requestVersion.current) setError(getErrorMessage(requestError, "Không thể kết nối dịch vụ AI. Vui lòng thử lại."));
    } finally { if (version === requestVersion.current) setLoading(false); }
  };

  const tooLong = question.trim().length > MAX_AI_QUESTION_CHARS;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Box><Typography variant="h5" fontWeight="bold">Trợ lý phân tích ParkingAI</Typography>
        <Typography color="text.secondary">Hỏi đáp dữ liệu bãi xe, sinh báo cáo ngày/tuần và gợi ý bố trí nhân sự.</Typography></Box>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Stack spacing={2}>
          <TextField multiline minRows={3} label="Câu hỏi quản trị"
            placeholder="Ví dụ: Khung giờ nào đông nhất hôm nay?" value={question}
            onChange={(event) => setQuestion(event.target.value)} disabled={loading}
            error={tooLong} helperText={`${question.length}/${MAX_AI_QUESTION_CHARS} ký tự`}
            slotProps={{ htmlInput: { maxLength: MAX_AI_QUESTION_CHARS } }} />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Button variant="contained" startIcon={<AutoAwesomeIcon />} disabled={!question.trim() || tooLong || loading} onClick={() => run("question")}>Hỏi AI</Button>
            <Button variant="outlined" disabled={loading} onClick={() => run("daily")}>Sinh báo cáo ngày</Button>
            <Button variant="outlined" disabled={loading} onClick={() => run("weekly")}>Sinh báo cáo tuần</Button>
            <Button variant="outlined" disabled={loading} onClick={() => run("staff")}>Gợi ý nhân sự</Button>
          </Stack>
          <Typography variant="body2" color="text.secondary">Báo cáo tuần sử dụng 7 ngày gần nhất, tính đến hôm nay theo giờ Việt Nam.</Typography>
        </Stack>
      </Paper>
      {loading && <Stack role="status" direction="row" spacing={1.5} sx={{ alignItems: "center" }}><CircularProgress size={24} /><Typography>Đang phân tích dữ liệu bãi xe…</Typography></Stack>}
      {error && <Alert severity="error">{error}</Alert>}
      {result && <Paper aria-live="polite" sx={{ p: { xs: 2, sm: 3 } }}><Typography variant="h6" gutterBottom>Kết quả phân tích</Typography><Typography sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxWidth: "75ch" }}>{result}</Typography></Paper>}
      <AIReportHistory revision={historyRevision} />
    </Box>
  );
}
