import { useEffect, useState } from "react";
import { Alert, Box, Typography } from "@mui/material";
import api from "../../services/api";
import { endpoint } from "./shared";
import { normalizedPoint } from "./occupancyPresentation";

const colors = { occupied: "#d97706", empty: "#059669", unknown: "#64748b" };

export default function OccupancyImage({ observationId, regions = [], draft = [], onPoint, label = "Ảnh chỗ đỗ và các vùng được quan sát" }) {
  const [image, setImage] = useState(null);
  useEffect(() => {
    let alive = true, url;
    if (!observationId) return undefined;
    api.get(endpoint(`/vision/observations/${observationId}/image`), { responseType: "blob" }).then((response) => {
      if (!alive) return;
      url = URL.createObjectURL(response.data);
      setImage({ id: observationId, url });
    }).catch(() => { if (alive) setImage({ id: observationId, error: true }); });
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [observationId]);
  if (!observationId) return <Typography color="text.secondary">Chọn ảnh được lưu tại camera này.</Typography>;
  if (image?.id !== observationId) return <Typography role="status">Đang tải ảnh riêng tư…</Typography>;
  if (image.error) return <Alert severity="warning">Ảnh không còn được lưu hoặc không có quyền xem. Làm mới để cập nhật.</Alert>;
  return <Box sx={{ position: "relative", maxWidth: 800, width: "100%", lineHeight: 0 }}>
    <Box component="img" src={image.url} alt={label} sx={{ width: "100%", display: "block", borderRadius: 1 }} />
    <Box component="svg" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label={label} role="img"
      sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", cursor: onPoint ? "crosshair" : "default" }}
      onClick={onPoint ? (event) => { const point = normalizedPoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect()); if (point) onPoint(point); } : undefined}>
      {regions.map((region) => <g key={region.slot_id}>
        <polygon points={region.polygon.map(([x, y]) => `${x * 1000},${y * 1000}`).join(" ")} fill={colors[region.state] || colors.unknown} fillOpacity=".18" stroke={colors[region.state] || colors.unknown} strokeWidth="3" vectorEffect="non-scaling-stroke" />
        <text x={region.polygon[0][0] * 1000 + 5} y={region.polygon[0][1] * 1000 + 32} fill="white" stroke="#0f172a" strokeWidth="4" paintOrder="stroke" fontSize="28">{region.slot_name || `#${region.slot_id}`}</text>
      </g>)}
      {draft.length > 0 && <polyline points={draft.map(([x, y]) => `${x * 1000},${y * 1000}`).join(" ")} fill="none" stroke="#2563eb" strokeWidth="3" vectorEffect="non-scaling-stroke" />}
      {draft.map(([x, y], index) => <circle key={index} cx={x * 1000} cy={y * 1000} r="7" fill="#2563eb" stroke="white" strokeWidth="2" />)}
    </Box>
  </Box>;
}
