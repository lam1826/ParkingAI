import { useContext, useEffect, useRef, useState } from "react";
import api from "../../services/api";
import { requestAI } from "../../services/aiReportService";
import { AuthContext } from "../../context/AuthContext";
import { getErrorMessage } from "../../utils/errorMessage";
import { clearAIChat, readAIChat, saveAIChat } from "../../utils/aiChatStorage";
import { requestKey, SitePicker, useSites } from "../../pages/Expansion/shared";
import { chatRequest, chatScopeKey } from "./chatRequest";

const internalActions = [{ id: "daily", label: "Lưu lượng hôm nay" }, { id: "weekly", label: "Cao điểm tuần này" }, { id: "staff", label: "Gợi ý nhân sự" }];
const customerActions = [{ id: "question", label: "Giá gửi xe" }, { id: "question", label: "Còn chỗ không?" }, { id: "question", label: "Đặt chỗ thế nào?" }];

function RobotIcon() {
  return <svg viewBox="0 0 28 28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="5" y="8" width="18" height="15" rx="5" /><path d="M14 8V4m-2 0h4M2 13v5m24-5v5m-16-3v2m8-2v2m-7 4h6" /></svg>;
}
function ChatIcon({ close = false }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={close ? "m6 6 12 12M6 18 18 6" : "M4 12h16m-6-6 6 6-6 6"} /></svg>;
}

export default function AIChatbot() {
  const { user } = useContext(AuthContext);
  return user ? <AccountChatbot key={`${user.id}:${user.role}`} user={user} /> : null;
}

function AccountChatbot({ user }) {
  const sites = useSites();
  return <ScopedChatbot key={chatScopeKey(user.id, user.role, sites.siteId)} user={user} sites={sites} />;
}

