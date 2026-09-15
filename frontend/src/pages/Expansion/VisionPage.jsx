import { useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { prepareCameraPhoto } from "./imageUpload";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { AuthContext } from "../../context/AuthContext";
import { cameraHealthText, cameraWriteBody, canManageCameras } from "./visionCameraState";
import api from "../../services/api";
import { Workspace, Section, Records, useSites, useRemote, useAction, read, send, items, endpoint, dateTime, requestKey, formLayout, SitePicker, combineRemotes, refreshAll } from "./shared";

const newCamera = { name: "Camera điện thoại", direction: "entry", retention_hours: 24, is_active: true };

function ObservationImage({ observation }) {
  const [image, setImage] = useState({ src: "", error: "", id: null });
  useEffect(() => {
    let alive = true;
    let objectUrl;
    api.get(endpoint(`/vision/observations/${observation.id}/image`), { responseType: "blob" }).then((response) => {
      if (!alive) return;
      objectUrl = URL.createObjectURL(response.data);
      setImage({ src: objectUrl, error: "", id: observation.id });
    }).catch(() => { if (alive) setImage({ src: "", error: "Không tải được ảnh hoặc ảnh đã hết hạn lưu.", id: observation.id }); });
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [observation.id]);
  if (image.id !== observation.id) return <Typography>Đang tải ảnh…</Typography>;
  if (image.error) return <Alert severity="warning">{image.error}</Alert>;
  return <Stack spacing={2}><Box sx={{ position: "relative", lineHeight: 0, maxWidth: 800, width: "100%", mx: "auto" }}>
    <Box component="img" src={image.src} alt="Ảnh phương tiện để kiểm tra biển số" sx={{ width: "100%", height: "auto", borderRadius: 1 }} />
    {(observation.detections || []).map((detection, index) => {
      const [x1, y1, x2, y2] = detection.box;
      if (!observation.image_width || !observation.image_height) return null;
      return <Box key={index} sx={{ position: "absolute", left: `${x1 / observation.image_width * 100}%`, top: `${y1 / observation.image_height * 100}%`, width: `${(x2 - x1) / observation.image_width * 100}%`, height: `${(y2 - y1) / observation.image_height * 100}%`, border: "2px solid", borderColor: "success.main", pointerEvents: "none" }} />;
    })}
  </Box>
    {(observation.detections || []).map((detection, index) => {
      if (!Array.isArray(detection.box) || detection.box.length !== 4) return null;
      const [x1, y1, x2, y2] = detection.box;
      const width = x2 - x1, height = y2 - y1;
      if (width <= 0 || height <= 0 || !observation.image_width) return null;
      return <Box key={index}>
        <Typography variant="subtitle2">Vùng biển số {index + 1} · {detection.plate || "Chưa đọc được chữ"}</Typography>
        <Box sx={{ width: "100%", maxWidth: 360, mt: 1 }}><svg viewBox={`${x1} ${y1} ${width} ${height}`} width="100%" role="img" aria-label={`Ảnh cắt vùng biển số ${index + 1}`}><image href={image.src} width={observation.image_width} height={observation.image_height} /></svg></Box>
        <Typography variant="body2">Điểm phát hiện: {detection.detector_confidence?.toFixed(3) ?? "Chưa có"} · Điểm đọc chữ: {detection.ocr_confidence?.toFixed(3) ?? "Chưa có"}</Typography>
        {detection.text_lines?.length > 0 && <Typography variant="body2">Chữ đọc được: {detection.text_lines.join(" / ")}</Typography>}
      </Box>;
    })}
    {!!observation.detections?.length && <Typography variant="body2" color="text.secondary">Điểm do model trả về dùng để tham khảo, không phải tỷ lệ đọc đúng đã kiểm chứng. Kiểm tra ảnh rồi sửa biển số ở dưới nếu cần.</Typography>}
  </Stack>;
}

export default function VisionPage() {
  const { user } = useContext(AuthContext);
  const navigate = useNavigate();
  const sites = useSites();
  const [cameraId, setCameraId] = useState("");
  const [selected, setSelected] = useState(null);
  const [plate, setPlate] = useState("");
  const [cameraForm, setCameraForm] = useState(newCamera);
  const [editingCamera, setEditingCamera] = useState(null);
  const [cameraOperation, setCameraOperation] = useState(null);
  const [privateToken, setPrivateToken] = useState(null);
  const [copyNotice, setCopyNotice] = useState("");
  const site = sites.sites.find((row) => String(row.id) === String(sites.siteId));
  const canManage = canManageCameras(user?.role, site?.role);
  const loadCameras = useCallback(() => sites.siteId ? read("/cameras", { site_id: sites.siteId }).then(items) : Promise.resolve([]), [sites.siteId]);
  const cameras = useRemote(loadCameras);
  const reloadCameras = cameras.reload;
  const load = useCallback(async () => {
    const status = await read("/vision/status");
    if (!sites.siteId) return { status, observations: [] };
    const observations = await read("/vision/observations", { site_id: sites.siteId });
    return { status, observations: items(observations) };
  }, [sites.siteId]);
  const remote = useRemote(load);
  const action = useAction(refreshAll(remote, cameras));
  const data = remote.data;
  const activeCameras = (cameras.data || []).filter((camera) => camera.is_active);
  const effectiveCamera = activeCameras.some((camera) => String(camera.id) === String(cameraId)) ? cameraId : cameraId ? "" : activeCameras[0]?.id || "";
  const pageRemote = { ...combineRemotes(remote, cameras), error: remote.error || cameras.error };
  useEffect(() => {
    const timer = window.setInterval(() => { if (!document.hidden && !action.busy && sites.siteId) void reloadCameras(); }, 15000);
    return () => window.clearInterval(timer);
  }, [reloadCameras, sites.siteId, action.busy]);
  useEffect(() => {
    setPrivateToken(null); setCopyNotice(""); setCameraOperation(null); setEditingCamera(null); setCameraForm(newCamera);
  }, [sites.siteId, user?.id, canManage]);
  const current = selected?.site_id === Number(sites.siteId) ? data?.observations.find((row) => row.id === selected.id) || selected : null;
  const choose = (row) => { setSelected(row); setPlate(row.confirmed_plate || row.suggested_plate || ""); };
  const upload = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const payload = new FormData();
    payload.append("camera_id", effectiveCamera);
    payload.append("event_id", requestKey());
    void action.run(async () => {
      payload.append("file", await prepareCameraPhoto(file));
      return (await api.post(endpoint("/vision/observations"), payload, { headers: { "Content-Type": undefined }, timeout: 120000 })).data;
    }, "Đã tiếp nhận ảnh. Kiểm tra kết quả trước khi xác nhận biển số.", choose);
  };
  const saveCamera = (event) => {
    event.preventDefault();
    if (!canManage) return;
    void action.run(() => {
      const body = cameraWriteBody(cameraForm, { siteId: sites.siteId, editing: Boolean(editingCamera) });
      return editingCamera ? api.patch(endpoint(`/cameras/${editingCamera.id}`), body) : send("/cameras", body);
    }, editingCamera ? "Đã cập nhật camera." : "Đã thêm camera.", () => { setEditingCamera(null); setCameraForm(newCamera); setPrivateToken(null); });
  };
  const executeCameraOperation = () => {
    if (!canManage || !cameraOperation) return;
    const { camera, kind } = cameraOperation;
    setPrivateToken(null); setCopyNotice("");
    void action.run(async () => {
      if (kind === "disable") return api.delete(endpoint(`/cameras/${camera.id}`));
      const result = await send(`/cameras/${camera.id}/edge-token`);
      if (result.camera_id !== camera.id || typeof result.token !== "string" || result.token.length < 32) throw new Error("Chưa nhận được khóa camera hợp lệ. Cập nhật trạng thái trước khi cấp lại.");
      return result;
    }, kind === "disable" ? "Đã ngừng camera và thu hồi khóa gửi ảnh." : "Đã cấp khóa mới; khóa cũ hết hiệu lực.", (result) => {
      setCameraOperation(null);
      if (kind === "rotate") setPrivateToken({ value: result.token, cameraId: camera.id, name: camera.name, siteId: Number(sites.siteId) });
    });
  };
  const copyToken = async () => {
    if (!privateToken || !canManage) return;
    try { await navigator.clipboard.writeText(privateToken.value); setCopyNotice("Đã sao chép khóa. Dán vào cấu hình thiết bị gửi ảnh."); }
    catch { setCopyNotice("Không thể truy cập bảng nhớ tạm. Kiểm tra quyền sao chép của trình duyệt rồi thử lại."); }
  };
  return <Workspace title="Camera & biển số" description="Dùng điện thoại chụp phương tiện hoặc tải ảnh lên. Kiểm tra biển số trước khi xử lý xe vào/ra." remote={pageRemote} action={action}>
    {sites.error && <Alert severity="error">{sites.error}</Alert>}
    <Box sx={formLayout}><SitePicker sites={sites} disabled={action.busy} onChange={(value) => { sites.setSiteId(value); setSelected(null); setCameraId(""); }} />
      <TextField select label="Camera / làn" disabled={action.busy || cameras.loading} value={effectiveCamera} onChange={(event) => setCameraId(event.target.value)}>{activeCameras.map((camera) => <MenuItem key={camera.id} value={camera.id}>{camera.name} · {camera.direction === "entry" ? "Xe vào" : "Xe ra"}</MenuItem>)}</TextField></Box>
    {data?.status && !data.status.available && <Alert severity="info">Nhận diện tự động chưa sẵn sàng. Bạn vẫn có thể lưu ảnh và nhập biển số để trình diễn quy trình. {data.status.reason}</Alert>}
    <Section title="Chụp và nhận diện" description="Chụp rõ toàn bộ biển số, giữ một phần xe xung quanh và tránh chói sáng. Ảnh chỉ được xem bởi người có quyền tại bãi và được xóa theo thời hạn lưu.">
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} useFlexGap>
        <Button component="label" variant="contained" startIcon={<PhotoCameraIcon />} disabled={action.busy || cameras.loading || !effectiveCamera}>Chụp bằng điện thoại<input hidden type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={upload} /></Button>
        <Button component="label" variant="outlined" startIcon={<UploadFileIcon />} disabled={action.busy || cameras.loading || !effectiveCamera}>Chọn ảnh từ máy<input hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={upload} /></Button>
      </Stack>
      {action.busy && <Typography role="status">Đang xử lý ảnh hoặc lưu kết quả…</Typography>}
      {!activeCameras.length && <Typography color="text.secondary">Chưa có camera đang hoạt động. Quản lý có thể thêm hoặc bật lại camera bên dưới.</Typography>}
    </Section>
    {current && <Section title="Kiểm tra kết quả" description={`Ảnh nhận lúc ${dateTime(current.observed_at)} · ${current.ocr_status === "recognized" ? "Đã có kết quả nhận diện" : "Cần nhập hoặc kiểm tra thủ công"}`}>
      {current.ocr_status === "no_plate" && <Alert severity="info">Chưa tìm được biển số trong ảnh. Chụp lại rõ biển và phần xe xung quanh, hoặc nhập biển số đã kiểm tra ở dưới.</Alert>}
      <ObservationImage observation={current} />
      <Box sx={formLayout}><TextField label="Biển số đã kiểm tra" value={plate} onChange={(event) => setPlate(event.target.value.toUpperCase())} inputProps={{ maxLength: 20 }} />
        <Button variant="contained" disabled={action.busy || !plate.trim() || current.review_status !== "pending"} onClick={() => action.run(() => send(`/vision/observations/${current.id}/review`, { decision: "accept", license_plate: plate }), "Đã xác nhận biển số. Tiếp tục xử lý xe tại bãi.", (result) => { setSelected(result); navigate(`/sites?site=${current.site_id}&plate=${encodeURIComponent(plate)}&action=${result.next_action?.kind || "check_in"}`); })}>Xác nhận và xử lý xe</Button>
        <Button variant="outlined" disabled={action.busy || current.review_status !== "pending"} onClick={() => action.run(() => send(`/vision/observations/${current.id}/review`, { decision: "reject" }), "Đã từ chối ảnh này.", setSelected)}>Không sử dụng ảnh</Button>
      </Box>
      <Alert severity="info">Xác nhận biển số chưa cho xe ra và chưa thu tiền. Bước tiếp theo dùng quy trình vào/ra của bãi.</Alert>
    </Section>}
    <Section title="Ảnh gần đây"><Records rows={data?.observations} columns={[{ key: "observed_at", label: "Thời gian", render: (row) => dateTime(row.observed_at) }, { key: "suggested_plate", label: "Biển dự đoán" }, { key: "confirmed_plate", label: "Biển đã kiểm tra" }, { key: "review_status", label: "Tình trạng", render: (row) => ({ pending: "Chờ kiểm tra", accepted: "Đã xác nhận", rejected: "Đã từ chối" })[row.review_status] || row.review_status }, { key: "action", label: "Ảnh", render: (row) => <Stack direction="row" spacing={1}><Button size="small" onClick={() => choose(row)}>Xem ảnh</Button>{canManage && <Button size="small" color="error" disabled={action.busy} onClick={() => action.run(() => api.delete(endpoint(`/vision/observations/${row.id}`)), "Đã xóa ảnh.", () => { if (selected?.id === row.id) setSelected(null); })}>Xóa</Button>}</Stack> }]} /></Section>
    <Section title="Camera tại bãi" description="Thông tin nhận ảnh tự cập nhật mỗi 15 giây khi mở trang. Có ảnh mới chỉ phản ánh lần gửi ảnh gần nhất, không xác nhận camera vật lý đang trực tuyến.">
      <Records rows={cameras.data || []} columns={[
        { key: "name", label: "Camera / làn" },
        { key: "direction", label: "Hướng", render: (row) => row.direction === "entry" ? "Xe vào" : "Xe ra" },
        { key: "health", label: "Nhận ảnh", render: cameraHealthText },
        { key: "last_received_at", label: "Ảnh gần nhất", render: (row) => dateTime(row.last_received_at) },
        { key: "retention_hours", label: "Lưu ảnh", render: (row) => `${row.retention_hours} giờ` },
        { key: "edge_enabled", label: "Khóa gửi ảnh", render: (row) => row.edge_enabled ? "Đã cấp khóa" : "Chưa có khóa" },
        ...(canManage ? [{ key: "actions", label: "Quản lý", render: (row) => <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          <Button size="small" disabled={action.busy} onClick={() => { setEditingCamera(row); setCameraForm({ name: row.name, direction: row.direction, retention_hours: row.retention_hours, is_active: row.is_active }); }}>Sửa</Button>
          <Button size="small" disabled={action.busy || !row.is_active} onClick={() => setCameraOperation({ camera: row, kind: "rotate" })}>{row.edge_enabled ? "Đổi khóa gửi ảnh" : "Cấp khóa gửi ảnh"}</Button>
          <Button size="small" color="error" disabled={action.busy || !row.is_active} onClick={() => setCameraOperation({ camera: row, kind: "disable" })}>Ngừng camera và thu hồi khóa</Button>
        </Stack> }] : []),
      ]} empty="Chưa có camera tại bãi này." />
    </Section>
    {canManage && <Section title={editingCamera ? `Sửa camera — ${editingCamera.name}` : "Thêm camera"} description="Tên làn, hướng nhận xe và thời hạn lưu ảnh áp dụng cho camera này.">
      <Box component="form" onSubmit={saveCamera}>
        <Box component="fieldset" disabled={action.busy} sx={{ ...formLayout, border: 0, p: 0, m: 0, minWidth: 0 }}>
          <TextField required label="Tên camera" value={cameraForm.name} onChange={(event) => setCameraForm((old) => ({ ...old, name: event.target.value }))} inputProps={{ maxLength: 100 }} />
          <TextField select label="Hướng xử lý" value={cameraForm.direction} onChange={(event) => setCameraForm((old) => ({ ...old, direction: event.target.value }))}><MenuItem value="entry">Xe vào</MenuItem><MenuItem value="exit">Xe ra</MenuItem></TextField>
          <TextField required type="number" label="Thời gian lưu ảnh (giờ)" value={cameraForm.retention_hours} onChange={(event) => setCameraForm((old) => ({ ...old, retention_hours: event.target.value }))} inputProps={{ min: 1, max: 72, step: 1 }} helperText="Từ 1 đến 72 giờ. Giảm thời hạn cũng áp dụng cho ảnh đã nhận." />
          <FormControlLabel control={<Checkbox checked={cameraForm.is_active} onChange={(event) => setCameraForm((old) => ({ ...old, is_active: event.target.checked }))} />} label="Camera đang hoạt động" />
        </Box>
        {editingCamera?.edge_enabled && !cameraForm.is_active && <Alert severity="warning" sx={{ mt: 2 }}>Ngừng camera sẽ thu hồi khóa gửi ảnh. Bật lại camera không khôi phục khóa cũ.</Alert>}
        <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 2, flexWrap: "wrap" }}>
          <Button type="submit" variant="contained" disabled={action.busy || !sites.siteId}>{editingCamera ? "Lưu camera" : "Thêm camera"}</Button>
          {editingCamera && <Button type="button" disabled={action.busy} onClick={() => { setEditingCamera(null); setCameraForm(newCamera); }}>Hủy sửa</Button>}
        </Stack>
      </Box>
    </Section>}
    {canManage && <Dialog open={Boolean(cameraOperation)} onClose={() => { if (!action.busy) setCameraOperation(null); }} maxWidth="sm" fullWidth aria-labelledby="camera-operation-title">
      <DialogTitle id="camera-operation-title">{cameraOperation?.kind === "disable" ? "Ngừng camera và thu hồi khóa" : "Cấp khóa gửi ảnh mới"}</DialogTitle>
      <DialogContent><Stack spacing={2}>
        <Typography fontWeight={700}>{cameraOperation?.camera.name}</Typography>
        <Typography>{cameraOperation?.kind === "disable" ? "Camera sẽ ngừng nhận ảnh. Khóa hiện tại hết hiệu lực; ảnh và lịch sử đã có vẫn giữ theo thời hạn lưu." : "Khóa hiện tại sẽ hết hiệu lực ngay. Khóa mới chỉ được trả về lần này; sao chép vào thiết bị gửi ảnh trước khi đóng."}</Typography>
        {action.error && <Alert severity="error">{action.error}</Alert>}
      </Stack></DialogContent>
      <DialogActions><Button disabled={action.busy} onClick={() => setCameraOperation(null)}>Quay lại</Button><Button variant="contained" color={cameraOperation?.kind === "disable" ? "error" : "primary"} disabled={action.busy} onClick={executeCameraOperation}>{cameraOperation?.kind === "disable" ? "Ngừng và thu hồi" : "Cấp khóa mới"}</Button></DialogActions>
    </Dialog>}
    {canManage && privateToken?.siteId === Number(sites.siteId) && <Dialog open onClose={() => { setPrivateToken(null); setCopyNotice(""); }} maxWidth="sm" fullWidth aria-labelledby="camera-token-title">
      <DialogTitle id="camera-token-title">Khóa gửi ảnh — {privateToken.name}</DialogTitle>
      <DialogContent><Stack spacing={2}>
        <Alert severity="info">Khóa chỉ được trả về lần này. Sao chép vào thiết bị gửi ảnh. Đóng hộp thoại sẽ xóa khóa khỏi giao diện.</Alert>
        <Typography>Mã camera: {privateToken.cameraId}</Typography>
        <TextField label="Khóa camera mới" type="password" value={privateToken.value} autoComplete="off" slotProps={{ input: { readOnly: true }, htmlInput: { spellCheck: false } }} />
        <Button variant="contained" onClick={() => void copyToken()}>Sao chép khóa</Button>
        {copyNotice && <Typography role="status">{copyNotice}</Typography>}
      </Stack></DialogContent>
      <DialogActions><Button onClick={() => { setPrivateToken(null); setCopyNotice(""); }}>Đóng và xóa khóa khỏi màn hình</Button></DialogActions>
    </Dialog>}
  </Workspace>;
}
