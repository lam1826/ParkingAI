import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { AuthContext } from "../../context/AuthContext";
import { canManageCameras } from "./visionCameraState";
import OccupancyImage from "./OccupancyImage";
import { occupancyDefaults, occupancyLabel, occupancyReason, regionDraft, visibleReadings } from "./occupancyPresentation";
import { Workspace, Section, Records, useSites, useRemote, useAction, read, send, items, dateTime, requestKey, formLayout, SitePicker, combineRemotes, refreshAll } from "./shared";

function CalibrationForm({ camera, observations, slots, action, current }) {
  const [referenceId, setReferenceId] = useState("");
  const [slotId, setSlotId] = useState("");
  const [points, setPoints] = useState([]);
  const [regions, setRegions] = useState([]);
  const [confirmed, setConfirmed] = useState(false);
  const [settings, setSettings] = useState({ ...occupancyDefaults });
  const [coordinate, setCoordinate] = useState({ x: "", y: "" });
  const [error, setError] = useState("");
  const [frozen, setFrozen] = useState(false);
  const attempt = useRef(null);
  const choices = slots.filter((slot) => !camera.zone_id || slot.zone_id === camera.zone_id);
  const availableSlots = choices.filter((slot) => !regions.some((region) => region.slot_id === slot.id));
  const changeSettings = (name) => (event) => setSettings((old) => ({ ...old, [name]: Number(event.target.value) }));
  const addPoint = (point) => { if (!frozen && !action.busy && points.length < 12) { setPoints((old) => [...old, point]); setError(""); } };
  const addRegion = () => {
    try {
      const region = regionDraft(slotId, points);
      if (!availableSlots.some((slot) => slot.id === region.slot_id)) throw new Error("Chọn chỗ chưa được khoanh và thuộc camera.");
      setRegions((old) => [...old, region]); setPoints([]); setSlotId(""); setError("");
    } catch (failure) { setError(failure.message); }
  };
  const submit = (event) => {
    event.preventDefault();
    if (!attempt.current) {
      if (!referenceId || !regions.length || !confirmed) { setError("Chọn ảnh nền, khoanh ít nhất một chỗ và xác nhận các vùng đang trống."); return; }
      attempt.current = { camera_id: camera.id, reference_observation_id: referenceId, regions, settings,
        empty_reference_confirmed: true, request_id: requestKey() };
      setFrozen(true);
    }
    void action.run(() => send(`/sites/${camera.site_id}/occupancy/calibrations`, attempt.current), "Đã lưu phiên bản cấu hình mới. Chọn ảnh mới để phân tích.", () => {
      attempt.current = null; setFrozen(false); setConfirmed(false); setRegions([]); setPoints([]);
    });
  };
  const reference = observations.find((observation) => observation.id === referenceId);
  return <Section title="Cấu hình vùng chỗ đỗ" description="Dùng camera cố định nhìn rõ các chỗ. Chọn ảnh nền khi các chỗ cần khoanh đang trống. Mỗi lần lưu tạo một phiên bản mới và cần phân tích lại ảnh.">
    {current && <Typography variant="body2">Phiên bản hiện tại {current.version} · Ảnh nền còn lưu đến {dateTime(current.valid_until)}. Không kéo dài thời hạn ảnh để giữ cấu hình.</Typography>}
    <Box component="form" onSubmit={submit}>
      <Box component="fieldset" disabled={action.busy || frozen} sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
        <Stack spacing={2}>
          <TextField select label="Ảnh nền trống" value={referenceId} onChange={(event) => { setReferenceId(event.target.value); setRegions([]); setPoints([]); setConfirmed(false); }}>
            {observations.map((observation) => <MenuItem key={observation.id} value={observation.id}>Chụp {dateTime(observation.captured_at)} · {observation.id.slice(0, 8)}</MenuItem>)}
          </TextField>
          {reference && <OccupancyImage observationId={reference.id} regions={regions.map((region) => ({ ...region, slot_name: choices.find((slot) => slot.id === region.slot_id)?.slot_name }))} draft={points} onPoint={!frozen && !action.busy ? addPoint : undefined} label="Ảnh nền để khoanh vùng chỗ trống" />}
          <Typography variant="body2">Chọn chỗ, bấm các góc theo chiều quanh vùng rồi thêm vùng. Có thể nhập tọa độ X/Y từ 0 đến 1 bằng bàn phím. Không khoanh chồng lên chỗ khác.</Typography>
          <Box sx={formLayout}>
            <TextField select label="Chỗ cần khoanh" value={slotId} onChange={(event) => setSlotId(event.target.value)}>
              {availableSlots.map((slot) => <MenuItem key={slot.id} value={slot.id}>{slot.slot_name} · {slot.zone_name}</MenuItem>)}
            </TextField>
            <TextField label="Tọa độ X (0–1)" type="number" value={coordinate.x} inputProps={{ min: 0, max: 1, step: .001 }} onChange={(event) => setCoordinate((old) => ({ ...old, x: event.target.value }))} />
            <TextField label="Tọa độ Y (0–1)" type="number" value={coordinate.y} inputProps={{ min: 0, max: 1, step: .001 }} onChange={(event) => setCoordinate((old) => ({ ...old, y: event.target.value }))} />
          </Box>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Button disabled={!reference || coordinate.x === "" || coordinate.y === "" || points.length >= 12} onClick={() => {
              const point = [Number(coordinate.x), Number(coordinate.y)];
              if (point.every((value) => Number.isFinite(value) && value >= 0 && value <= 1)) { addPoint(point); setCoordinate({ x: "", y: "" }); }
              else setError("Tọa độ phải nằm trong khoảng 0 đến 1.");
            }}>Thêm đỉnh</Button>
            <Button disabled={!points.length} onClick={() => setPoints((old) => old.slice(0, -1))}>Bỏ đỉnh cuối</Button>
            <Button disabled={!reference || !slotId || points.length < 3 || regions.length >= 64} variant="outlined" onClick={addRegion}>Thêm vùng ({points.length} đỉnh)</Button>
          </Stack>
          {points.length > 0 && <Typography variant="caption">Các đỉnh: {points.map(([x, y]) => `(${x}; ${y})`).join(" → ")}</Typography>}
          <Records rows={regions.map((region) => ({ ...region, id: region.slot_id }))} columns={[
            { key: "slot_id", label: "Chỗ", render: (region) => choices.find((slot) => slot.id === region.slot_id)?.slot_name || `#${region.slot_id}` },
            { key: "polygon", label: "Số đỉnh", render: (region) => region.polygon.length },
            { key: "remove", label: "Thao tác", render: (region) => <Button disabled={action.busy || frozen} onClick={() => setRegions((old) => old.filter((item) => item.slot_id !== region.slot_id))}>Bỏ vùng</Button> },
          ]} />
          <Box component="details"><Typography component="summary" sx={{ cursor: "pointer", py: 1 }}>Ngưỡng xử lý ảnh</Typography>
            <Box sx={{ ...formLayout, mt: 2 }}>
              {[
                ["pixel_delta", "Độ chênh điểm ảnh", 10, 80, 1], ["empty_ratio", "Tỷ lệ thay đổi tối đa khi trống", .01, .2, .01],
                ["occupied_ratio", "Tỷ lệ thay đổi tối thiểu khi có xe", .15, .8, .01], ["max_lighting_shift", "Mức đổi sáng tối đa", 10, 80, 1],
                ["min_blur_variance", "Độ rõ tối thiểu", 0, 200, 1], ["stale_after_seconds", "Tuổi ảnh tối đa (giây)", 5, 300, 1],
                ["confirmation_frames", "Số ảnh cần thống nhất", 1, 3, 1],
              ].map(([name, label, min, max, step]) => <TextField key={name} label={label} type="number" required value={settings[name]} onChange={changeSettings(name)} inputProps={{ min, max, step }} />)}
            </Box>
          </Box>
          <FormControlLabel control={<Checkbox checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />} label="Tôi đã kiểm tra ảnh nền: tất cả các vùng vừa khoanh đang trống." />
        </Stack>
      </Box>
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      {frozen && <Alert severity="info" sx={{ mt: 2 }}>Nội dung được giữ nguyên để gửi lại nếu mất kết nối. Làm mới kiểm tra phiên bản trước khi nhập cấu hình khác.</Alert>}
      <Stack direction="row" spacing={1} sx={{ mt: 2 }}><Button type="submit" variant="contained" disabled={action.busy || !camera.is_active}>{frozen ? "Gửi lại cùng cấu hình" : "Lưu phiên bản mới"}</Button>
        {frozen && <Button disabled={action.busy} onClick={() => { attempt.current = null; setFrozen(false); }}>Nhập cấu hình khác</Button>}
      </Stack>
    </Box>
  </Section>;
}

