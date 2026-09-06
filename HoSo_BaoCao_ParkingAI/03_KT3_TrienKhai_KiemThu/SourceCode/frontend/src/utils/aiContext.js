export const MAX_AI_QUESTION_CHARS = 1000;
const questionPrefix = (label) => label ? `Ngữ cảnh giao diện hiện tại: ${label}. Câu hỏi: ` : "";

export function questionLimit(label) {
  return MAX_AI_QUESTION_CHARS - questionPrefix(label).length;
}

export function buildAIQuestion(question, label) {
  const text = typeof question === "string" ? question.trim() : "";
  if (!text) throw new Error("Vui lòng nhập câu hỏi.");
  if (text.length > questionLimit(label)) throw new Error(`Câu hỏi được nhập tối đa ${questionLimit(label)} ký tự.`);
  return questionPrefix(label) + text;
}

export function readReportContext(report) {
  const unknown = { source: "Chưa ghi nguồn dữ liệu", period: "Chưa ghi kỳ dữ liệu" };
  const firstLine = report?.prompt_used?.split("\n")[0];
  if (!firstLine?.startsWith("PARKINGAI_CONTEXT ")) return unknown;
  try {
    const context = JSON.parse(firstLine.slice("PARKINGAI_CONTEXT ".length));
    const sources = { database: "Dữ liệu bãi xe", custom: "Dữ liệu cung cấp", mixed: "Dữ liệu bãi xe và dữ liệu cung cấp" };
    const formatDate = (date) => /^\d{4}-\d{2}-\d{2}$/.test(date ?? "") ? date.split("-").reverse().join("/") : null;
    const start = formatDate(context.start_date);
    const end = formatDate(context.end_date);
    return { source: sources[context.source] || unknown.source,
      period: start && end ? (start === end ? start : `${start} – ${end}`) : unknown.period };
  } catch { return unknown; }
}
