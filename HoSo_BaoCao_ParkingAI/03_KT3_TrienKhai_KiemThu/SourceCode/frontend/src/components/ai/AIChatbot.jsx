import { useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Avatar,
  Badge,
  Box,
  Chip,
  CircularProgress,
  Fab,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
  Zoom,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import api from "../../services/api";
import { requestAI, requestDailyReport, requestWeeklyReport } from "../../services/aiReportService";
import { AuthContext } from "../../context/AuthContext";
import { getErrorMessage } from "../../utils/errorMessage";
import { clearAIChat, readAIChat, saveAIChat } from "../../utils/aiChatStorage";
import { buildAIQuestion, questionLimit } from "../../utils/aiContext";

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  content: "Xin chào! Mình có thể hỗ trợ bạn tra cứu và phân tích dữ liệu bãi đỗ xe.",
};

const aiActions = [
  { id: "daily", label: "Báo cáo ngày" },
  { id: "weekly", label: "Báo cáo tuần" },
  { id: "staff", label: "Gợi ý nhân sự" },
];

const pageContexts = [
  { match: "/sessions", label: "Phiên đỗ xe", prompts: ["Có bao nhiêu xe đang trong bãi?", "Khung giờ nào đông nhất hôm nay?"] },
  { match: "/vehicles", label: "Phương tiện", prompts: ["Tóm tắt tình hình phương tiện hôm nay", "Loại xe nào xuất hiện nhiều nhất?"] },
  { match: "/customers", label: "Khách hàng", prompts: ["Tóm tắt hoạt động khách hàng", "Có điểm nào cần lưu ý hôm nay?"] },
  { match: "/monthly-passes", label: "Vé tháng", prompts: ["Tình hình sử dụng vé tháng thế nào?", "Có xu hướng nào cần lưu ý?"] },
  { match: "/reports", label: "Báo cáo", prompts: ["Tóm tắt doanh thu hôm nay", "Phân tích xu hướng lưu lượng"] },
  { match: "/parking-slots", label: "Vị trí đỗ", prompts: ["Tỷ lệ lấp đầy hiện tại là bao nhiêu?", "Khu vực nào còn nhiều chỗ trống?"] },
  { match: "/zones", label: "Khu vực", prompts: ["Khu vực nào đang đông nhất?", "Tóm tắt sức chứa bãi xe"] },
  { match: "/vehicle-types", label: "Loại xe", prompts: ["Loại xe nào phổ biến nhất?", "Phân tích lưu lượng theo loại xe"] },
  { match: "/price-configs", label: "Bảng giá", prompts: ["Tóm tắt doanh thu hôm nay", "Đánh giá xu hướng phí gửi xe"] },
  { match: "/users", label: "Tài khoản", prompts: ["Tóm tắt hoạt động hệ thống hôm nay", "Đề xuất bố trí nhân sự"] },
  { match: "/roles", label: "Vai trò", prompts: ["Tóm tắt hoạt động hệ thống hôm nay", "Có điểm vận hành nào cần lưu ý?"] },
  { match: "/account", label: "Tài khoản của tôi", prompts: ["Tình hình bãi xe hôm nay thế nào?", "Có điểm nào cần lưu ý hôm nay?"] },
  { match: "/", label: "Dashboard", prompts: ["Tình hình bãi xe hôm nay thế nào?", "Đề xuất bố trí nhân sự hôm nay"] },
];

export default function AIChatbot() {
  const { user } = useContext(AuthContext);
  return user ? <AccountChatbot key={user.id} userId={user.id} /> : null;
}

