/* Standalone prototype only. Data is in memory; no network or real payments. */
(function () {
  'use strict';

  const MINUTE = 60000;
  const GRACE = 15 * MINUTE;
  const DAY = 24 * 60 * MINUTE;
  const vehicleTypes = [
    { id: 'car', label: 'Ô tô', prefix: 'B', requiresPlate: true, active: true },
    { id: 'motorbike', label: 'Xe máy', prefix: 'A', requiresPlate: true, active: true },
    { id: 'bicycle', label: 'Xe đạp', prefix: 'C', requiresPlate: false, active: true },
    { id: 'ebike', label: 'Xe đạp điện', prefix: 'D', requiresPlate: false, active: true }
  ];
  const normalize = value => String(value || '').trim().toUpperCase().replace(/[\s.\-]/g, '');
  const plateLabel = value => String(value || '').trim().toUpperCase();
  const timestamp = value => new Date(value).getTime();
  const validPlate = value => /^[0-9]{2}[A-Z][A-Z0-9]{0,2}[0-9]{4,6}$/.test(normalize(value));
  const clone = value => JSON.parse(JSON.stringify(value));
  const typesFor = state => (Array.isArray(state?.vehicleTypes) ? state.vehicleTypes : vehicleTypes).map(type => ({ ...type, rate: Number(state?.rates?.[type.id] ?? type.rate ?? 0) }));
  const typeInfo = (id, state) => typesFor(state).find(type => type.id === id);
  const typeLabel = (id, state) => typeInfo(id, state)?.label || 'Phương tiện';
  const validIdentifier = (value, vehicleType, state) => typeInfo(vehicleType, state)?.requiresPlate
    ? validPlate(value)
    : /^[A-Z0-9][A-Z0-9-]{0,19}$/.test(plateLabel(value));
  const slotKey = code => normalize(code).replace(/\d+/g, digits => digits.replace(/^0+(?=\d)/, ''));
  const labelKey = label => label.toLocaleLowerCase('vi-VN').normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd').replace(/[^a-z0-9]/g, '');
  const overlap = (aStart, aEnd, bStart, bEnd) => timestamp(aStart) < timestamp(bEnd) && timestamp(bStart) < timestamp(aEnd);

  function seed() {
    const state = {
      now: '2026-09-23T16:30:00+07:00',
      vehicleTypes: clone(vehicleTypes),
      zones: [
        { id: 'zone_car', name: 'Khu B · Ô tô', vehicleType: 'car', capacity: 12, active: true },
        { id: 'zone_motorbike', name: 'Khu A · Xe máy', vehicleType: 'motorbike', capacity: 24, active: true },
        { id: 'zone_bicycle', name: 'Khu C · Xe đạp', vehicleType: 'bicycle', capacity: 12, active: true },
        { id: 'zone_ebike', name: 'Khu D · Xe đạp điện', vehicleType: 'ebike', capacity: 8, active: true }
      ],
      customers: [
        { id: 'KH-1', name: 'Khách vé tháng mẫu', phone: '0900000001', email: 'monthly@example.test', active: true, owned: true },
        { id: 'KH-2', name: 'Khách quen mẫu', phone: '0900000002', email: 'regular@example.test', active: true }
      ],
      vehicles: [
        { id: 'XE-1', customerId: 'KH-1', plate: '59A-888.88', vehicleType: 'car', active: true },
        { id: 'XE-2', customerId: 'KH-2', plate: '59B1-555.55', vehicleType: 'motorbike', active: true },
        { id: 'XE-3', customerId: 'KH-1', plate: '59A-888.89', vehicleType: 'car', active: true }
      ],
      monthlyPasses: [
        { id: 'VT-1', customerId: 'KH-1', plate: '59A-888.88', vehicleType: 'car', startDate: '2026-09-01', endDate: '2026-09-30', price: 600000, active: true },
        { id: 'VT-2', customerId: 'KH-2', plate: '59B1-555.55', vehicleType: 'motorbike', startDate: '2026-08-01', endDate: '2026-08-31', price: 150000, active: true },
        { id: 'VT-3', customerId: 'KH-1', plate: '59A-888.89', vehicleType: 'car', startDate: '2026-10-01', endDate: '2026-10-31', price: 600000, active: true }
      ],
      capacity: { car: 12, motorbike: 24, bicycle: 12, ebike: 8 },
      rates: { car: 20000, motorbike: 5000, bicycle: 2000, ebike: 3000 },
      sessions: [
        { id: 'LX-2048', plate: '59A-123.45', vehicleType: 'car', entry: '2026-09-23T14:05:00+07:00', exit: null, slot: 'B-01', status: 'active', paid: 0, owned: true, ticket: 'VE-2048', source: 'manual' },
        { id: 'LX-4096', plate: '59B1-678.90', vehicleType: 'motorbike', entry: '2026-09-23T15:10:00+07:00', exit: null, slot: 'A-01', status: 'active', paid: 0, owned: false, ticket: 'VE-4096', source: 'manual' },
        { id: 'LX-2049', plate: '51K-456.78', vehicleType: 'car', entry: '2026-09-23T15:45:00+07:00', exit: null, slot: 'B-02', status: 'active', paid: 0, owned: false, ticket: 'VE-2049', source: 'camera' },
        { id: 'LX-4097', plate: '59C2-345.67', vehicleType: 'motorbike', entry: '2026-09-23T16:00:00+07:00', exit: null, slot: 'A-02', status: 'active', paid: 0, owned: false, ticket: 'VE-4097', source: 'camera' },
        { id: 'LX-2001', plate: '59A-123.45', vehicleType: 'car', entry: '2026-09-22T09:10:00+07:00', exit: '2026-09-22T11:05:00+07:00', slot: 'B-01', status: 'closed', paid: 40000, closedGross: 40000, owned: true, ticket: 'VE-2001', source: 'manual' },
        { id: 'LX-5000', plate: 'XD-001', vehicleType: 'bicycle', entry: '2026-09-23T15:20:00+07:00', exit: null, slot: 'C-01', status: 'active', paid: 0, owned: true, ticket: 'VE-5000', source: 'manual' }
      ],
      reservations: [
        { id: 'DC-1001', plate: '59A-123.45', vehicleType: 'car', start: '2026-09-24T08:00:00+07:00', end: '2026-09-24T10:00:00+07:00', status: 'confirmed', slot: 'B-03' }
      ],
      transactions: [
        { id: 'TT-1001', sessionId: 'LX-2001', plate: '59A-123.45', amount: 40000, method: 'online', at: '2026-09-22T11:05:00+07:00' }
      ],
      audit: [{ at: '2026-09-23T16:00:00+07:00', text: 'Camera ghi nhận xe 59C2-345.67 vào vị trí A-02 (mô phỏng).' }],
      support: [],
      customerAccess: []
    };
    state.slots = typesFor(state).flatMap(type => Array.from({ length: state.capacity[type.id] }, (_, index) => ({
      code: `${type.prefix}-${String(index + 1).padStart(2, '0')}`,
      vehicleType: type.id, zoneId: `zone_${type.id}`, active: true
    })));
    state.sessions.forEach(session => { session.rateSnapshot = state.rates[session.vehicleType]; });
    state.transactions[0].source = 'parking';
    // Seven calendar days, paired receipts, distinct occupied intervals/slots.
    for (let day = 17; day <= 23; day += 1) {
      for (let index = 0; index < 4; index += 1) {
        const vehicleType = index % 2 ? 'motorbike' : 'car';
        const hour = [7, 8, 11, 13][index];
        const entry = `2026-09-${day}T${String(hour).padStart(2, '0')}:00:00+07:00`;
        const exit = `2026-09-${day}T${String(hour + 1).padStart(2, '0')}:30:00+07:00`;
        const id = `LX-${6000 + (day - 17) * 4 + index}`;
        const amount = state.rates[vehicleType] * 2;
        const plate = vehicleType === 'car' ? `51A-${day}${index}11` : `59D1-${day}${index}22`;
        state.sessions.push({ id, plate, vehicleType, entry, exit, slot: index % 2 ? 'A-04' : 'B-04',
          status: 'closed', paid: amount, closedGross: amount, owned: false, ticket: id.replace('LX-', 'VE-'),
          source: 'manual', rateSnapshot: state.rates[vehicleType] });
        state.transactions.push({ id: `TT-${2000 + (day - 17) * 4 + index}`, sessionId: id, source: 'parking', plate,
          amount, method: index % 2 ? 'cash' : 'online', at: exit });
      }
    }
    state.monthlyPasses.forEach((pass, index) => state.transactions.push({ id: `TT-${3000 + index}`,
      sessionId: null, monthlyPassId: pass.id, source: 'monthly', plate: pass.plate, amount: pass.price,
      method: 'cash', at: index === 1 ? '2026-08-01T08:00:00+07:00' : '2026-09-01T08:00:00+07:00' }));
    return state;
  }

  function quote(state, session) {
    if (!session) return { minutes: 0, gross: 0, paid: 0, due: 0, monthlyPassId: null, coverageStart: null, coverageEnd: null, coveredMinutes: 0, billableMinutes: 0, rate: 0 };
    const end = timestamp(session.status === 'closed' && session.exit ? session.exit : state.now);
    const start = timestamp(session.entry);
    const elapsed = Math.max(0, end - start);
    const rate = Number(session.rateSnapshot == null ? state.rates[session.vehicleType] : session.rateSnapshot) || 0;
    const covered = session.monthlyPassId && session.coverageEnd ? Math.max(0, Math.min(end, timestamp(session.coverageEnd)) - start) : 0;
    const billable = Math.max(0, elapsed - covered);
    // Minimum one hourly block for a walk-in, even an immediate departure.
    // A monthly-covered stay is free; only time beyond its entry snapshot bills.
    const blocks = session.monthlyPassId ? Math.ceil(billable / (60 * MINUTE)) : Math.max(1, Math.ceil(billable / (60 * MINUTE)));
    const gross = session.closedGross == null ? blocks * rate : Number(session.closedGross);
    const paid = Math.max(0, Number(session.paid) || 0);
    return { minutes: Math.ceil(elapsed / MINUTE), gross, paid, due: Math.max(0, gross - paid), rate,
      monthlyPassId: session.monthlyPassId || null, coverageStart: session.coverageStart || null,
      coverageEnd: session.coverageEnd || null, coveredMinutes: Math.ceil(covered / MINUTE), billableMinutes: Math.ceil(billable / MINUTE) };
  }

  const zonesFor = state => (state.zones || []).map(zone => ({ ...zone }));
  const dayStart = value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return NaN;
    const at = timestamp(`${value}T00:00:00+07:00`);
    return Number.isFinite(at) && new Date(at + 7 * 60 * MINUTE).toISOString().slice(0, 10) === value ? at : NaN;
  };
  const dateAt = at => new Date(at + 7 * 60 * MINUTE).toISOString().slice(0, 10);
  function passStatus(state, pass) {
    const key = !pass.active ? 'inactive' : timestamp(state.now) < dayStart(pass.startDate) ? 'upcoming'
      : timestamp(state.now) >= dayStart(pass.endDate) + DAY ? 'expired' : 'active';
    return { key, label: { active: 'Còn hạn', upcoming: 'Chưa đến hạn', expired: 'Hết hạn', inactive: 'Ngừng dùng' }[key] };
  }
  function usableSlot(state, slot) {
    const zone = (state.zones || []).find(item => item.id === slot.zoneId);
    const type = typeInfo(slot.vehicleType, state);
    return slot.active !== false && !!type && type.active !== false && !!zone && zone.active !== false && zone.vehicleType === slot.vehicleType;
  }
  function slotStatus(state, slot) {
    if (activeSlots(state).has(slotKey(slot.code))) return 'occupied';
    if (!usableSlot(state, slot)) return 'inactive';
    return liveHolds(state).some(item => slotKey(item.slot) === slotKey(slot.code)) ? 'reserved' : 'available';
  }
  function recalculateCapacity(state) {
    state.capacity = Object.fromEntries(typesFor(state).map(type => [type.id,
      (state.slots || []).filter(slot => slot.vehicleType === type.id && usableSlot(state, slot)).length]));
  }

  function liveHolds(state) {
    const now = timestamp(state.now);
    return state.reservations.filter(item => item.status === 'confirmed' && now <= timestamp(item.start) + GRACE && now < timestamp(item.end));
  }

  function slotsFor(state, vehicleType) {
    if (!typeInfo(vehicleType, state)) return [];
    return (state.slots || []).filter(slot => slot.vehicleType === vehicleType).map(slot => ({ ...slot }));
  }

  function activeSlots(state) {
    return new Set(state.sessions.filter(item => item.status === 'active').map(item => slotKey(item.slot)));
  }

  function freeSlots(state, vehicleType, excludeReservationId) {
    const used = activeSlots(state);
    liveHolds(state).filter(item => item.id !== excludeReservationId).forEach(item => used.add(slotKey(item.slot)));
    return slotsFor(state, vehicleType).filter(slot => usableSlot(state, slot) && !used.has(slotKey(slot.code)));
  }

  function nextSlotCode(state, vehicleType) {
    const type = typeInfo(vehicleType, state);
    if (!type) return '';
    const used = new Set((state.slots || []).map(slot => slotKey(slot.code)));
    let index = 1;
    let code;
    do {
      code = `${type.prefix}-${String(index++).padStart(2, '0')}`;
    } while (used.has(slotKey(code)));
    return code;
  }

  function available(state, vehicleType) {
    return freeSlots(state, vehicleType).length;
  }

  function nextId(items, prefix, start) {
    const maximum = items.reduce((max, item) => {
      const match = String(item.id || '').match(/-(\d+)$/);
      return match ? Math.max(max, Number(match[1])) : max;
    }, start);
    return `${prefix}-${maximum + 1}`;
  }

  function vehicleIdentifier(state, supplied, vehicleType) {
    const value = plateLabel(supplied);
    const type = typeInfo(vehicleType, state);
    if (value || type?.requiresPlate) return value;
    const prefix = vehicleType === 'bicycle' ? 'XD' : vehicleType === 'ebike' ? 'XDD' : `${type.prefix}X`;
    const pattern = new RegExp(`^${prefix}-?(\\d+)$`);
    const maximum = [...state.sessions, ...state.reservations, ...(state.vehicles || [])].reduce((max, item) => {
      const match = plateLabel(item.plate).match(pattern);
      return match ? Math.max(max, Number(match[1])) : max;
    }, 0);
    return `${prefix}-${String(maximum + 1).padStart(4, '0')}`;
  }

  function lookupSession(state, identifier, vehicleType) {
    const value = normalize(identifier);
    if (!value || !typeInfo(vehicleType, state)) return undefined;
    const matches = state.sessions.filter(item => item.status === 'active' && item.vehicleType === vehicleType
      && (normalize(item.plate) === value || normalize(item.ticket) === value));
    return matches.length === 1 ? matches[0] : undefined;
  }

  function log(state, text) {
    state.audit.unshift({ at: state.now, text });
  }

  function expire(state) {
    const now = timestamp(state.now);
    state.reservations.forEach(item => {
      if (item.status === 'confirmed' && (now > timestamp(item.start) + GRACE || now >= timestamp(item.end))) {
        item.status = 'expired';
        log(state, `Đặt chỗ ${item.id} đã hết thời gian giữ chỗ.`);
      }
    });
  }

  const catalogueActions = new Set(['save-zone', 'delete-zone', 'add-vehicle-type', 'save-vehicle-type',
    'delete-vehicle-type', 'add-slot', 'save-slot', 'delete-slot', 'save-customer', 'save-vehicle', 'save-pass', 'renew-pass']);
  const safeName = value => String(value || '').trim().replace(/\s+/g, ' ').normalize('NFC');
  const validName = (value, max = 80) => value.length >= 2 && value.length <= max && !/[\u0000-\u001f\u007f<>]/.test(value);
  const validMoney = value => (typeof value === 'number' || (typeof value === 'string' && value.trim() !== ''))
    && Number.isSafeInteger(Number(value)) && Number(value) >= 0 && Number(value) <= 1000000000;
  const busyPlate = (state, plate) => state.sessions.some(item => item.status === 'active' && normalize(item.plate) === normalize(plate))
    || liveHolds(state).some(item => normalize(item.plate) === normalize(plate));
  const referencedPlate = (state, plate) => [...state.sessions, ...state.reservations, ...(state.monthlyPasses || [])]
    .some(item => normalize(item.plate) === normalize(plate));
  const slotHistory = (state, code) => [...state.sessions, ...state.reservations].some(item => slotKey(item.slot) === slotKey(code));
  const slotBusy = (state, code) => activeSlots(state).has(slotKey(code)) || liveHolds(state).some(item => slotKey(item.slot) === slotKey(code));
  const customerBusy = (state, id) => (state.vehicles || []).some(vehicle => vehicle.customerId === id && busyPlate(state, vehicle.plate));

  function catalogAction(state, action) {
    if (!catalogueActions.has(action.type)) return null;
    const no = message => ({ ok: false, message });
    const yes = message => ({ ok: true, message });
    if (!['admin', 'manager'].includes(action.role)) return no('Chỉ Admin hoặc Manager được quản lý danh mục.');
    if (action.active !== undefined && typeof action.active !== 'boolean') return no('Trạng thái hoạt động chưa hợp lệ.');
    state.zones ||= []; state.customers ||= []; state.vehicles ||= []; state.monthlyPasses ||= [];
    const type = typeInfo(action.vehicleType, state);

    if (['save-vehicle-type', 'add-vehicle-type'].includes(action.type)) {
      const previous = action.id ? state.vehicleTypes.find(item => item.id === action.id) : null;
      if (action.id && !previous) return no('Không tìm thấy loại xe.');
      const label = safeName(action.label), prefix = plateLabel(action.prefix), rate = Number(action.rate);
      const active = action.active ?? previous?.active ?? true;
      if (!validName(label, 40) || !labelKey(label)) return no('Tên loại xe từ 2 đến 40 ký tự, không chứa dấu < >.');
      if (!/^[A-Z][A-Z0-9]{0,5}$/.test(prefix)) return no('Mã loại gồm 1–6 chữ/số, bắt đầu bằng chữ.');
      if (typeof action.requiresPlate !== 'boolean') return no('Chọn loại xe có hoặc không có biển số.');
      if (!validMoney(action.rate)) return no('Giá giờ phải là số nguyên từ 0 đến 1 tỷ đồng.');
      if (state.vehicleTypes.some(item => item.id !== previous?.id && (labelKey(item.label) === labelKey(label) || slotKey(item.prefix) === slotKey(prefix)))) return no('Tên hoặc mã loại xe đã tồn tại.');
      if (previous && !active && (state.sessions.some(item => item.status === 'active' && item.vehicleType === previous.id)
        || liveHolds(state).some(item => item.vehicleType === previous.id))) return no('Loại xe đang có xe hoặc đặt chỗ; xử lý các lượt này trước khi ngừng.');
      if (previous && previous.requiresPlate !== action.requiresPlate && [...state.sessions, ...state.reservations, ...state.vehicles, ...state.monthlyPasses].some(item => item.vehicleType === previous.id)) return no('Không đổi cách nhận dạng loại xe đã có hồ sơ hoặc lịch sử; hãy tạo loại mới.');
      const id = previous?.id || `custom_${prefix.toLowerCase()}`;
      if (!previous && state.vehicleTypes.some(item => item.id === id)) return no('Mã định danh loại xe đã dùng; chọn mã khác.');
      const record = { id, label, prefix, requiresPlate: action.requiresPlate, active };
      if (previous) Object.assign(previous, record); else state.vehicleTypes.push(record);
      state.rates[id] = rate;
      return yes(`Đã ${previous ? 'cập nhật' : 'thêm'} loại xe ${label}. Giá mới chỉ áp dụng lượt vào sau thay đổi.`);
    }
    if (action.type === 'delete-vehicle-type') {
      const previous = state.vehicleTypes.find(item => item.id === action.id);
      if (!previous) return no('Không tìm thấy loại xe.');
      if ([...state.slots, ...state.zones, ...state.sessions, ...state.reservations, ...state.vehicles, ...state.monthlyPasses].some(item => item.vehicleType === previous.id)) return no('Loại xe đã được dùng; giữ lịch sử và chuyển sang ngừng hoạt động khi không còn xe/đặt chỗ.');
      state.vehicleTypes = state.vehicleTypes.filter(item => item.id !== previous.id);
      delete state.rates[previous.id];
      return yes(`Đã xóa loại xe chưa sử dụng ${previous.label}.`);
    }
    if (action.type === 'save-zone') {
      const previous = action.id ? state.zones.find(item => item.id === action.id) : null;
      if (action.id && !previous) return no('Không tìm thấy khu vực.');
      const name = safeName(action.name), capacity = Number(action.capacity), active = action.active ?? previous?.active ?? true;
      if (!validName(name) || state.zones.some(item => item.id !== previous?.id && labelKey(item.name) === labelKey(name))) return no('Tên khu vực chưa hợp lệ hoặc đã tồn tại.');
      if (!type || (!previous && type.active === false)) return no('Chọn loại xe đang hoạt động cho khu vực.');
      if (!Number.isInteger(capacity) || capacity < 0 || capacity > 1000) return no('Sức chứa khu vực là số nguyên từ 0 đến 1.000.');
      const slots = state.slots.filter(item => item.zoneId === previous?.id);
      if (capacity < slots.length) return no('Sức chứa không được nhỏ hơn số vị trí hiện có trong khu vực.');
      if (previous && previous.vehicleType !== action.vehicleType && slots.length) return no('Khu vực còn vị trí đỗ; không đổi loại xe của khu vực.');
      if (!active && slots.some(slot => slotBusy(state, slot.code))) return no('Khu vực đang có xe hoặc đặt chỗ; chưa thể ngừng.');
      const record = { id: previous?.id || nextId(state.zones, 'KV', 0), name, vehicleType: action.vehicleType, capacity, active };
      if (previous) Object.assign(previous, record); else state.zones.push(record);
      return yes(`Đã lưu khu vực ${name}. Sức chứa không tự tạo vị trí; hãy thêm từng vị trí đỗ.`);
    }
    if (action.type === 'delete-zone') {
      const previous = state.zones.find(item => item.id === action.id);
      if (!previous) return no('Không tìm thấy khu vực.');
      if (state.slots.some(item => item.zoneId === previous.id)) return no('Khu vực còn vị trí đỗ; không xóa. Có thể ngừng khu vực khi không còn xe/đặt chỗ.');
      state.zones = state.zones.filter(item => item.id !== previous.id);
      return yes(`Đã xóa khu vực chưa sử dụng ${previous.name}.`);
    }
    if (['save-slot', 'add-slot'].includes(action.type)) {
      const originalCode = action.originalCode || (action.newCode ? action.code : null);
      const previous = originalCode ? state.slots.find(item => slotKey(item.code) === slotKey(originalCode)) : null;
      if (originalCode && !previous) return no('Không tìm thấy vị trí đỗ.');
      const code = plateLabel(action.newCode || action.code), active = action.active ?? previous?.active ?? true;
      if (!code || code.length > 20 || !/^[A-Z0-9]+(?:-[A-Z0-9]+)*$/.test(code)) return no('Mã vị trí từ 1–20 chữ/số, có thể chứa gạch ngang.');
      if (state.slots.some(item => item !== previous && slotKey(item.code) === slotKey(code))) return no('Mã vị trí đã tồn tại trong bãi.');
      if (!type) return no('Chọn loại xe hợp lệ.');
      let zone = state.zones.find(item => item.id === action.zoneId);
      // Compatibility: the original Add Space form had no area field. Its
      // manager action explicitly grows a matching area; new forms send zoneId.
      if (!action.zoneId && action.type === 'add-slot') {
        zone = state.zones.find(item => item.vehicleType === action.vehicleType && item.active);
        if (!zone) {
          zone = { id: nextId(state.zones, 'KV', 0), name: `Khu ${type.prefix} · ${type.label}`, vehicleType: type.id, capacity: 0, active: true };
          state.zones.push(zone);
        }
        zone.capacity = Math.max(zone.capacity, state.slots.filter(item => item.zoneId === zone.id).length + 1);
      }
      if (!zone || zone.vehicleType !== action.vehicleType) return no('Khu vực phải tồn tại và cùng loại xe với vị trí.');
      if (active && (!zone.active || type.active === false)) return no('Khu vực hoặc loại xe đã ngừng; không bật vị trí để nhận xe.');
      const changedIdentity = previous && (previous.code !== code || previous.zoneId !== zone.id || previous.vehicleType !== action.vehicleType);
      if (previous && changedIdentity && slotHistory(state, previous.code)) return no('Vị trí đã có lịch sử; không đổi mã/khu/loại. Hãy ngừng vị trí và tạo vị trí mới.');
      if (previous && (!active || changedIdentity) && slotBusy(state, previous.code)) return no('Vị trí đang có xe hoặc giữ chỗ; chưa thể thay đổi.');
      if (state.slots.filter(item => item !== previous && item.zoneId === zone.id).length >= zone.capacity) return no('Khu vực đã đạt sức chứa; điều chỉnh khu vực trước khi thêm vị trí.');
      const record = { code, zoneId: zone.id, vehicleType: action.vehicleType, active };
      if (previous) Object.assign(previous, record); else state.slots.push(record);
      return yes(`Đã lưu vị trí ${code}.`);
    }
    if (action.type === 'delete-slot') {
      const previous = state.slots.find(item => slotKey(item.code) === slotKey(action.code));
      if (!previous) return no('Không tìm thấy vị trí đỗ.');
      if (slotHistory(state, previous.code)) return no('Vị trí có lượt gửi hoặc đặt chỗ trong lịch sử; dùng ngừng hoạt động, không xóa.');
      state.slots = state.slots.filter(item => item !== previous);
      return yes(`Đã xóa vị trí chưa sử dụng ${previous.code}.`);
    }
    if (action.type === 'save-customer') {
      const previous = action.id ? state.customers.find(item => item.id === action.id) : null;
      if (action.id && !previous) return no('Không tìm thấy khách hàng.');
      const name = safeName(action.name), phone = String(action.phone || '').trim(), email = String(action.email || '').trim();
      const active = action.active ?? previous?.active ?? true;
      if (!validName(name) || !/^(?:\+84|0)[0-9]{8,10}$/.test(phone)) return no('Nhập tên khách và số điện thoại Việt Nam hợp lệ.');
      if (email && (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 120)) return no('Email chưa hợp lệ.');
      if (state.customers.some(item => item.id !== previous?.id && item.phone === phone)) return no('Số điện thoại đã thuộc hồ sơ khách khác.');
      if (previous && !active && customerBusy(state, previous.id)) return no('Khách còn xe hoặc đặt chỗ trong bãi; chưa thể ngừng hồ sơ.');
      const record = { id: previous?.id || nextId(state.customers, 'KH', 0), name, phone, email, active };
      if (previous) Object.assign(previous, record); else state.customers.push(record);
      return yes(`Đã lưu khách hàng ${name}.`);
    }
    if (action.type === 'save-vehicle') {
      const previous = action.id ? state.vehicles.find(item => item.id === action.id) : null;
      if (action.id && !previous) return no('Không tìm thấy hồ sơ xe.');
      if (!type) return no('Chọn loại xe hợp lệ.');
      const plate = vehicleIdentifier(state, action.plate, action.vehicleType), active = action.active ?? previous?.active ?? true;
      const customer = state.customers.find(item => item.id === action.customerId);
      if (!customer || (active && (!customer.active || type.active === false))) return no('Chọn khách và loại xe đang hoạt động.');
      if (!validIdentifier(plate, action.vehicleType, state)) return no('Biển số hoặc mã xe chưa hợp lệ.');
      if (state.vehicles.some(item => item !== previous && normalize(item.plate) === normalize(plate))) return no('Biển số hoặc mã xe đã có hồ sơ.');
      if (previous && (normalize(previous.plate) !== normalize(plate) || previous.vehicleType !== action.vehicleType || previous.customerId !== customer.id)
        && referencedPlate(state, previous.plate)) return no('Xe đã có vé/lượt/đặt chỗ; không thay định danh hoặc chủ xe trong lịch sử.');
      if (previous && !active && busyPlate(state, previous.plate)) return no('Xe đang gửi hoặc đã giữ chỗ; chưa thể ngừng hồ sơ xe.');
      const record = { id: previous?.id || nextId(state.vehicles, 'XE', 0), customerId: customer.id, plate, vehicleType: action.vehicleType, active };
      if (previous) Object.assign(previous, record); else state.vehicles.push(record);
      return yes(`Đã lưu hồ sơ xe ${plate}.`);
    }
    if (['save-pass', 'renew-pass'].includes(action.type)) {
      const original = action.id ? state.monthlyPasses.find(item => item.id === action.id) : null;
      if (action.id && !original) return no('Không tìm thấy vé tháng.');
      const renewal = action.type === 'renew-pass';
      if (renewal && !original) return no('Chọn vé tháng cần gia hạn.');
      const data = renewal ? { ...original, ...action, startDate: action.startDate || dateAt(dayStart(original.endDate) + DAY),
        price: action.price === undefined ? original.price : action.price, active: true } : action;
      const previous = renewal ? null : original;
      const plate = plateLabel(data.plate), active = data.active ?? previous?.active ?? true;
      const start = dayStart(data.startDate), end = dayStart(data.endDate);
      if (![start, end].every(Number.isFinite) || end < start || !validMoney(data.price)) return no('Ngày hiệu lực hoặc giá vé chưa hợp lệ. Ngày hết hạn phải từ ngày bắt đầu.');
      if (renewal && start <= dayStart(original.endDate)) return no('Kỳ gia hạn phải bắt đầu sau kỳ vé gốc.');
      const vehicle = state.vehicles.find(item => normalize(item.plate) === normalize(plate) && item.vehicleType === data.vehicleType && item.customerId === data.customerId);
      const customer = state.customers.find(item => item.id === data.customerId);
      if (!vehicle || !customer) return no('Đăng ký xe đúng loại và đúng khách trước khi cấp vé tháng.');
      if (!previous && (!vehicle.active || !customer.active || typeInfo(data.vehicleType, state)?.active === false)) return no('Khách, xe và loại xe phải đang hoạt động để cấp vé.');
      const fields = ['customerId', 'vehicleType', 'startDate', 'endDate'];
      const changed = previous && (fields.some(key => previous[key] !== data[key]) || normalize(previous.plate) !== normalize(plate) || previous.price !== Number(data.price));
      if (changed && (state.transactions.some(item => item.monthlyPassId === previous.id) || state.sessions.some(item => item.monthlyPassId === previous.id))) return no('Vé đã ghi nhận tiền hoặc sử dụng; chỉ đổi trạng thái. Dùng Gia hạn để tạo kỳ mới và giữ lịch sử.');
      if (active && state.monthlyPasses.some(item => item !== previous && item.active && normalize(item.plate) === normalize(plate)
        && item.vehicleType === data.vehicleType && start <= dayStart(item.endDate) && dayStart(item.startDate) <= end)) return no('Khoảng hiệu lực chồng lấn vé tháng đang hoạt động của xe.');
      const record = { id: previous?.id || nextId(state.monthlyPasses, 'VT', 0), customerId: data.customerId, plate,
        vehicleType: data.vehicleType, startDate: data.startDate, endDate: data.endDate, price: Number(data.price), active };
      if (previous) Object.assign(previous, record);
      else {
        state.monthlyPasses.push(record);
        state.transactions.unshift({ id: nextId(state.transactions, 'TT', 1000), sessionId: null, monthlyPassId: record.id,
          source: 'monthly', plate, amount: record.price, method: 'cash', at: state.now });
      }
      return yes(`Đã ${renewal ? 'gia hạn' : previous ? 'cập nhật' : 'cấp'} vé tháng ${record.id}. ${previous ? 'Lượt đang gửi giữ quyền đã chốt khi vào.' : 'Đã ghi nhận thu tiền mặt mô phỏng; không chuyển tiền thật.'}`);
    }
    return no('Thao tác danh mục chưa được hỗ trợ.');
  }

  function apply(original, action) {
    const state = clone(original);
    const finish = (ok, message, sessionId) => ({ state, ok, message, ...(sessionId ? { sessionId } : {}) });
    const fail = message => ({ state: clone(original), ok: false, message });
    if (!action || typeof action.type !== 'string') return fail('Thao tác chưa hợp lệ.');
    expire(state);

    const catalogResult = catalogAction(state, action);
    if (catalogResult) {
      if (!catalogResult.ok) return fail(catalogResult.message);
      recalculateCapacity(state);
      log(state, catalogResult.message);
      return finish(true, catalogResult.message);
    }

    if (action.type === 'advance') {
      const minutes = Number(action.minutes);
      if (!Number.isFinite(minutes) || minutes < 1 || minutes > 30 * 24 * 60) return fail('Nhập thời gian tăng từ 1 phút đến 30 ngày.');
      state.now = new Date(timestamp(state.now) + minutes * MINUTE).toISOString();
      expire(state);
      log(state, `Đồng hồ mô phỏng tăng ${minutes} phút.`);
      return finish(true, `Đã tăng ${minutes} phút. Phí được tính lại theo thời gian gửi.`);
    }

    if (action.type === 'checkin') {
      if (!typeInfo(action.vehicleType, state) || typeInfo(action.vehicleType, state).active === false) return fail('Chọn loại xe đang hoạt động.');
      const plate = vehicleIdentifier(state, action.plate, action.vehicleType);
      if (!validIdentifier(plate, action.vehicleType, state)) return fail(typeInfo(action.vehicleType, state).requiresPlate
        ? 'Kiểm tra biển số. Ví dụ: 59A-123.45 hoặc 59B1-678.90.'
        : 'Mã xe chỉ gồm chữ, số và dấu gạch ngang, tối đa 20 ký tự. Có thể để trống để cấp mã tự động.');
      if (state.sessions.some(item => item.status === 'active' && normalize(item.plate) === normalize(plate))) return fail('Biển số hoặc mã xe này đang có một lượt gửi trong bãi.');
      const registered = (state.vehicles || []).find(item => normalize(item.plate) === normalize(plate));
      if (registered && (registered.vehicleType !== action.vehicleType || !registered.active)) return fail('Xe đã đăng ký khác loại hoặc ngừng hoạt động; hãy kiểm tra hồ sơ xe.');
      const now = timestamp(state.now);
      const reservation = liveHolds(state).find(item => normalize(item.plate) === normalize(plate) && item.vehicleType === action.vehicleType && now >= timestamp(item.start) && now <= timestamp(item.start) + GRACE);
      const occupied = activeSlots(state);
      const slot = reservation ? reservation.slot : freeSlots(state, action.vehicleType)[0]?.code;
      if (!slot || occupied.has(slotKey(slot)) || !slotsFor(state, action.vehicleType).some(item => usableSlot(state, item) && slotKey(item.code) === slotKey(slot))) return fail('Chưa có vị trí phù hợp để nhận xe. Kiểm tra chỗ trống hoặc vị trí đang được giữ trước.');
      const id = nextId(state.sessions, 'LX', 5000);
      const session = { id, plate, vehicleType: action.vehicleType, entry: state.now, exit: null, slot, status: 'active', paid: 0, owned: false, ticket: id.replace('LX-', 'VE-'), source: action.source === 'camera' ? 'camera' : 'manual', rateSnapshot: Number(state.rates[action.vehicleType]) };
      if (registered) { session.vehicleId = registered.id; session.customerId = registered.customerId; }
      const pass = (state.monthlyPasses || []).find(item => item.active && item.vehicleType === action.vehicleType
        && normalize(item.plate) === normalize(plate) && dayStart(item.startDate) <= now && now < dayStart(item.endDate) + DAY
        && (state.customers || []).some(customer => customer.id === item.customerId && customer.active));
      if (pass) {
        session.monthlyPassId = pass.id;
        session.coverageStart = new Date(dayStart(pass.startDate)).toISOString();
        // End is exclusive: midnight immediately after the inclusive endDate.
        session.coverageEnd = new Date(dayStart(pass.endDate) + DAY).toISOString();
      }
      state.sessions.unshift(session);
      if (reservation) reservation.status = 'arrived';
      log(state, `${session.source === 'camera' ? 'Camera' : 'Nhập tay'}: xe ${plate} vào ${slot}${reservation ? `, tiếp nhận ${reservation.id}` : ', khách vãng lai'}.`);
      return finish(true, `Đã nhận ${typeLabel(action.vehicleType, state).toLowerCase()} ${plate} vào ${slot}. ${typeInfo(action.vehicleType, state).requiresPlate ? '' : `Mã xe: ${plate}. `}Mã vé: ${session.ticket}.`, id);
    }

    if (action.type === 'pay') {
      const session = state.sessions.find(item => item.id === action.sessionId);
      if (!session || session.status !== 'active') return fail('Không tìm thấy lượt gửi đang hoạt động.');
      if (!['online', 'cash'].includes(action.method)) return fail('Chọn phương thức thanh toán hợp lệ.');
      const amount = quote(state, session).due;
      if (amount === 0) return finish(true, 'Lượt gửi đã thanh toán đủ tại thời điểm hiện tại.', session.id);
      session.paid += amount;
      state.transactions.unshift({ id: nextId(state.transactions, 'TT', 1000), sessionId: session.id, source: 'parking', plate: session.plate, amount, method: action.method, at: state.now });
      log(state, `Đã nhận ${amount.toLocaleString('vi-VN')} đ cho ${session.plate} qua ${action.method === 'online' ? 'thanh toán online DEMO' : 'tiền mặt mô phỏng'}.`);
      return finish(true, 'Đã ghi nhận thanh toán mô phỏng. Không có giao dịch tiền thật.', session.id);
    }

    if (action.type === 'checkout') {
      const session = state.sessions.find(item => item.id === action.sessionId);
      if (!session || session.status !== 'active') return fail('Không tìm thấy lượt gửi đang hoạt động.');
      const fee = quote(state, session);
      if (fee.due > 0) return fail(`Xe còn ${fee.due.toLocaleString('vi-VN')} đ cần thanh toán trước khi ra.`);
      session.exit = state.now;
      session.closedGross = fee.gross;
      session.status = 'closed';
      log(state, `Xe ${session.plate} ra bãi; đã thu ${fee.paid.toLocaleString('vi-VN')} đ, giải phóng ${session.slot}.`);
      return finish(true, `Đã ghi nhận xe ${session.plate} ra bãi.`, session.id);
    }

    if (action.type === 'reserve') {
      if (!typeInfo(action.vehicleType, state) || typeInfo(action.vehicleType, state).active === false) return fail('Chọn loại xe đang hoạt động.');
      const plate = vehicleIdentifier(state, action.plate, action.vehicleType);
      if (!validIdentifier(plate, action.vehicleType, state)) return fail(typeInfo(action.vehicleType, state).requiresPlate
        ? 'Kiểm tra biển số và loại xe.'
        : 'Mã xe chỉ gồm chữ, số và dấu gạch ngang, tối đa 20 ký tự. Có thể để trống để cấp mã tự động.');
      const start = timestamp(action.start);
      const end = timestamp(action.end);
      const now = timestamp(state.now);
      if (![start, end].every(Number.isFinite) || start < now || end <= start) return fail('Giờ đến phải từ hiện tại; giờ kết thúc phải sau giờ đến.');
      if (start > now + 30 * DAY) return fail('Chỉ có thể đặt trước tối đa 30 ngày.');
      const holds = liveHolds(state);
      if (holds.length >= 5) return fail('Bạn đã có 5 đặt chỗ đang hoạt động. Hãy hủy đặt chỗ không còn dùng.');
      if (holds.some(item => normalize(item.plate) === normalize(plate) && overlap(item.start, item.end, action.start, action.end))) return fail('Biển số hoặc mã xe này đã có đặt chỗ trùng khung giờ.');
      const used = activeSlots(state);
      holds.filter(item => overlap(item.start, item.end, action.start, action.end)).forEach(item => used.add(slotKey(item.slot)));
      const slot = slotsFor(state, action.vehicleType).find(item => usableSlot(state, item) && !used.has(slotKey(item.code)))?.code;
      if (!slot) return fail('Chưa có vị trí phù hợp để giữ trong khung giờ này.');
      const id = nextId(state.reservations, 'DC', 1000);
      state.reservations.unshift({ id, plate, vehicleType: action.vehicleType, start: new Date(start).toISOString(), end: new Date(end).toISOString(), status: 'confirmed', slot });
      log(state, `Khách đặt trước ${id}, xe ${plate}, vị trí ${slot}.`);
      return finish(true, `Đã giữ chỗ ${id} cho ${typeLabel(action.vehicleType, state).toLowerCase()} ${plate}. ${typeInfo(action.vehicleType, state).requiresPlate ? '' : `Giữ mã xe ${plate} để tiếp nhận khi đến. `}Không thu trước; phí bắt đầu khi xe vào bãi. Giữ tối đa 15 phút sau giờ đến.`);
    }

    if (action.type === 'cancel-reservation') {
      const reservation = state.reservations.find(item => item.id === action.id);
      if (!reservation || reservation.status !== 'confirmed') return fail('Đặt chỗ này không còn ở trạng thái có thể hủy.');
      reservation.status = 'cancelled';
      log(state, `Khách hủy đặt chỗ ${reservation.id}.`);
      return finish(true, 'Đã hủy đặt chỗ và giải phóng vị trí giữ trước.');
    }

    if (action.type === 'claim') {
      const ticket = String(action.ticket || '').trim().toUpperCase();
      const session = lookupSession(state, action.plate, action.vehicleType);
      if (!session || session.ticket !== ticket) return fail('Chưa xác minh được lượt gửi. Kiểm tra biển số/mã xe, loại xe và mã vé.');
      if (!state.customerAccess.includes(session.id)) state.customerAccess.push(session.id);
      log(state, `Khách xác minh mã vé để xem và thanh toán lượt ${session.id}.`);
      return finish(true, 'Đã xác minh lượt đang gửi. Bạn có thể xem phí và thanh toán lượt này.', session.id);
    }

    if (action.type === 'support') {
      const subject = String(action.subject || '').trim();
      const message = String(action.message || '').trim();
      if (!subject || !message) return fail('Nhập chủ đề và nội dung cần hỗ trợ.');
      if (subject.length > 120 || message.length > 2000) return fail('Chủ đề tối đa 120 ký tự, nội dung tối đa 2.000 ký tự.');
      state.support.unshift({ id: nextId(state.support, 'HT', 1000), subject, message, at: state.now, status: 'open' });
      log(state, `Khách gửi yêu cầu hỗ trợ: ${subject}.`);
      return finish(true, 'Đã lưu yêu cầu trong bản demo. Chưa gửi đến nhân viên thật.');
    }

    return fail('Thao tác này chưa được hỗ trợ trong bản demo.');
  }

  const api = { seed, quote, available, apply, normalize, typeLabel, vehicleTypes, typesFor, typeInfo, lookupSession, slotsFor, freeSlots, nextSlotCode, zonesFor, slotStatus, passStatus };
  if (typeof window !== 'undefined') window.DemoEngine = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
}());
