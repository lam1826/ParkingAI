// ParkingSession timestamps là naive business-local (Asia/Ho_Chi_Minh), còn
// ngày vé tháng là YYYY-MM-DD. Không được giao cả hai cho Date parser mặc
// định vì kết quả sẽ phụ thuộc timezone của browser.

const BUSINESS_TIME_ZONE = "Asia/Ho_Chi_Minh";
const BUSINESS_OFFSET = "+07:00"; // Việt Nam không dùng DST
const FALLBACK = "—";
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const NAIVE_DATE_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?$/;
const HAS_EXPLICIT_ZONE = /(?:[Zz]|[+-]\d{2}:?\d{2}|[+-]\d{2})$/;

const partsFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: BUSINESS_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function validDateOnlyParts(value) {
  const match = typeof value === "string" ? value.trim().match(DATE_ONLY) : null;
  if (!match) return null;
  const [, year, month, day] = match;
  const instant = new Date(`${year}-${month}-${day}T00:00:00Z`);
  if (
    Number.isNaN(instant.getTime())
    || instant.getUTCFullYear() !== Number(year)
    || instant.getUTCMonth() + 1 !== Number(month)
    || instant.getUTCDate() !== Number(day)
  ) {
    return null;
  }
  return { year, month, day };
}

function toBusinessInstant(value) {
  if (value instanceof Date) return value;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const normalized = trimmed.replace(" ", "T");
  if (NAIVE_DATE_TIME.test(trimmed)) return new Date(`${normalized}${BUSINESS_OFFSET}`);
  return new Date(HAS_EXPLICIT_ZONE.test(normalized) ? normalized : `${normalized}T00:00:00${BUSINESS_OFFSET}`);
}

function instantParts(value) {
  const instant = toBusinessInstant(value);
  if (!instant || Number.isNaN(instant.getTime())) return null;
  const parts = partsFormatter.formatToParts(instant);
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

export function formatBusinessDateOnly(value, fallback = FALLBACK) {
  const dateOnly = validDateOnlyParts(value);
  if (dateOnly) return `${dateOnly.day}/${dateOnly.month}/${dateOnly.year}`;
  const parts = instantParts(value);
  return parts ? `${parts.day}/${parts.month}/${parts.year}` : fallback;
}

export function formatBusinessTimestamp(value, fallback = FALLBACK) {
  const parts = instantParts(value);
  return parts
    ? `${parts.hour}:${parts.minute}:${parts.second} - ${parts.day}/${parts.month}/${parts.year}`
    : fallback;
}

export default function formatDate(value, pattern = "DD/MM/YYYY") {
  return pattern.includes("HH")
    ? formatBusinessTimestamp(value)
    : formatBusinessDateOnly(value);
}