function CameraWorkspace({ camera, canManage }) {
  const [sourceId, setSourceId] = useState("");
  const load = useCallback(async () => {
    const receivedAt = performance.now();
    const [summary, observations, availability] = await Promise.all([
      read(`/sites/${camera.site_id}/occupancy`, { camera_id: camera.id }),
      read("/vision/observations", { site_id: camera.site_id, limit: 100 }),
      read(`/sites/${camera.site_id}/availability`),
    ]);
    return { summary, observations: items(observations).filter((row) => row.camera_id === camera.id), slots: availability.slots || [], receivedAt };
  }, [camera.id, camera.site_id]);
  const remote = useRemote(load);
  const action = useAction(remote.reload);
  const [elapsed, setElapsed] = useState(0);
  const reload = remote.reload;
  const receivedAt = remote.data?.receivedAt;
  useEffect(() => {
    const tick = () => setElapsed(receivedAt == null ? 0 : Math.max(0, performance.now() - receivedAt));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [receivedAt]);
  useEffect(() => {
    const timer = window.setInterval(() => { if (!document.hidden && !action.busy) void reload(); }, 15000);
    return () => window.clearInterval(timer);
  }, [reload, action.busy]);
  const data = remote.data;
  const summary = data?.summary;
  const readings = visibleReadings(summary, elapsed);
  const effectiveNow = Date.parse(summary?.server_now) + elapsed;
  const sources = (data?.observations || []).filter((row) => Date.parse(row.expires_at) > effectiveNow);
  const selectedSource = sources.some((row) => row.id === sourceId) ? sourceId : "";
  const referenceValid = summary?.calibration?.reference_image_available && Date.parse(summary.calibration.valid_until) > Date.parse(summary.server_now) + elapsed;
  return <Workspace title={camera.name} description="Mỗi kết quả gắn với ảnh chụp và phiên bản cấu hình của camera." remote={remote} action={action}>
    <Alert severity="info">So sánh ảnh giúp tìm vùng thay đổi; người đi qua, vật thể và bóng đổ cũng có thể làm vùng bị xem là có xe. Chưa đo độ chính xác trên bãi thực tế. Kết quả không tự đổi vị trí, lượt gửi hoặc tiền thu.</Alert>
    {summary?.engine && !summary.engine.available && <Alert severity="warning">{summary.engine.reason}</Alert>}
    {!camera.is_active && <Alert severity="warning">Camera ngừng hoạt động. Kết quả hiện tại được xem là chưa xác định.</Alert>}
    {summary?.calibration && !referenceValid && <Alert severity="warning">Ảnh nền đã hết hạn hoặc bị xóa. Quản lý cần chọn ảnh nền mới và lưu một phiên bản cấu hình mới.</Alert>}
    <Section title="Quan sát mới nhất" description="Trạng thái hết hiệu lực khi ảnh chụp quá cũ. Trang làm mới dữ liệu mỗi 15 giây; phân tích ảnh chỉ chạy khi bấm nút.">
      {summary?.latest && <Stack spacing={1}>
        <Typography>Chụp {dateTime(summary.latest.measured_at)} · Nhận {dateTime(summary.latest.received_at)} · Phân tích {dateTime(summary.latest.analyzed_at)}</Typography>
        <Typography variant="body2">Phiên bản {summary.latest.calibration_version} · Có thể dùng đến {dateTime(summary.valid_until)} · Ảnh {summary.latest.source_observation_id}</Typography>
        {summary.source_image_available && Date.parse(summary.latest.source_image_valid_until) > effectiveNow && <OccupancyImage observationId={summary.latest.source_observation_id} regions={readings} />}
      </Stack>}
      {!summary?.calibration && <Typography color="text.secondary">Chưa có cấu hình vùng chỗ đỗ. Quản lý chọn ảnh nền và khoanh các chỗ bên dưới.</Typography>}
      {summary?.calibration && !summary.latest && <Typography color="text.secondary">Chưa phân tích ảnh với phiên bản {summary.calibration.version}.</Typography>}
      <Records rows={readings.map((row) => ({ ...row, id: row.slot_id }))} columns={[
        { key: "slot_name", label: "Chỗ đỗ" }, { key: "zone_name", label: "Khu vực" },
        { key: "state", label: "Theo ảnh", render: (row) => <Chip size="small" label={occupancyLabel(row.state)} color={row.state === "empty" ? "success" : row.state === "occupied" ? "warning" : "default"} /> },
        { key: "business_state", label: "Theo lượt gửi", render: (row) => ({ occupied: "Đang có xe", empty: "Trống", inactive: "Ngừng sử dụng" })[row.business_state] || "—" },
        { key: "mismatch", label: "Đối chiếu", render: (row) => row.mismatch === true ? <Chip size="small" color="warning" label="Cần kiểm tra chênh lệch" /> : row.mismatch === false ? "Khớp" : "Chưa đủ dữ liệu" },
        { key: "reason", label: "Ghi chú", render: (row) => occupancyReason(row.reason) || "—" },
      ]} />
    </Section>
    <Section title="Phân tích ảnh được chọn" description="Ảnh mới phải giữ nguyên góc chụp và kích thước so với ảnh nền. Mặc định cần hai ảnh khác nhau có kết quả thống nhất.">
      <Box sx={formLayout}><TextField select label="Ảnh cần phân tích" value={selectedSource} onChange={(event) => setSourceId(event.target.value)} disabled={action.busy}>
        {sources.map((row) => <MenuItem key={row.id} value={row.id}>Chụp {dateTime(row.captured_at)} · {row.id.slice(0, 8)}</MenuItem>)}
      </TextField><Button variant="contained" disabled={action.busy || !selectedSource || !summary?.calibration || !referenceValid || !camera.is_active || !summary?.engine?.available} onClick={() => action.run(() => send(`/sites/${camera.site_id}/occupancy/analyze`, { camera_id: camera.id, calibration_id: summary.calibration.id, observation_id: selectedSource }), "Đã xử lý ảnh. Kiểm tra trạng thái và các chênh lệch bên trên.")}>Phân tích ảnh</Button>
        <Button component={Link} to="/vision">Gửi ảnh camera mới</Button></Box>
      {!sources.length && <Typography color="text.secondary">Chưa có ảnh của camera này trong 100 ảnh gần nhất của bãi.</Typography>}
    </Section>
    {canManage && data && <CalibrationForm camera={camera} observations={sources} slots={data.slots} current={summary?.calibration} action={action} />}
  </Workspace>;
}

export default function OccupancyPage() {
  const { user } = useContext(AuthContext);
  const sites = useSites();
  const [choice, setChoice] = useState("");
  const load = useCallback(() => sites.siteId ? read("/cameras", { site_id: sites.siteId }).then(items) : Promise.resolve([]), [sites.siteId]);
  const cameras = useRemote(load);
  const site = sites.sites.find((row) => String(row.id) === String(sites.siteId));
  const camera = cameras.data?.find((row) => String(row.id) === choice) || cameras.data?.[0];
  const pageRemote = { ...combineRemotes(sites, cameras), reload: refreshAll(sites, cameras) };
  return <Stack spacing={3}>
    <Workspace title="Chỗ đỗ qua camera" description="Đối chiếu hình ảnh với lượt gửi để phát hiện chỗ cần kiểm tra trực tiếp." remote={pageRemote}>
      <Box sx={formLayout}><SitePicker sites={sites} /><TextField select label="Camera quan sát" value={camera?.id || ""} onChange={(event) => setChoice(String(event.target.value))}>
        {(cameras.data || []).map((row) => <MenuItem key={row.id} value={row.id}>{row.name}{row.is_active ? "" : " · Ngừng hoạt động"}</MenuItem>)}
      </TextField></Box>
      {!cameras.loading && !camera && <Alert severity="info">Chưa có camera. Quản lý thêm camera trong mục Camera & biển số, sau đó gửi ảnh có các chỗ cần quan sát.</Alert>}
    </Workspace>
    {camera && <CameraWorkspace key={`${user?.id}:${camera.site_id}:${camera.id}:${canManageCameras(user?.role, site?.role)}`} camera={camera} canManage={canManageCameras(user?.role, site?.role)} />}
  </Stack>;
}
