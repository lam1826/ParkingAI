import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import api from "../../services/api";
import { getErrorMessage } from "../../utils/errorMessage";
import formatCurrency from "../../utils/formatCurrency";
import { formatBusinessTimestamp } from "../../utils/formatDate";
import { requestId } from "../../utils/requestId";

export const endpoint = (path) => `/api/v2${path}`;
export const read = async (path, params) => (await api.get(endpoint(path), { params })).data;
export const send = async (path, body = {}) => (await api.post(endpoint(path), body)).data;
export const items = (data) => Array.isArray(data) ? data : data?.items || [];
export const money = (value) => `${formatCurrency(value ?? 0)} ₫`;
export const dateTime = (value) => value ? formatBusinessTimestamp(value) : "—";
export const dateOnly = (value) => value ? String(value).slice(0, 10).split("-").reverse().join("/") : "—";
export const requestKey = requestId;
export const formLayout = { display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))" }, gap: 2, alignItems: "start" };

export function useRemote(loader) {
  const generation = useRef(0);
  const activeLoader = useRef(loader);
  const [result, setResult] = useState({ loader: null, value: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    const requestedLoader = activeLoader.current;
    const turn = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const result = await requestedLoader();
      if (generation.current === turn) setResult({ loader: requestedLoader, value: result });
      return result;
    } catch (failure) {
      if (generation.current === turn) {
        setResult({ loader: requestedLoader, value: null });
        setError(getErrorMessage(failure, "Không tải được dữ liệu. Vui lòng thử lại."));
      }
      return null;
    } finally {
      if (generation.current === turn) setLoading(false);
    }
  }, []);
  useEffect(() => {
    // A mutation started before a filter change may call its captured reload.
    // Keep reload stable and always refresh the currently committed scope.
    activeLoader.current = loader;
    void reload();
    return () => { generation.current += 1; };
  }, [loader, reload]);
  const current = result.loader === loader;
  return { data: current ? result.value : null, loading: loading || !current, error: current ? error : "", reload };
}

export function useAction(reload) {
  const active = useRef(false);
  const mounted = useRef(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const run = async (operation, success = "Đã lưu thay đổi.", onSuccess) => {
    if (active.current) return;
    active.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await operation();
      if (!mounted.current) return;
      onSuccess?.(result);
      setNotice(success);
      await reload?.();
    } catch (failure) {
      if (mounted.current) setError(getErrorMessage(failure, "Chưa xác nhận được kết quả. Làm mới để kiểm tra trước khi gửi lại."));
    } finally {
      active.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const notify = (success) => {
    if (mounted.current) { setError(""); setNotice(success); }
  };
  return { run, busy, error, notice, notify };
}

/** Page/filter state for one paged list: any filter change returns to the first page. */
export function usePage(initialFilters = {}, size = 25) {
  const [state, setState] = useState({ page: 0, filters: initialFilters });
  const setPage = useCallback((page) => setState((old) => ({ ...old, page })), []);
  const setFilters = useCallback((update) => setState((old) => ({ page: 0, filters: typeof update === "function" ? update(old.filters) : { ...old.filters, ...update } })), []);
  return { page: state.page, filters: state.filters, size, params: { limit: size, offset: state.page * size }, setPage, setFilters };
}

/** Reload several independent sections after one mutation; each keeps its own late-result guard. */
export function refreshAll(...remotes) {
  return () => Promise.all(remotes.map((remote) => remote?.reload?.()));
}

/** One section loads, fails and retries on its own; other sections keep their data. */
export function RemoteSection({ remote, title, description, actions, children, empty }) {
  return <Section title={title} description={description} actions={actions}>
    {remote.error && <Alert severity="error" action={<Button color="inherit" size="small" startIcon={<RefreshIcon />} onClick={remote.reload} disabled={remote.loading}>Thử lại</Button>}>{remote.error}</Alert>}
    {remote.loading && <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center" }} role="status"><CircularProgress size={18} /><Typography variant="body2">Đang tải {title ? title.toLowerCase() : "dữ liệu"}…</Typography></Stack>}
    {remote.data != null ? children(remote.data) : (!remote.loading && !remote.error && empty)}
  </Section>;
}

const loadSites = () => read("/sites").then(items);
export function useSites() {
  const remote = useRemote(loadSites);
  const [choice, setChoice] = useState("");
  const sites = remote.data || [];
  const siteId = sites.some((site) => String(site.id) === String(choice)) ? choice : sites[0]?.id || "";
  return { ...remote, sites, siteId, setSiteId: setChoice };
}

/** `remote` may be one useRemote result or a synthetic {reload, loading, error} that spans sections. */
export function Workspace({ title, description, remote, action, actions = [], children, tools }) {
  const feedback = action ? [action, ...actions] : actions;
  return <Stack spacing={3} sx={{ minWidth: 0, maxWidth: 1440, mx: "auto" }}>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} useFlexGap sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
      <Box><Typography variant="h4" component="h1">{title}</Typography><Typography color="text.secondary" sx={{ mt: 1, maxWidth: "75ch" }}>{description}</Typography></Box>
      <Stack direction="row" spacing={1} useFlexGap>{tools}<Button variant="outlined" startIcon={<RefreshIcon />} onClick={remote.reload} disabled={remote.loading || feedback.some((item) => item?.busy)}>Làm mới</Button></Stack>
    </Stack>
    {remote.error && <Alert severity="error">{remote.error}</Alert>}
    {feedback.map((item, index) => item?.error && <Alert key={`error-${index}`} severity="error">{item.error}</Alert>)}
    {feedback.map((item, index) => item?.notice && <Alert key={`notice-${index}`} severity="success" role="status">{item.notice}</Alert>)}
    {remote.loading && <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center" }} role="status"><CircularProgress size={20} /><Typography>Đang tải dữ liệu…</Typography></Stack>}
    {children}
  </Stack>;
}

/** Combine sections for the page header: loading while any section loads; errors stay per section. */
export function combineRemotes(...remotes) {
  return { reload: refreshAll(...remotes), loading: remotes.some((remote) => remote.loading), error: "" };
}

export function Section({ title, description, children, actions }) {
  return <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }}>
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ justifyContent: "space-between" }}><Box><Typography variant="h6" component="h2">{title}</Typography>{description && <Typography color="text.secondary" sx={{ mt: 0.5 }}>{description}</Typography>}</Box>{actions}</Stack>
      {children}
    </Stack>
  </Paper>;
}

