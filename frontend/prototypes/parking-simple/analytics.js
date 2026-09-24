/* Deterministic DEMO analysis. No network, model calls, personal-data prompts or mutations. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DemoAnalytics = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const DAY = 86400000;
  const OFFSET = 7 * 3600000;
  const stamp = value => typeof value === 'string' && /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : NaN;
  const day = value => Number.isFinite(stamp(value)) ? new Date(stamp(value) + OFFSET).toISOString().slice(0, 10) : '';
  const validDay = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
  const hour = value => new Date(stamp(value) + OFFSET).getUTCHours();
  const label = value => String(value).split('-').reverse().join('/');
  const money = value => new Intl.NumberFormat('vi-VN').format(value) + ' đ';
  const normalize = text => String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();
  const slotKey = value => String(value || '').trim().toUpperCase().replace(/[\s.\-]/g, '').replace(/\d+/g, digits => digits.replace(/^0+(?=\d)/, ''));
  const financialQuestion = text => /doanh thu|tong thu|thu chi|so tien|da thu|tien mat|thu nhap|doanh so|loi nhuan|tai chinh/.test(normalize(text));

  function periodRange(state, period, anchorDate) {
    const anchor = anchorDate || day(state?.now);
    if (!['day', 'week'].includes(period) || !validDay(anchor)) return null;
    return { start: new Date(Date.parse(anchor + 'T00:00:00Z') - (period === 'week' ? 6 : 0) * DAY).toISOString().slice(0, 10), end: anchor };
  }

  function availability(state, now) {
    const types = Array.isArray(state.vehicleTypes) ? state.vehicleTypes : [];
    const slots = Array.isArray(state.slots) ? state.slots : [];
    const zones = Array.isArray(state.zones) ? state.zones : [];
    const active = state.sessions.filter(s => s.status === 'active' && stamp(s.entry) <= now);
    const held = new Set((state.reservations || []).filter(r => r.status === 'confirmed'
      && stamp(r.end) > now && stamp(r.start) + 15 * 60000 >= now).map(r => slotKey(r.slot)));
    const occupied = new Set(active.map(s => slotKey(s.slot)));
    const rows = zones.map(z => ({ id: z.id, name: z.name, vehicleType: z.vehicleType, active: z.active !== false, capacity: 0, occupied: 0, reserved: 0, free: 0, inactive: 0 }));
    const byId = new Map(rows.map(r => [String(r.id), r]));
    for (const slot of slots) {
      let zone = byId.get(String(slot.zoneId));
      if (!zone) {
        const id = 'unassigned:' + (slot.zoneId || slot.vehicleType || 'unknown');
        zone = byId.get(id);
        if (!zone) { zone = { id, name: 'Chưa gán khu', active: false, capacity: 0, occupied: 0, reserved: 0, free: 0, inactive: 0 }; rows.push(zone); byId.set(id, zone); }
      }
      zone.capacity++;
      const type = types.find(t => t.id === slot.vehicleType);
      const enabled = slot.active !== false && zone.active && zone.vehicleType === slot.vehicleType && type && type.active !== false;
      if (occupied.has(slotKey(slot.code))) zone.occupied++;
      else if (!enabled) zone.inactive++;
      else if (held.has(slotKey(slot.code))) zone.reserved++;
      else zone.free++;
    }
    const totals = rows.reduce((sum, row) => { for (const key of ['capacity', 'occupied', 'reserved', 'free', 'inactive']) sum[key] += row[key]; return sum; }, { capacity: 0, occupied: 0, reserved: 0, free: 0, inactive: 0 });
    return { asOf: state.now, ...totals, occupancyPercent: totals.capacity ? Math.round(totals.occupied * 1000 / totals.capacity) / 10 : null,
      activeSessions: active.length, byZone: rows, note: 'Ảnh chụp hiện tại; không phải tỷ lệ lấp đầy trung bình của kỳ báo cáo.' };
  }

  function aggregate(state, filter) {
    if (!state || !Number.isFinite(stamp(state.now)) || !Array.isArray(state.sessions) || !Array.isArray(state.transactions))
      return { ok: false, error: 'Dữ liệu DEMO thiếu đồng hồ, lượt gửi hoặc phiếu thu hợp lệ.' };
    if (['sessions', 'transactions', 'vehicleTypes', 'slots', 'zones', 'reservations'].some(key => state[key] !== undefined
      && (!Array.isArray(state[key]) || state[key].some(row => !row || typeof row !== 'object' || Array.isArray(row)))))
      return { ok: false, error: 'Dữ liệu DEMO có danh sách hoặc bản ghi sai cấu trúc; chưa thể phân tích.' };
    if (!filter || !validDay(filter.start) || !validDay(filter.end) || filter.end < filter.start)
      return { ok: false, error: 'Chọn ngày hợp lệ; ngày kết thúc không được trước ngày bắt đầu.' };
    const from = Date.parse(filter.start + 'T00:00:00+07:00');
    const until = Date.parse(filter.end + 'T00:00:00+07:00') + DAY;
    if ((until - from) / DAY > 366) return { ok: false, error: 'Mỗi lần phân tích tối đa 366 ngày.' };
    const now = stamp(state.now);
    const inPeriod = value => stamp(value) >= from && stamp(value) < until && stamp(value) <= now;
    const daily = [];
    for (let at = from; at < until; at += DAY) daily.push({ day: day(new Date(at).toISOString()), arrivals: 0, departures: 0, movements: 0, revenue: 0, receiptCount: 0 });
    const dayMap = new Map(daily.map(row => [row.day, row]));
    const hourly = Array.from({ length: 24 }, (_, h) => ({ hour: h, label: `${String(h).padStart(2, '0')}:00–${String(h).padStart(2, '0')}:59`, arrivals: 0, departures: 0, movements: 0 }));
    let invalidSessions = 0;
    for (const session of state.sessions) {
      if (session.status === 'cancelled') continue;
      if (!Number.isFinite(stamp(session.entry)) || (session.exit && (!Number.isFinite(stamp(session.exit)) || stamp(session.exit) < stamp(session.entry)))) { invalidSessions++; continue; }
      for (const [field, counter] of [['entry', 'arrivals'], ['exit', 'departures']]) {
        if (field === 'exit' && !['closed', 'completed'].includes(session.status)) continue;
        if (inPeriod(session[field])) { hourly[hour(session[field])][counter]++; hourly[hour(session[field])].movements++; dayMap.get(day(session[field]))[counter]++; dayMap.get(day(session[field])).movements++; }
      }
    }
    let invalidReceipts = 0;
    const seen = new Set();
    const receipts = [];
    for (const receipt of state.transactions) {
      if (receipt.kind && receipt.kind !== 'receipt') continue;
      if (!Number.isSafeInteger(receipt.amount) || receipt.amount < 0 || !Number.isFinite(stamp(receipt.at)) || !receipt.id || seen.has(receipt.id)) { invalidReceipts++; continue; }
      seen.add(receipt.id);
      if (!inPeriod(receipt.at)) continue;
      receipts.push({ ...receipt });
      const row = dayMap.get(day(receipt.at));
      row.revenue += receipt.amount; row.receiptCount++;
    }
    const totals = daily.reduce((sum, row) => { for (const key of ['arrivals', 'departures', 'movements', 'revenue', 'receiptCount']) sum[key] += row[key]; return sum; }, { arrivals: 0, departures: 0, movements: 0, revenue: 0, receiptCount: 0 });
    if (!Number.isSafeInteger(totals.revenue)) return { ok: false, error: 'Tổng tiền vượt giới hạn tính chính xác; chưa thể sinh báo cáo.' };
    const peak = Math.max(0, ...hourly.map(row => row.movements));
    return { ok: true, period: { ...filter, timezone: 'Asia/Ho_Chi_Minh', asOf: state.now }, totals, daily, hourly,
      peakHours: peak ? hourly.filter(row => row.movements === peak) : [], current: availability(state, now),
      receipts: receipts.sort((a, b) => stamp(b.at) - stamp(a.at)),
      warnings: [...(invalidSessions ? [`Bỏ qua ${invalidSessions} lượt có thời gian không hợp lệ.`] : []), ...(invalidReceipts ? [`Bỏ qua ${invalidReceipts} phiếu thu không hợp lệ hoặc trùng mã.`] : [])] };
  }

  function generate(state, options = {}) {
    const { kind = 'report', period = 'day', anchorDate, question = '', role } = options;
    const fail = text => ({ ok: false, text, input: null });
    if (!['admin', 'manager', 'staff'].includes(role)) return fail('Phân tích vận hành chỉ dành cho nhân viên và quản lý bãi.');
    if (!['report', 'question', 'staff'].includes(kind)) return fail('Chọn báo cáo, hỏi đáp hoặc gợi ý nhân sự.');
    if (kind === 'question' && (!String(question).trim() || String(question).length > 600)) return fail('Nhập câu hỏi từ 1 đến 600 ký tự.');
    if (role === 'staff' && financialQuestion(question)) return fail('Nhân viên chỉ xem lưu lượng và chỗ trống. Báo cáo thu dành cho Manager và Admin.');
    const filter = periodRange(state, period, anchorDate);
    if (!filter) return fail('Chọn kỳ ngày/tuần và ngày kết thúc hợp lệ.');
    const result = aggregate(state, filter);
    if (!result.ok) return fail(result.error);
    const finance = ['admin', 'manager'].includes(role);
    // Snapshots contain aggregates only: no plates, identities, tickets or raw receipts.
    const input = { kind, period, role, question: String(question).trim(), periodRange: result.period,
      totals: { arrivals: result.totals.arrivals, departures: result.totals.departures, movements: result.totals.movements },
      daily: result.daily.map(({ revenue, receiptCount, ...row }) => finance ? { ...row, revenue, receiptCount } : row),
      hourly: result.hourly.map(row => ({ ...row })), current: result.current, warnings: result.warnings };
    if (finance) Object.assign(input.totals, { revenue: result.totals.revenue, receiptCount: result.totals.receiptCount });
    const q = normalize(question);
    const header = `AI mô phỏng · ${period === 'week' ? '7 ngày' : 'Ngày'} ${label(filter.start)}${filter.end !== filter.start ? ' – ' + label(filter.end) : ''} (giờ Việt Nam).`;
    const traffic = `${result.totals.arrivals} lượt vào, ${result.totals.departures} lượt ra; tổng ${result.totals.movements} thao tác vào/ra trong kỳ.`;
    const peaks = result.peakHours.length ? `Khung giờ có tổng lượt vào + ra cao nhất: ${result.peakHours.map(row => `${row.label} (${row.movements} lượt: ${row.arrivals} vào, ${row.departures} ra)`).join('; ')}. Không gộp các giờ liền nhau thành một giờ.` : 'Chưa có lượt vào/ra trong kỳ để xác định khung giờ cao điểm.';
    const localTime = new Date(stamp(state.now) + OFFSET).toISOString().slice(11, 16);
    const current = result.current.capacity ? `Hiện tại lúc ${localTime} theo đồng hồ demo: ${result.current.occupied}/${result.current.capacity} vị trí có xe (${result.current.occupancyPercent}%), ${result.current.free} chỗ nhận xe, ${result.current.reserved} chỗ giữ trước, ${result.current.inactive} chỗ ngừng dùng. Đây là hiện trạng, không phải lấp đầy trung bình trong kỳ.` : 'Chưa có vị trí đỗ được cấu hình; chưa tính được tỷ lệ lấp đầy hiện tại.';
    const staffing = result.totals.movements ? 'Gợi ý: ưu tiên người trực cổng và hỗ trợ thanh toán tại các khung cao điểm nêu trên; đối chiếu thêm lưu lượng từng ngày trước khi chia ca. Chưa có thời gian xử lý mỗi xe, năng suất hoặc lịch trực nên chưa đủ cơ sở đề xuất số nhân viên cụ thể.' : 'Chưa đủ dữ liệu để gợi ý khung trực hoặc số nhân viên. Cần ghi nhận lượt vào/ra trước.';
    let parts;
    if (kind === 'staff') parts = [traffic, peaks, staffing];
    else if (kind === 'report') parts = [traffic, ...(finance ? [`Đã thu ${money(result.totals.revenue)} từ ${result.totals.receiptCount} phiếu thu trong kỳ; không cộng phí chưa trả hoặc đặt chỗ chưa thu tiền.`] : []), peaks, current];
    else if (financialQuestion(q)) parts = [`Đã thu ${money(result.totals.revenue)} từ ${result.totals.receiptCount} phiếu thu trong kỳ. Đây là tiền đã ghi nhận, không phải lợi nhuận; chưa có dữ liệu chi phí.`];
    else if (/nhan su|nhan vien|chia ca|bo tri|lich truc/.test(q)) parts = [traffic, peaks, staffing];
    else if (/cao diem|dong nhat|dong xe|gio dong|khung gio/.test(q)) parts = [traffic, peaks];
    else if (/cho trong|con.*cho|lap day|suc chua|vi tri/.test(q)) parts = [current, ...result.current.byZone.map(z => `${z.name}: ${z.free} chỗ nhận xe, ${z.occupied} có xe, ${z.reserved} giữ trước, ${z.inactive} ngừng dùng.`)];
    else if (/bao cao|tong quan|luu luong|luot|xe vao|xe ra/.test(q)) parts = [traffic, peaks, current];
    else parts = ['Chưa có dữ liệu phù hợp để trả lời câu hỏi này. Bạn có thể hỏi về lượt vào/ra, cao điểm, chỗ trống hoặc gợi ý nhân sự.'];
    const text = [header, ...parts, ...result.warnings, 'Kết quả được tạo từ dữ liệu DEMO bằng quy tắc cố định; chưa gọi AI thật và không dự báo lưu lượng tương lai.'].join('\n\n');
    return { ok: true, text, input };
  }
  return { aggregate, generate, periodRange, day, validDay, financialQuestion };
});
