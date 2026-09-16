import { useCallback, useContext } from "react";
import { Link as RouterLink } from "react-router-dom";
import { Alert, Box, Button, Chip, CircularProgress, Container, Divider, Grid, Link, List, ListItem, ListItemText, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import PlaceIcon from "@mui/icons-material/Place";
import PhoneIcon from "@mui/icons-material/Phone";
import DirectionsIcon from "@mui/icons-material/Directions";
import RefreshIcon from "@mui/icons-material/Refresh";
import BrandLogo from "../../components/brand/BrandLogo";
import { AuthContext } from "../../context/AuthContext";
import api from "../../services/api";
import formatCurrency from "../../utils/formatCurrency";
import { singleSiteId } from "../../utils/singleSiteMode";
import { useRemote } from "../Expansion/shared";
import { actionTargets, mapLinks, notPublished, paymentModeLabel, planDuration, productLabel, rateUnit, textOrPlaceholder } from "./publicSiteState";

const money = (value) => `${formatCurrency(value ?? 0)} ₫`;

async function loadProfile() {
  const configured = singleSiteId();
  if (configured !== null) return (await api.get(`/api/v2/public/sites/${configured}`)).data;
  const directory = (await api.get("/api/v2/public/sites")).data?.items || [];
  if (!directory.length) return null;
  return (await api.get(`/api/v2/public/sites/${directory[0].id}`)).data;
}

function Fact({ icon, label, value, missing }) {
  return <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start" }}>
    <Box sx={{ color: "primary.main", mt: 0.25 }}>{icon}</Box>
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1.4 }}>{label}</Typography>
      <Typography sx={{ overflowWrap: "anywhere" }} color={missing ? "text.secondary" : "text.primary"} fontStyle={missing ? "italic" : "normal"}>{value}</Typography>
    </Box>
  </Stack>;
}

function Placeholder({ children }) {
  return <Typography color="text.secondary" fontStyle="italic">{children}</Typography>;
}