function AccountChatbot({ userId }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState(() => {
    const stored = readAIChat(sessionStorage, userId);
    return stored.length ? stored : [welcomeMessage];
  });
  const messagesEndRef = useRef(null);
  const requestVersion = useRef(0);

  const pageContext = useMemo(
    () => pageContexts.find((item) => item.match === "/" || location.pathname.startsWith(item.match)),
    [location.pathname],
  );

  useEffect(() => {
    saveAIChat(sessionStorage, userId, messages);
  }, [messages, userId]);

  useEffect(() => {
    const handleClear = () => {
      requestVersion.current += 1;
      setMessages([welcomeMessage]);
      setQuestion("");
      setLoading(false);
    };
    window.addEventListener("parking-ai-clear-chat", handleClear);
    return () => {
      requestVersion.current += 1;
      window.removeEventListener("parking-ai-clear-chat", handleClear);
    };
  }, []);

  useEffect(() => {
    if (open) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  const clearMessages = () => {
    clearAIChat();
  };

  const sendMessage = async (presetQuestion) => {
    const text = (presetQuestion ?? question).trim();
    if (!text || loading || text.length > questionLimit(pageContext.label)) return;
    const version = ++requestVersion.current;

    const userMessage = { id: `user-${Date.now()}`, role: "user", content: text };
    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setLoading(true);

    try {
      const contextualQuestion = buildAIQuestion(text, pageContext.label);
      const { data } = await requestAI(api, "/ai/question", { question: contextualQuestion });
      if (version !== requestVersion.current) return;
      setMessages((current) => [
        ...current,
        { id: `assistant-${Date.now()}`, role: "assistant", content: data.content || "AI chưa trả về nội dung." },
      ]);
    } catch (error) {
      if (version !== requestVersion.current) return;
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          error: true,
          content: getErrorMessage(error, "Không thể kết nối dịch vụ AI. Vui lòng thử lại."),
        },
      ]);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  };

  const runAIAction = async (action) => {
    if (loading) return;
    const version = ++requestVersion.current;
    const actionInfo = aiActions.find((item) => item.id === action);
    setMessages((current) => [
      ...current,
      { id: `action-${Date.now()}`, role: "user", content: actionInfo.label },
    ]);
    setLoading(true);

    try {
      // Backend tự tổng hợp dữ liệu thật từ database rồi mới gửi cho AI
      // (luồng: Database -> Aggregation -> Prompt -> AI), client chỉ gửi tham số.
      let response;
      if (action === "daily") {
        response = await requestDailyReport(api);
      } else if (action === "weekly") {
        response = await requestWeeklyReport(api);
      } else {
        response = await requestAI(api, "/ai/staff-suggestion", {});
      }

      if (version !== requestVersion.current) return;
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: response.data.content || "AI chưa trả về nội dung.",
        },
      ]);
    } catch (error) {
      if (version !== requestVersion.current) return;
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          error: true,
          content: getErrorMessage(error, "Không thể thực hiện tác vụ AI."),
        },
      ]);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  return (
    <>
      <Zoom in={!open}>
        <Tooltip title="Hỏi ParkingAI" placement="left">
          <Fab
            color="primary"
            aria-label="Mở trợ lý ParkingAI"
            onClick={() => setOpen(true)}
            sx={{ position: "fixed", right: { xs: 16, sm: 28 }, bottom: { xs: 16, sm: 28 }, zIndex: 1300 }}
          >
            <Badge color="success" variant="dot" overlap="circular">
              <AutoAwesomeIcon />
            </Badge>
          </Fab>
        </Tooltip>
      </Zoom>

      <Zoom in={open} unmountOnExit>
        <Paper
          elevation={12}
          sx={{
            position: "fixed",
            right: { xs: 12, sm: 28 },
            bottom: { xs: 12, sm: 28 },
            width: { xs: "calc(100vw - 24px)", sm: 390 },
            height: { xs: "min(620px, calc(100vh - 24px))", sm: 540 },
            zIndex: 1400,
            borderRadius: 3,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Box sx={{ px: 2, py: 1.5, bgcolor: "primary.main", color: "primary.contrastText", display: "flex", alignItems: "center", gap: 1.25 }}>
            <Avatar sx={{ width: 36, height: 36, bgcolor: "common.white", color: "primary.main" }}>
              <AutoAwesomeIcon fontSize="small" />
            </Avatar>
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography fontWeight={700}>ParkingAI Assistant</Typography>
              <Typography variant="caption" sx={{ opacity: 0.85 }}>Đang hỗ trợ tại trang {pageContext.label}</Typography>
            </Box>
            <Tooltip title="Xóa hội thoại">
              <IconButton size="small" color="inherit" onClick={clearMessages} aria-label="Xóa hội thoại">
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <IconButton size="small" color="inherit" onClick={() => setOpen(false)} aria-label="Đóng trợ lý">
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>

          <Box role="log" aria-label="Hội thoại ParkingAI" aria-live="polite" sx={{ flexGrow: 1, overflowY: "auto", p: 2, bgcolor: "background.default" }}>
            <Stack spacing={1.5}>
              {messages.map((message) => (
                <Box key={message.id} sx={{ display: "flex", justifyContent: message.role === "user" ? "flex-end" : "flex-start" }}>
                  <Box
                    sx={{
                      maxWidth: "84%",
                      px: 1.5,
                      py: 1,
                      borderRadius: message.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                      bgcolor: message.error ? "error.light" : message.role === "user" ? "primary.main" : "common.white",
                      color: message.role === "user" ? "primary.contrastText" : "text.primary",
                      boxShadow: message.role === "assistant" ? 1 : 0,
                    }}
                  >
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                      {message.content}
                    </Typography>
                  </Box>
                </Box>
              ))}
              {loading && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, color: "text.secondary" }}>
                  <CircularProgress size={18} />
                  <Typography variant="caption">ParkingAI đang phân tích...</Typography>
                </Box>
              )}
              <div ref={messagesEndRef} />
            </Stack>
          </Box>

          <Stack direction="row" spacing={1} sx={{ px: 1.5, pt: 1.25, overflowX: "auto" }}>
            {aiActions.map((action) => (
              <Chip
                key={action.id}
                label={action.label}
                size="small"
                color="primary"
                variant="outlined"
                disabled={loading}
                onClick={() => runAIAction(action.id)}
                sx={{ flexShrink: 0 }}
              />
            ))}
          </Stack>

          {messages.length === 1 && (
            <Stack direction="row" spacing={1} sx={{ px: 1.5, pt: 1.25, overflowX: "auto" }}>
              {pageContext.prompts.map((prompt) => (
                <Chip key={prompt} label={prompt} size="small" variant="outlined" onClick={() => sendMessage(prompt)} sx={{ flexShrink: 0 }} />
              ))}
            </Stack>
          )}

          <Box sx={{ p: 1.5, display: "flex", alignItems: "flex-end", gap: 1, bgcolor: "common.white" }}>
            <TextField
              fullWidth
              multiline
              maxRows={3}
              size="small"
              placeholder="Nhập câu hỏi..."
              label="Câu hỏi"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              error={question.trim().length > questionLimit(pageContext.label)}
              helperText={`${question.length}/${questionLimit(pageContext.label)} ký tự`}
              slotProps={{ htmlInput: { maxLength: questionLimit(pageContext.label) } }}
            />
            <IconButton
              color="primary"
              onClick={() => sendMessage()}
              disabled={!question.trim() || loading || question.trim().length > questionLimit(pageContext.label)}
              aria-label="Gửi câu hỏi"
              sx={{ mb: 0.25 }}
            >
              <SendRoundedIcon />
            </IconButton>
          </Box>
        </Paper>
      </Zoom>
    </>
  );
}
