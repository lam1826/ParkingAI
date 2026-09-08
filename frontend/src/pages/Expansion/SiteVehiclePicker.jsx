import { useCallback, useEffect, useState } from "react";
import { Autocomplete, TextField } from "@mui/material";
import { items, read, useRemote } from "./shared";

export default function SiteVehiclePicker({ siteId, value, onChange, disabled = false, label = "Xe đã đăng ký khách hàng" }) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 200);
    return () => window.clearTimeout(timer);
  }, [query]);
  const load = useCallback(() => read(`/sites/${siteId}/vehicles`, { q: debounced, limit: 20 }).then(items), [siteId, debounced]);
  const remote = useRemote(load);
  return <Autocomplete options={remote.data || []} value={value || null} onChange={(_, selected) => onChange(selected)} disabled={disabled}
    loading={remote.loading} filterOptions={(options) => options} isOptionEqualToValue={(option, selected) => option.id === selected.id}
    getOptionLabel={(option) => `${option.license_plate} · #${option.id}`} noOptionsText="Chưa tìm thấy xe đã gắn với khách hàng" loadingText="Đang tìm xe…"
    onInputChange={(_, text, reason) => { if (["input", "clear"].includes(reason)) setQuery(text); }}
    renderInput={(params) => <TextField {...params} required label={label} error={Boolean(remote.error)} helperText={remote.error || "Nhập biển số để tìm; hiển thị tối đa 20 kết quả."} />} />;
}