export default function PublicSitePage() {
  const auth = useContext(AuthContext);
  const user = auth?.user || null;
  const load = useCallback(() => loadProfile(), []);
  const remote = useRemote(load);
  const profile = remote.data;
  const targets = actionTargets(profile, user);
  const map = mapLinks(profile);
  const loading = remote.loading;
  return <Box sx={{ minHeight: "100vh", bgcolor: "#f5f7fb", pb: 6 }}>
    <Box component="header" sx={{ bgcolor: "primary.main", color: "white", py: 1.5 }}>
      <Container maxWidth="lg">
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} useFlexGap sx={{ alignItems: { sm: "center" }, justifyContent: "space-between" }}>
          <RouterLink to="/gioi-thieu" style={{ color: "inherit", textDecoration: "none" }} aria-label="Trang giới thiệu bãi xe"><BrandLogo size={36} inverse /></RouterLink>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            {user ? <>
              <Typography sx={{ alignSelf: "center" }}>Xin chào, {user.username}</Typography>
              <Button component={RouterLink} to={user.role === "customer" ? "/portal" : "/"} variant="contained" color="inherit" sx={{ color: "primary.dark" }}>{user.role === "customer" ? "Bãi xe của tôi" : "Vào hệ thống"}</Button>
            </> : <>
              <Button component={RouterLink} to={`/login?next=${encodeURIComponent("/portal")}`} variant="outlined" color="inherit">Đăng nhập</Button>
              <Button component={RouterLink} to={`/register?next=${encodeURIComponent("/portal")}`} variant="contained" color="inherit" sx={{ color: "primary.dark" }}>Đăng ký</Button>
            </>}
          </Stack>
        </Stack>
      </Container>
    </Box>
    <Container maxWidth="lg" component="main" sx={{ pt: { xs: 3, md: 5 } }}>
      {remote.error && <Alert severity="error" sx={{ mb: 3 }} action={<Button color="inherit" size="small" startIcon={<RefreshIcon />} onClick={remote.reload} disabled={loading}>Thử lại</Button>}>Không tải được thông tin bãi xe: {remote.error}</Alert>}
      {loading && <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 3 }} role="status"><CircularProgress size={20} /><Typography>Đang tải thông tin bãi xe…</Typography></Stack>}
      {!loading && !remote.error && !profile && <Alert severity="info" action={<Button color="inherit" size="small" onClick={remote.reload}>Tải lại</Button>}>Chưa có bãi xe nào được công bố. Hãy quay lại sau hoặc đăng nhập nếu bạn là quản lý.</Alert>}
      {profile && <Stack spacing={3}>
        {profile.demo_labeled && <Alert severity="info">Trang trình diễn đồ án: thông tin, giá và thanh toán là dữ liệu mô phỏng có nhãn DEMO; không có giao dịch ngân hàng thật.</Alert>}
        <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 4 } }}>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h3" component="h1" sx={{ fontSize: { xs: "1.75rem", md: "2.5rem" }, fontWeight: 700 }}>{profile.name}</Typography>
              <Typography color="text.secondary" sx={{ mt: 1, maxWidth: "75ch" }}>{profile.description || <Placeholder>Bãi chưa cập nhật mô tả.</Placeholder>}</Typography>
            </Box>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 4 }}><Fact icon={<PlaceIcon />} label="Địa chỉ" value={textOrPlaceholder(profile.address)} missing={!profile.address} /></Grid>
              <Grid size={{ xs: 12, md: 4 }}><Fact icon={<AccessTimeIcon />} label="Giờ mở cửa" value={textOrPlaceholder(profile.opening_hours)} missing={!profile.opening_hours} /></Grid>
              <Grid size={{ xs: 12, md: 4 }}><Fact icon={<PhoneIcon />} label="Liên hệ" value={profile.contact?.phone || profile.contact?.email ? [profile.contact.phone, profile.contact.email].filter(Boolean).join(" · ") : notPublished} missing={!profile.contact?.phone && !profile.contact?.email} /></Grid>
            </Grid>
            <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
              <Button component={RouterLink} to={targets.purchase.to} variant="contained" size="large">{targets.purchase.label}</Button>
              {targets.reserve && <Button component={RouterLink} to={targets.reserve.to} variant="outlined" size="large">{targets.reserve.label}</Button>}
              {map.directions && <Button component={Link} href={map.directions} target="_blank" rel="noopener noreferrer" variant="outlined" size="large" startIcon={<DirectionsIcon />}>Chỉ đường</Button>}
            </Stack>
            {!targets.signedIn && <Typography variant="body2" color="text.secondary">Mua vé giờ/ngày/tháng và đặt chỗ cần tài khoản khách. Sau khi đăng nhập, bạn quay lại đúng bước đã chọn.</Typography>}
          </Stack>
        </Paper>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, md: 7 }}>
            <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, height: "100%" }}>
              <Typography variant="h5" component="h2" sx={{ mb: 1 }}>Bảng giá & gói vé</Typography>
              <Typography color="text.secondary" sx={{ mb: 2 }}>Giá do bãi công bố; số tiền thực tế được máy chủ tính khi mua vé hoặc khi xe ra.</Typography>
              {profile.walk_in_rates?.length ? <TableContainer sx={{ mb: 2 }}><Table size="small" aria-label="Giá gửi xe vãng lai"><TableHead><TableRow><TableCell>Loại xe</TableCell><TableCell>Giá vãng lai</TableCell><TableCell>Áp dụng từ</TableCell></TableRow></TableHead><TableBody>
                {profile.walk_in_rates.map((rate) => <TableRow key={`${rate.vehicle_type_id}-${rate.ticket_type}`}><TableCell>{rate.vehicle_type_name}</TableCell><TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>{money(rate.price)} {rateUnit(rate.ticket_type)}</TableCell><TableCell>{rate.effective_date ? String(rate.effective_date).split("-").reverse().join("/") : "—"}</TableCell></TableRow>)}
              </TableBody></Table></TableContainer> : <Placeholder>Bãi chưa công bố giá gửi xe vãng lai.</Placeholder>}
              {profile.plans?.length ? <TableContainer><Table size="small" aria-label="Gói vé"><TableHead><TableRow><TableCell>Gói vé</TableCell><TableCell>Loại xe</TableCell><TableCell>Thời lượng</TableCell><TableCell>Giá</TableCell></TableRow></TableHead><TableBody>
                {profile.plans.map((plan) => <TableRow key={plan.id}><TableCell>{plan.name}<Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{productLabel(plan.product_kind)}</Typography></TableCell><TableCell>{plan.vehicle_type_name}</TableCell><TableCell>{planDuration(plan)}</TableCell><TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>{money(plan.price)}</TableCell></TableRow>)}
              </TableBody></Table></TableContainer> : <Placeholder>Bãi chưa công bố gói vé giờ/ngày/tháng.</Placeholder>}
              {profile.payment_modes?.length > 0 && <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>Hình thức thanh toán: {profile.payment_modes.map(paymentModeLabel).join(" · ")}.</Typography>}
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, md: 5 }}>
            <Stack spacing={3} sx={{ height: "100%" }}>
              <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 } }}>
                <Typography variant="h5" component="h2" sx={{ mb: 1 }}>Loại xe phục vụ</Typography>
                {profile.vehicle_types?.length ? <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                  {profile.vehicle_types.map((type) => <Chip key={type.id} label={`${type.name} · ${type.slot_count} chỗ`} />)}
                </Stack> : <Placeholder>Bãi chưa cấu hình chỗ đỗ cho loại xe nào.</Placeholder>}
                {profile.capacity && <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>{profile.capacity.zones} khu vực · {profile.capacity.slots} vị trí đang hoạt động. Tình trạng chỗ trống theo thời gian thực chỉ hiển thị sau khi đăng nhập.</Typography>}
              </Paper>
              <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, flex: 1 }}>
                <Typography variant="h5" component="h2" sx={{ mb: 1 }}>Vị trí & chỉ đường</Typography>
                {map.kind === "coordinates" && <Box component="iframe" title={`Bản đồ vị trí ${profile.name}`} src={map.embed} loading="lazy" referrerPolicy="no-referrer" sx={{ width: "100%", aspectRatio: "4 / 3", border: 0, borderRadius: 1, maxWidth: "100%" }} />}
                {map.kind === "address" && <Typography color="text.secondary">Bãi chưa công bố tọa độ; chỉ đường dựa theo địa chỉ đã cập nhật.</Typography>}
                {map.kind === "none" && <Placeholder>Bãi chưa cập nhật địa chỉ hoặc tọa độ.</Placeholder>}
                {map.open && <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 1.5, flexWrap: "wrap" }}>
                  <Button component={Link} href={map.directions} target="_blank" rel="noopener noreferrer" startIcon={<DirectionsIcon />}>Chỉ đường</Button>
                  <Button component={Link} href={map.open} target="_blank" rel="noopener noreferrer">Mở bản đồ</Button>
                </Stack>}
              </Paper>
            </Stack>
          </Grid>
        </Grid>
        <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 } }}>
          <Typography variant="h5" component="h2" sx={{ mb: 1 }}>Cách sử dụng</Typography>
          <List dense>
            <ListItem><ListItemText primary="1. Đăng ký tài khoản khách, liên kết hồ sơ và xe" secondary="Nhân viên xác minh xe trước khi bạn mua vé cho xe đó." /></ListItem>
            <ListItem><ListItemText primary="2. Mua vé giờ/ngày/tháng hoặc đặt chỗ" secondary="Giá chốt tại thời điểm mua; vé được cấp sau khi khoản thu được xác nhận." /></ListItem>
            <ListItem><ListItemText primary="3. Đến bãi, nhân viên xác nhận xe vào/ra" secondary="Phí phát sinh (nếu có) được máy chủ tính theo bảng giá công bố." /></ListItem>
            <ListItem><ListItemText primary="4. Cần hỗ trợ hoặc hoàn tiền" secondary="Gửi yêu cầu ngay trong mục Bãi xe của tôi sau khi đăng nhập." /></ListItem>
          </List>
          <Divider sx={{ my: 1.5 }} />
          <Typography variant="body2" color="text.secondary">Thông tin cập nhật lần cuối: {profile.profile_updated_at ? new Date(profile.profile_updated_at).toLocaleString("vi-VN") : "chưa cập nhật"}.</Typography>
        </Paper>
      </Stack>}
    </Container>
  </Box>;
}
