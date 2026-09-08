import { useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { prepareCameraPhoto } from "./imageUpload";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { AuthContext } from "../../context/AuthContext";
import { hasMinimumRole } from "../../constants/roles";
import api from "../../services/api";
import { Workspace, Section, Records, useSites, useRemote, useAction, read, send, items, endpoint, dateTime, requestKey, formLayout } from "./shared";

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
  return <Box sx={{ position: "relative", lineHeight: 0, maxWidth: 800, width: "100%", mx: "auto" }}>
    <Box component="img" src={image.src} alt="Ảnh phương tiện để kiểm tra biển số" sx={{ width: "100%", height: "auto", borderRadius: 1 }} />
    {(observation.detections || []).map((detection, index) => {
      const [x1, y1, x2, y2] = detection.box;
      if (!observation.image_width || !observation.image_height) return null;
      return <Box key={index} sx={{ position: "absolute", left: `${x1 / observation.image_width * 100}%`, top: `${y1 / observation.image_height * 100}%`, width: `${(x2 - x1) / observation.image_width * 100}%`, height: `${(y2 - y1) / observation.image_height * 100}%`, border: "2px solid", borderColor: "success.main", pointerEvents: "none" }} />;
    })}
  </Box>;
}

export default function VisionPage() {
  const { user } = useContext(AuthContext);
  const navigate = useNavigate();
  const sites = useSites();
  const [cameraId, setCameraId] = useState("");
  const [selected, setSelected] = useState(null);
  const [plate, setPlate] = useState("");
  const [cameraForm, setCameraForm] = useState({ name: "Camera điện thoại", direction: "entry" });
  const load = useCallback(async () => {
    const status = await read("/vision/status");
    if (!sites.siteId) return { status, cameras: [], observations: [] };
    const [cameras, observations] = await Promise.all([read("/cameras", { site_id: sites.siteId }), read("/vision/observations", { site_id: sites.siteId })]);
    return { status, cameras: items(cameras).filter((camera) => camera.is_active), observations: items(observations) };
  }, [sites.siteId]);
  const remote = useRemote(load);
  const action = useAction(remote.reload);
  const data = remote.data;
  const effectiveCamera = data?.cameras.some((camera) => String(camera.id) === String(cameraId)) ? cameraId : data?.cameras[0]?.id || "";
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
  return <Workspace title="Camera & biển số" description="Dùng điện thoại chụp phương tiện hoặc tải ảnh lên. Kiểm tra biển số trước khi xử lý xe vào/ra." remote={remote} action={action}>
    {sites.error && <Alert severity="error">{sites.error}</Alert>}
    <Box sx={formLayout}><TextField select label="Bãi xe" disabled={action.busy} value={sites.siteId} onChange={(event) => { sites.setSiteId(event.target.value); setSelected(null); }}>{sites.sites.map((site) => <MenuItem key={site.id} value={site.id}>{site.name}</MenuItem>)}</TextField>
      <TextField select label="Camera / làn" disabled={action.busy || remote.loading} value={effectiveCamera} onChange={(event) => setCameraId(event.target.value)}>{data?.cameras.map((camera) => <MenuItem key={camera.id} value={camera.id}>{camera.name} · {camera.direction === "entry" ? "Xe vào" : "Xe ra"}</MenuItem>)}</TextField></Box>
    {data?.status && !data.status.available && <Alert severity="info">Nhận diện tự động chưa sẵn sàng. Bạn vẫn có thể lưu ảnh và nhập biển số để trình diễn quy trình. {data.status.reason}</Alert>}
    <Section title="Chụp và nhận diện" description="Đưa toàn bộ biển số vào ảnh, tránh chói sáng. Ảnh chỉ được xem bởi người có quyền tại bãi và được xóa theo thời hạn lưu.">
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} useFlexGap>
        <Button component="label" variant="contained" startIcon={<PhotoCameraIcon />} disabled={action.busy || remote.loading || !effectiveCamera}>Chụp bằng điện thoại<input hidden type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={upload} /></Button>
        <Button component="label" variant="outlined" startIcon={<UploadFileIcon />} disabled={action.busy || remote.loading || !effectiveCamera}>Chọn ảnh từ máy<input hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={upload} /></Button>
      </Stack>
      {action.busy && <Typography role="status">Đang xử lý ảnh hoặc lưu kết quả…</Typography>}
      {!data?.cameras.length && <Typography color="text.secondary">Chưa có camera tại bãi. Quản lý tạo một camera điện thoại bên dưới để bắt đầu.</Typography>}
    </Section>
    {current && <Section title="Kiểm tra kết quả" description={`Ảnh nhận lúc ${dateTime(current.observed_at)} · ${current.ocr_status === "recognized" ? "Đã có kết quả nhận diện" : "Cần nhập hoặc kiểm tra thủ công"}`}>
      <ObservationImage observation={current} />
      <Box sx={formLayout}><TextField label="Biển số đã kiểm tra" value={plate} onChange={(event) => setPlate(event.target.value.toUpperCase())} inputProps={{ maxLength: 20 }} />
        <Button variant="contained" disabled={action.busy || !plate.trim() || current.review_status !== "pending"} onClick={() => action.run(() => send(`/vision/observations/${current.id}/review`, { decision: "accept", license_plate: plate }), "Đã xác nhận biển số. Tiếp tục xử lý xe tại bãi.", (result) => { setSelected(result); navigate(`/sites?site=${current.site_id}&plate=${encodeURIComponent(plate)}&action=${result.next_action?.kind || "check_in"}`); })}>Xác nhận và xử lý xe</Button>
        <Button variant="outlined" disabled={action.busy || current.review_status !== "pending"} onClick={() => action.run(() => send(`/vision/observations/${current.id}/review`, { decision: "reject" }), "Đã từ chối ảnh này.", setSelected)}>Không sử dụng ảnh</Button>
      </Box>
      <Alert severity="info">Xác nhận biển số chưa cho xe ra và chưa thu tiền. Bước tiếp theo dùng quy trình vào/ra của bãi.</Alert>
    </Section>}
    <Section title="Ảnh gần đây"><Records rows={data?.observations} columns={[{ key: "observed_at", label: "Thời gian", render: (row) => dateTime(row.observed_at) }, { key: "suggested_plate", label: "Biển dự đoán" }, { key: "confirmed_plate", label: "Biển đã kiểm tra" }, { key: "review_status", label: "Tình trạng", render: (row) => ({ pending: "Chờ kiểm tra", accepted: "Đã xác nhận", rejected: "Đã từ chối" })[row.review_status] || row.review_status }, { key: "action", label: "Ảnh", render: (row) => <Button size="small" onClick={() => choose(row)}>Xem ảnh</Button> }]} /></Section>
    {hasMinimumRole(user?.role, "manager") && <Section title="Thêm camera điện thoại"><Box component="form" sx={formLayout} onSubmit={(event) => { event.preventDefault(); void action.run(() => send("/cameras", { ...cameraForm, site_id: Number(sites.siteId), zone_id: null, is_active: true, retention_hours: 24 }), "Đã thêm camera điện thoại."); }}><TextField required label="Tên camera" value={cameraForm.name} onChange={(event) => setCameraForm((old) => ({ ...old, name: event.target.value }))} /><TextField select label="Hướng xử lý" value={cameraForm.direction} onChange={(event) => setCameraForm((old) => ({ ...old, direction: event.target.value }))}><MenuItem value="entry">Xe vào</MenuItem><MenuItem value="exit">Xe ra</MenuItem></TextField><Button type="submit" variant="outlined" disabled={action.busy || !sites.siteId}>Thêm camera</Button></Box></Section>}
  </Workspace>;
}