function ScopedChatbot({ user, sites }) {
  const customer = user.role === "customer";
  const scopeKey = chatScopeKey(user.id, user.role, sites.siteId);
  const welcome = { id: "welcome", role: "assistant", content: customer
    ? "Chào bạn! Mình giúp bạn xem giá, tìm chỗ trống và hướng dẫn đặt trước."
    : `Chào bạn! Mình có thể tóm tắt lưu lượng ngày/tuần, chỗ trống và gợi ý khung trực từ dữ liệu bãi.${user.role === "staff" ? " Tài khoản nhân viên chỉ xem dữ liệu vận hành." : ""}` };
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState(() => { const stored = readAIChat(sessionStorage, scopeKey); return stored.length ? stored : [welcome]; });
  const endRef = useRef(null), inputRef = useRef(null), launcherRef = useRef(null), versionRef = useRef(0), activeRef = useRef(false);
  useEffect(() => { saveAIChat(sessionStorage, scopeKey, messages); }, [messages, scopeKey]);
  useEffect(() => {
    const clear = () => { versionRef.current += 1; activeRef.current = false; setLoading(false); setMessages([welcome]); setQuestion(""); };
    window.addEventListener("parking-ai-clear-chat", clear);
    return () => { versionRef.current += 1; activeRef.current = false; window.removeEventListener("parking-ai-clear-chat", clear); };
  }, [scopeKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: "instant", block: "nearest" }); }, [messages, loading, open]);
  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);
  const close = () => { setOpen(false); requestAnimationFrame(() => launcherRef.current?.focus()); };
  const ask = async (text = question, action = "question") => {
    if (activeRef.current || !text.trim() || !sites.siteId) return;
    const version = ++versionRef.current;
    const token = localStorage.getItem("token");
    activeRef.current = true; setLoading(true); setQuestion("");
    setMessages((old) => [...old, { id: `q-${version}-${Date.now()}`, role: "user", content: text.trim() }]);
    try {
      const request = chatRequest({ role: user.role, siteId: sites.siteId, question: text, action, createKey: requestKey });
      const { data } = await requestAI(api, request.path, request.body);
      if (version !== versionRef.current || token !== localStorage.getItem("token")) return;
      if (typeof data?.content !== "string" || !data.content.trim()) throw new Error("AI chưa trả về nội dung hợp lệ.");
      setMessages((old) => [...old, { id: `a-${version}-${Date.now()}`, role: "assistant", content: data.content }]);
    } catch (error) {
      if (version !== versionRef.current || token !== localStorage.getItem("token")) return;
      setMessages((old) => [...old, { id: `e-${version}-${Date.now()}`, role: "assistant", error: true, content: getErrorMessage(error, "AI chưa sẵn sàng. Hãy thử lại sau; bảng giá và chỗ trống vẫn xem được tại các trang của bãi.") }]);
    } finally {
      if (version === versionRef.current) { activeRef.current = false; setLoading(false); }
    }
  };
  return <div className="chat-widget">
    {open && <section className="chat-window" role="dialog" aria-modal="false" aria-labelledby="parking-chat-title" onKeyDown={event => { if (event.key === "Escape") close(); }}>
      <header className="chat-header"><div className="chat-avatar"><RobotIcon /></div><div><h2 id="parking-chat-title">Trợ lý ParkingAI</h2><p>{customer ? "Hỗ trợ khách hàng" : "Trợ lý quản lý bãi"} · {({ customer: "Customer", manager: "Manager", admin: "Admin", staff: "Staff" })[user.role]}</p></div><button className="chat-close" type="button" aria-label="Đóng trợ lý" onClick={close}><ChatIcon close /></button></header>
      <div className="chat-disclaimer">{customer ? "Không gửi mã thanh toán riêng hoặc mật khẩu." : "Phân tích từ dữ liệu bãi được cấp quyền."}<button type="button" aria-label="Xóa hội thoại" onClick={() => clearAIChat()} style={{ border: 0, background: "transparent", color: "inherit", fontSize: "inherit", textDecoration: "underline", marginLeft: 8 }}>Xóa chat</button></div>
      {!sites.singleSiteMode && sites.sites.length > 1 && <div style={{ padding: "8px 13px" }}><SitePicker sites={sites} label="Bãi đang hỏi" /></div>}
      <div className="chat-messages" role="log" aria-label="Hội thoại ParkingAI" aria-live="polite" aria-relevant="additions text">
        {messages.map(message => <div key={message.id} className={`bubble ${message.role}`} style={message.error ? { background: "#fff0ed", color: "#7c3029" } : undefined}><span className="sr-only">{message.role === "user" ? "Bạn" : "Trợ lý"}: </span>{message.content}</div>)}
        {loading && <div className="bubble assistant" role="status">Đang đọc dữ liệu và tạo câu trả lời…</div>}<div ref={endRef} />
      </div>
      <div className="chat-suggestions">{(customer ? customerActions : internalActions).map(item => <button key={item.label} type="button" disabled={loading || !sites.siteId} onClick={() => void ask(item.label, item.id)}>{item.label}</button>)}</div>
      <form className="chat-compose" onSubmit={event => { event.preventDefault(); void ask(); }}><label className="sr-only" htmlFor="parking-chat-question">Câu hỏi cho trợ lý ParkingAI</label><textarea id="parking-chat-question" ref={inputRef} rows={1} maxLength={2000} placeholder="Nhập câu hỏi…" value={question} disabled={loading} required onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void ask(); } }} /><button type="submit" aria-label="Gửi câu hỏi" disabled={loading || !sites.siteId || !question.trim()}><ChatIcon /></button></form>
    </section>}
    <button ref={launcherRef} className={`chat-launcher ${open ? "is-open" : ""}`} type="button" aria-expanded={open} aria-label={open ? "Thu gọn chatbot" : "Mở trợ lý ParkingAI"} onClick={() => open ? close() : setOpen(true)}>{open ? <ChatIcon close /> : <RobotIcon />}</button>
    {!open && <span className="chat-launcher-label">Hỏi ParkingAI</span>}
  </div>;
}
