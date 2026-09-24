import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button } from "@mui/material";
import OperationIcon from "./OperationIcon";
import { Link as RouterLink } from "react-router-dom";
import api from "../../services/api";
import { getErrorMessage } from "../../utils/errorMessage";
import { ObservationImage } from "./VisionPage";
import { prepareCameraPhoto } from "./imageUpload";
import { captureCameraPhoto, cameraRecognitionMessage, playCameraPreview } from "./cameraCapture.js";
import { cameraHealthText } from "./visionCameraState";
import { framesForAutomation, passageLabels } from "./cameraAutomationState.js";
import { automationPolicyUpdate, canStartCameraAutomation, startCameraAutomation } from "./cameraAutomationStart.js";
import { endpoint, items, read, send, requestKey, dateTime, useRemote, useAction } from "./shared";

export default function CameraOperations({ site, direction = "entry", onManual, onPassage, onCheckout }) {
  const [choice, setChoice] = useState("");
  const [running, setRunning] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [opening, setOpening] = useState(false);
  const [starting, setStarting] = useState(false);
  const [videoReady, setVideoReady] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [selected, setSelected] = useState(null);
  const [plate, setPlate] = useState("");
  const [latest, setLatest] = useState(null);
  const [error, setError] = useState("");
  const video = useRef(null), media = useRef(null), active = useRef(true), busy = useRef(false), processed = useRef(new Set());
  const startingRef = useRef(false);
  const loadCameras = useCallback(() => read("/cameras", { site_id: site.id }).then(items), [site.id]);
  const cameras = useRemote(loadCameras);
  const loadEngine = useCallback(() => read("/vision/status"), []);
  const engine = useRemote(loadEngine);
  const laneCameras = useMemo(() => (cameras.data || []).filter(row => row.direction === direction), [cameras.data, direction]);
  const camera = laneCameras.find(row => String(row.id) === String(choice)) || laneCameras[0];
  const cameraId = camera?.id;
  const hasAutomationSource = streaming || camera?.edge_enabled;
  const loadPolicy = useCallback(() => cameraId ? read(`/cameras/${cameraId}/automation`) : Promise.resolve(null), [cameraId]);
  const policy = useRemote(loadPolicy);
  const loadFrames = useCallback(() => read("/vision/observations", { site_id: site.id, limit: 25 }).then(items), [site.id]);
  const frames = useRemote(loadFrames);
  const reloadFrames = frames.reload;
  const action = useAction(policy.reload);
  const review = useAction(frames.reload);
  const canManage = ["admin", "manager"].includes(site.role);
  const latestCallback = useRef(onPassage);
  useEffect(() => { latestCallback.current = onPassage; }, [onPassage]);
  const stopMedia = () => { media.current?.getTracks().forEach(track => track.stop()); media.current = null; };
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; stopMedia(); };
  }, []);
  const chooseFrame = row => { setSelected(row); setPlate(row.confirmed_plate || row.suggested_plate || ""); };
  const startWebcam = async () => {
    if (opening) return false;
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) { setError("Webcam cần trình duyệt hỗ trợ và kết nối HTTPS hoặc localhost. Có thể chụp bằng điện thoại rồi tải ảnh."); return false; }
    setOpening(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      if (!active.current) { stream.getTracks().forEach(track => track.stop()); return false; }
      stopMedia(); media.current = stream; setVideoReady(false); setStreaming(true);
      stream.getVideoTracks().forEach(track => track.addEventListener("ended", () => {
        if (active.current && media.current === stream) { stopMedia(); setStreaming(false); setVideoReady(false); setRunning(false); }
      }));
      if (video.current) video.current.srcObject = stream;
      await playCameraPreview(video.current);
      return active.current && media.current === stream && stream.getVideoTracks().some(track => track.readyState === "live");
    } catch {
      stopMedia();
      if (active.current) { setStreaming(false); setVideoReady(false); setError("Chưa mở được webcam. Kiểm tra quyền camera hoặc chọn ảnh từ thiết bị."); }
      return false;
    } finally { if (active.current) setOpening(false); }
  };
  const toggleAutomation = async () => {
    if (running) { setRunning(false); return; }
    if (startingRef.current || opening || busy.current || action.busy || policy.loading || !canStartCameraAutomation(camera, policy.data, canManage)) return;
    startingRef.current = true; setStarting(true); setError(""); setLatest(null);
    try {
      const started = await startCameraAutomation({
        policy: policy.data, canManage,
        hasSource: Boolean(media.current || camera.edge_enabled), openSource: startWebcam,
        enablePolicy: async update => (await api.put(endpoint(`/cameras/${cameraId}/automation`), update)).data,
        reloadPolicy: policy.reload, isActive: () => active.current,
      });
      if (active.current && started) {
        if (!camera.edge_enabled && !media.current?.getVideoTracks().some(track => track.readyState === "live")) {
          throw new Error("Camera đã ngắt kết nối. Hãy mở lại webcam rồi bật tự động.");
        }
        setRunning(true);
      }
    } catch (failure) {
      if (active.current) { setRunning(false); setError(getErrorMessage(failure, "Chưa bật được tự động. Hãy thử lại.")); }
    } finally {
      startingRef.current = false;
      if (active.current) setStarting(false);
    }
  };
  const upload = async (file, capturedAt = new Date().toISOString()) => {
    if (!cameraId) throw new Error("Hãy chọn camera của bãi.");
    const payload = new FormData(); payload.append("file", file); payload.append("camera_id", cameraId);
    payload.append("event_id", requestKey()); payload.append("captured_at", capturedAt);
    // One-off captures and files always require review, even if another
    // workspace is running automation. Only that loop uses live ingress.
    return (await api.post(endpoint("/vision/observations"), payload, { headers: { "Content-Type": undefined }, timeout: 120000 })).data;
  };
  const scanWebcam = async () => {
    if (busy.current || !media.current) return;
    busy.current = true; setScanning(true); setError(""); setLatest(null);
    try {
      const { file, capturedAt } = await captureCameraPhoto(video.current);
      const row = await upload(file, capturedAt);
      processed.current.add(row.id);
      if (active.current) { chooseFrame(row); void reloadFrames(); void engine.reload(); }
    } catch (failure) { if (active.current) setError(getErrorMessage(failure, "Chưa quét được biển số. Hãy thử lại.")); }
    finally { busy.current = false; if (active.current) setScanning(false); }
  };
  const uploadFile = async event => {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file || busy.current) return;
    busy.current = true; setScanning(true); setError(""); setLatest(null);
    try {
      const row = await upload(await prepareCameraPhoto(file));
      processed.current.add(row.id);
      if (active.current) { chooseFrame(row); void reloadFrames(); void engine.reload(); }
    } catch (failure) { if (active.current) setError(getErrorMessage(failure, "Chưa tải được ảnh. Hãy thử lại.")); }
    finally { busy.current = false; if (active.current) setScanning(false); }
  };
  useEffect(() => {
    if (!running || !cameraId || !policy.data?.enabled || !hasAutomationSource) return;
    let stopped = false, timer;
    const tick = async () => {
      if (stopped) return;
      if (document.visibilityState !== "visible" || busy.current) { timer = window.setTimeout(tick, 4000); return; }
      busy.current = true; setScanning(true);
      try {
        if (media.current && video.current?.readyState >= 2) {
          const { file, capturedAt } = await captureCameraPhoto(video.current);
          if (stopped) return;
          const payload = new FormData(); payload.append("file", file); payload.append("camera_id", cameraId);
          payload.append("event_id", requestKey()); payload.append("captured_at", capturedAt);
          const { data: row } = await api.post(endpoint("/vision/live-frames"), payload, { headers: { "Content-Type": undefined }, timeout: 120000 });
          if (!stopped) { setSelected(row); setPlate(row.suggested_plate || ""); setLatest(null); }
        }
        if (stopped) return;
        const rows = items(await read("/vision/observations", { site_id: site.id, limit: 25 }));
        for (const row of framesForAutomation(rows, cameraId, processed.current, Date.now(), policy.data.max_age_seconds)) {
          if (stopped) break;
          const result = await send(`/vision/observations/${row.id}/process`);
          processed.current.add(row.id);
          // Stop prevents new requests; a submitted request can still commit.
          // Reconcile its result without stealing selection from a newer lane.
          latestCallback.current?.(result, { updateSelection: !stopped && active.current });
          if (!stopped) { setLatest(result); setSelected(row); setPlate(row.suggested_plate || ""); }
        }
        if (!stopped) { setError(""); void reloadFrames(); }
      } catch (failure) { if (!stopped) setError(getErrorMessage(failure, "Tự động chưa xử lý được ảnh. Hệ thống sẽ kiểm tra lại.")); }
      finally { busy.current = false; if (active.current) setScanning(false); if (!stopped) timer = window.setTimeout(tick, 4000); }
    };
    void tick();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [running, cameraId, policy.data, hasAutomationSource, site.id, reloadFrames]);
  const current = selected?.camera_id === cameraId ? selected : null;
  const recognition = cameraRecognitionMessage(current);
  const automationHint = !camera?.is_active ? "Cần camera đang hoạt động tại làn này để bật tự động."
    : policy.loading ? "Đang tải quyền tự động của camera…"
    : !policy.data ? "Chưa tải được quyền tự động. Hãy thử tải lại cài đặt camera."
    : !policy.data.enabled && !canManage ? "Cần Admin hoặc Manager cho phép tự động ở camera này. Bạn vẫn có thể quét biển số để kiểm tra."
    : !policy.data.enabled ? "Bấm Bật tự động để cho phép camera nhận / trả xe với ảnh đủ điều kiện. Webcam sẽ mở nếu chưa có nguồn ảnh."
    : !hasAutomationSource ? "Bấm Bật tự động để mở webcam và xử lý ảnh mới."
    : "Tự động chỉ xử lý ảnh đủ điều kiện; ảnh chưa rõ vẫn cần nhân viên kiểm tra.";
  return <>
    {cameras.error && <Alert severity="error">{cameras.error}</Alert>}
    {policy.error && <Alert severity="error" action={<Button disabled={policy.loading || starting} onClick={() => void policy.reload()}>Thử lại</Button>}>{policy.error}</Alert>}
    {action.error && <Alert severity="error">{action.error}</Alert>}
    {engine.error && <Alert severity="warning">{engine.error}</Alert>}
    {engine.data && !engine.data.available && <Alert severity="warning">{engine.data.reason}</Alert>}
    {error && <Alert severity="warning">{error}</Alert>}
    <div className="camera-stage" style={{ minHeight: 260 }}>
      <div className="camera-label" style={{ zIndex: 1 }}>{camera?.name || "Camera"} · Làn {direction === "entry" ? "vào" : "ra"}</div>
      <video ref={video} muted playsInline onLoadedData={() => setVideoReady(true)} style={{ display: streaming ? "block" : "none", width: "100%", height: 290, objectFit: "contain" }} />
      {!streaming && (current ? <div style={{ padding: "44px 12px 60px" }}><ObservationImage observation={current} /></div> : <div style={{ minHeight: 260, display: "grid", placeContent: "center", justifyItems: "center", gap: 12, color: "#dce8f3", fontSize: 13 }}><OperationIcon name="camera" style={{ width: 42, height: 42 }} /><span>{cameras.loading ? "Đang tải camera…" : camera ? "Camera chưa bật" : "Chưa có camera tại làn này"}</span></div>)}
      <div className="camera-result"><span>{latest ? passageLabels[latest.state] : streaming ? "Webcam đang mở" : camera ? cameraHealthText(camera) : "Cần cấu hình camera"}</span><span className={`badge ${running ? "success" : "neutral"}`}>{scanning ? "Đang đọc ảnh…" : running ? "Tự động đang bật" : "Tự động tắt"}</span></div>
    </div>
    <div className="camera-controls" style={{ flexWrap: "wrap" }}>
      <button className="button secondary" disabled={!camera?.is_active || running || opening || scanning || starting} onClick={streaming ? () => { stopMedia(); setStreaming(false); setVideoReady(false); } : startWebcam}>{opening ? "Đang mở camera…" : streaming ? "Tắt webcam" : "Dùng webcam"}</button>
      <button className="button primary" disabled={!camera?.is_active || !streaming || !videoReady || running || scanning || starting} aria-busy={scanning} onClick={scanWebcam}>{scanning ? "Đang đọc ảnh…" : "Quét biển số"}</button>
      <button className="button secondary" disabled={!running && (starting || opening || scanning || action.busy || policy.loading || !canStartCameraAutomation(camera, policy.data, canManage))} aria-busy={starting} aria-describedby="camera-automation-hint" onClick={() => void toggleAutomation()}>{running ? "Dừng tự động" : starting ? "Đang bật tự động…" : "Bật tự động"}</button>
    </div>
    {streaming && !running && !current && <p role="status" className="muted" style={{ fontSize: 12, marginTop: 12 }}>Đặt biển số rõ trong khung hình rồi bấm Quét biển số.</p>}
    <p id="camera-automation-hint" className="muted" style={{ fontSize: 12, marginTop: 12 }}>{automationHint}</p>
    <p className="muted" style={{ fontSize: 12, marginTop: 16 }}>Loại xe lấy từ hồ sơ phương tiện. Ảnh chưa rõ hoặc xe còn phí chờ nhân viên kiểm tra.</p>
    {running && <p role="status" className="muted" style={{ fontSize: 12, marginTop: 8 }}>Đang xử lý ảnh mới. Tự động tạm dừng khi tab bị ẩn.</p>}
    {latest && <Alert sx={{ mt: 2 }} severity={["entered", "exited", "already_entered"].includes(latest.state) ? "success" : "info"}>
      <strong>{passageLabels[latest.state]}{latest.license_plate ? ` · ${latest.license_plate}` : ""}</strong><p>{latest.reason}</p>
      {latest.state === "waiting_payment" && latest.session_id && <Button onClick={() => onCheckout(latest.session_id)}>Xem phí & thanh toán</Button>}
    </Alert>}
    {current && <div style={{ marginTop: 18 }}>
      {recognition && <Alert severity={recognition.severity} role="status" data-camera-ocr-status={current.ocr_status}><strong>{recognition.title}</strong><p>{recognition.detail}</p></Alert>}
      <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>Ảnh chụp lúc {dateTime(current.captured_at)}</p>
      <div className="field"><label htmlFor="camera-confirmed-plate">Biển số đã kiểm tra</label><input id="camera-confirmed-plate" value={plate} maxLength={20} readOnly={current.review_status !== "pending"} aria-describedby={current.review_status !== "pending" ? "camera-reviewed-hint" : undefined} onChange={event => setPlate(event.target.value)} />{current.review_status !== "pending" && <small id="camera-reviewed-hint">Ảnh đã được xử lý. Nếu cần sửa biển số, hãy quét hoặc chọn ảnh mới để kiểm tra.</small>}</div>
      {review.error && <Alert severity="error">{review.error}</Alert>}
      <button className="button secondary" disabled={running || starting || scanning || review.busy || !plate.trim() || current.review_status === "rejected"} onClick={() => void review.run(async () => {
        const result = current.review_status === "accepted" ? current : await send(`/vision/observations/${current.id}/review`, { decision: "accept", license_plate: plate.trim().toUpperCase() });
        onManual(result.confirmed_plate || plate.trim().toUpperCase(), camera.direction);
        return result;
      }, "Đã chuyển biển số sang thao tác thủ công.")}>Dùng biển số & kiểm tra thủ công</button>
    </div>}
    <details className="demo-help"><summary>Cài đặt camera & kiểm tra ảnh</summary>
      {camera && <>
        <div className="field"><label htmlFor="operation-camera">Camera tại làn</label><select id="operation-camera" value={cameraId} disabled={running || starting || streaming || scanning || opening} onChange={event => { setChoice(event.target.value); setSelected(null); setLatest(null); }}>{laneCameras.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></div>
        <label className="button secondary small" style={{ cursor: !camera.is_active || running || starting || scanning ? "default" : "pointer" }}>Chụp / chọn ảnh<input hidden type="file" disabled={!camera.is_active || running || starting || scanning} accept="image/jpeg,image/png,image/webp" capture="environment" onChange={uploadFile} /></label>
        {canManage ? <><label className="checkbox-field" style={{ marginTop: 18 }}><input type="checkbox" checked={Boolean(policy.data?.enabled)} disabled={action.busy || starting || policy.loading || !policy.data || !camera.is_active} onChange={event => { const enabled = event.target.checked; setRunning(false); void action.run(() => api.put(endpoint(`/cameras/${cameraId}/automation`), automationPolicyUpdate(policy.data, enabled)), enabled ? "Đã cho phép tự động với ảnh mới." : "Đã tắt tự động."); }} />Cho phép xử lý ảnh đủ điều kiện</label><p style={{ marginTop: 10 }}>Một biển số rõ, điểm nhận diện từ {policy.data?.minimum_confidence ?? .97} và ảnh chụp trong {policy.data?.max_age_seconds ?? 15} giây. Cần kiểm chứng độ chính xác trên camera thực tế.</p></> : !policy.data?.enabled && <p>Quản lý chưa bật quy tắc tự động cho camera này.</p>}
        {!!frames.data?.filter(row => row.camera_id === cameraId).length && <div className="field" style={{ marginTop: 18 }}><label htmlFor="camera-recent-frame">Ảnh gần đây</label><select id="camera-recent-frame" value={current?.id || ""} disabled={running || starting || scanning || review.busy} onChange={event => { const row = frames.data.find(row => row.id === event.target.value); if (row) chooseFrame(row); else setSelected(null); }}><option value="">Chọn ảnh để kiểm tra</option>{frames.data.filter(row => row.camera_id === cameraId).map(row => <option key={row.id} value={row.id}>{row.confirmed_plate || row.suggested_plate || "Chưa đọc được biển"} · {dateTime(row.observed_at)}</option>)}</select></div>}
      </>}
      <RouterLink className="button quiet small" to={`/vision?site=${site.id}`}>Cấu hình camera & lịch sử ảnh</RouterLink>
    </details>
  </>;
}