const labels = { pending: "Chờ xử lý", approved: "Đã duyệt", rejected: "Từ chối", paid: "Đã thanh toán mô phỏng", fulfilled: "Đã cấp vé", completed: "Hoàn tất", failed: "Thất bại", cancelled: "Đã hủy", expired: "Hết hạn", confirmed: "Đã đặt", arrived: "Đã đến", active: "Đang hiệu lực", waiting: "Đang chờ", offered: "Đã có chỗ", review: "Cần đối soát", needs_review: "Cần đối soát", refunded: "Đã hoàn mô phỏng" };
export function StateChip({ value }) {
  const good = ["paid", "fulfilled", "completed", "approved", "active", "arrived"].includes(value);
  return <Chip size="small" variant="outlined" color={good ? "success" : ["failed", "rejected"].includes(value) ? "error" : "default"} label={labels[value] || value || "—"} />;
}

export function Records({ rows = [], columns, empty = "Chưa có dữ liệu." }) {
  if (!rows.length) return <Typography color="text.secondary" sx={{ py: 3 }}>{empty}</Typography>;
  return <TableContainer sx={{ maxWidth: "100%" }}><Table size="small"><TableHead><TableRow>{columns.map((col) => <TableCell key={col.key} sx={{ whiteSpace: "nowrap", fontWeight: 700 }}>{col.label}</TableCell>)}</TableRow></TableHead><TableBody>{rows.map((row, index) => <TableRow key={row.id ?? index} hover>{columns.map((col) => <TableCell key={col.key} sx={{ py: 1.5, minWidth: col.minWidth, fontVariantNumeric: "tabular-nums" }}>{col.render ? col.render(row) : row[col.key] ?? "—"}</TableCell>)}</TableRow>)}</TableBody></Table></TableContainer>;
}

export function PageControls({ page, count, onChange, busy, size = 50 }) {
  return <Stack direction="row" spacing={2} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}><Button disabled={busy || page === 0} onClick={() => onChange(page - 1)}>Trang trước</Button><Typography>Trang {page + 1}</Typography><Button disabled={busy || count < size} onClick={() => onChange(page + 1)}>Trang sau</Button></Stack>;
}
