/* Standalone demo screens. All changes stay in DemoEngine's in-memory state. */
(function () {
  'use strict';
  const E = window.DemoEngine;
  const manage = app => ['admin', 'manager'].includes(app.ui.role);
  const internal = app => ['admin', 'manager', 'staff'].includes(app.ui.role);
  const read = (data, key) => String(typeof data?.get === 'function' ? data.get(key) ?? '' : data?.[key] ?? '').trim();
  const rows = (app, key) => app.state[key] || [];
  const types = app => E.typesFor(app.state);
  const zones = app => E.zonesFor(app.state);
  const dayOf = value => Number.isFinite(new Date(value).getTime()) ? new Date(new Date(value).getTime() + 7 * 3600000).toISOString().slice(0, 10) : '';
  const dateLabel = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || '')) ? value.split('-').reverse().join('/') : '—';
  const stamp = (app, value) => value ? `${app.time(value)} · ${dateLabel(dayOf(value))}` : '—';
  const duration = minutes => `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`;
  const customerName = (app, id) => rows(app, 'customers').find(item => item.id === id)?.name || 'Chưa liên kết';
  const typeName = (app, id) => E.typeLabel(id, app.state);
  const stateLabel = { available: 'Còn nhận xe', occupied: 'Đang có xe', reserved: 'Đã giữ chỗ', inactive: 'Ngừng phục vụ' };
  const reservationLabel = { confirmed: 'Đã giữ chỗ', arrived: 'Đã vào bãi', cancelled: 'Đã hủy', expired: 'Hết hạn' };
  const sessionLabel = { active: 'Đang gửi', closed: 'Đã ra', cancelled: 'Đã hủy' };
  const kinds = { zone: 'khu vực', slot: 'vị trí đỗ', type: 'loại xe', customer: 'khách hàng', vehicle: 'phương tiện', pass: 'vé tháng', renewal: 'kỳ vé tháng' };
  const fieldLists = {
    zone: ['id', 'name', 'vehicleType', 'capacity', 'active'],
    slot: ['originalCode', 'code', 'zoneId', 'active'],
    type: ['id', 'label', 'prefix', 'rate', 'requiresPlate', 'active'],
    customer: ['id', 'name', 'phone', 'email', 'active'],
    vehicle: ['id', 'customerId', 'plate', 'vehicleType', 'active'],
    pass: ['id', 'customerId', 'plate', 'vehicleType', 'startDate', 'endDate', 'price', 'active'],
    renewal: ['id', 'startDate', 'endDate', 'price'],
  };

  function button(app, action, label, data = {}, style = 'quiet small') {
    return `<button type="button" class="button ${style}" data-action="core-${action}" ${Object.entries(data).map(([key, value]) => `data-${key}="${app.esc(value)}"`).join(' ')}>${label}</button>`;
  }
  function heading(app, title, description, kind) {
    return `<div class="page-head"><div><h1>${title}</h1><p>${description}</p></div>${kind && manage(app) ? button(app, 'open', `${app.icon('plus')} Thêm ${kinds[kind]}`, { kind }, 'primary') : ''}</div>`;
  }
  function notice(app) {
    return manage(app) ? '' : '<p class="inline-note">Nhân viên được tra cứu. Manager và Admin phụ trách thay đổi danh mục và cấp vé tháng.</p>';
  }
  function badge(app, active) {
    return `<span class="badge ${active !== false ? 'success' : 'neutral'}">${active !== false ? 'Đang hoạt động' : 'Ngừng hoạt động'}</span>`;
  }
  function tabs(app, page, selected, items) {
    return `<div class="core-subtabs segments" role="group" aria-label="Nội dung ${page === 'lot' ? 'bãi đỗ' : 'khách và vé'}">${items.map(([value, label]) => `<button type="button" class="${selected === value ? 'active' : ''}" aria-pressed="${selected === value}" data-action="core-tab" data-page="${page}" data-value="${value}">${label}</button>`).join('')}</div>`;
  }
  function table(columns, body, empty = 'Chưa có dữ liệu.') {
    return body.length ? `<div class="table-wrap"><table class="data-table core-table"><thead><tr>${columns.map(name => `<th scope="col">${name}</th>`).join('')}</tr></thead><tbody>${body.join('')}</tbody></table></div>` : `<div class="empty">${empty}</div>`;
  }
  function actions(app, kind, id, allowDelete = false) {
    if (!manage(app)) return '';
    return `<div class="core-row-actions">${button(app, 'open', 'Sửa', { kind, id })}${allowDelete ? button(app, 'delete', 'Xóa', { kind, id }, 'quiet small danger') : ''}</div>`;
  }
  function input(app, name, label, value, extra = '') {
    return `<label class="field">${label}<input name="${name}" value="${app.esc(value ?? '')}" ${extra}></label>`;
  }
  function select(app, name, label, value, options, required = true) {
    return `<label class="field">${label}<select name="${name}"${required ? ' required' : ''}>${options.map(([key, text]) => `<option value="${app.esc(key)}"${String(value ?? '') === String(key) ? ' selected' : ''}>${app.esc(text)}</option>`).join('')}</select></label>`;
  }
  function checked(name, label, value) {
    return `<label class="checkbox-field"><input type="checkbox" name="${name}" value="true"${value !== false ? ' checked' : ''}><span>${label}</span></label>`;
  }
  function typeOptions(app, value) {
    return [['', 'Chọn loại xe'], ...types(app).filter(type => type.active !== false || type.id === value).map(type => [type.id, type.label + (type.active === false ? ' · Ngừng dùng' : '')])];
  }
  function customerOptions(app, value) {
    return [['', 'Chọn khách hàng'], ...rows(app, 'customers').filter(row => row.active !== false || row.id === value).map(row => [row.id, `${row.name} · ${row.phone}`])];
  }
  function recordFor(app, kind, id) {
    if (kind === 'slot') return rows(app, 'slots').find(row => row.code === id);
    if (kind === 'zone') return zones(app).find(row => row.id === id);
    if (kind === 'type') return types(app).find(row => row.id === id);
    return rows(app, { customer: 'customers', vehicle: 'vehicles', pass: 'monthlyPasses', renewal: 'monthlyPasses' }[kind]).find(row => row.id === id);
  }
  function addDays(day, count) {
    return new Date(new Date(`${day}T00:00:00+07:00`).getTime() + count * 86400000 + 7 * 3600000).toISOString().slice(0, 10);
  }
  function initialDraft(app, kind, id) {
    const current = recordFor(app, kind, id);
    if (current) {
      if (kind === 'type') return { ...current, rate: app.state.rates[current.id], active: current.active !== false };
      if (kind === 'slot') return { ...current, originalCode: current.code, active: current.active !== false };
      if (kind === 'renewal') {
        const start = addDays(current.endDate, 1);
        return { id: current.id, startDate: start, endDate: addDays(start, 29), price: current.price };
      }
      return { ...current, active: current.active !== false };
    }
    const today = dayOf(app.state.now);
    return { id: '', originalCode: '', active: true, requiresPlate: true, rate: '5000', capacity: '',
      startDate: today, endDate: addDays(today, 29), price: '', customerId: '', vehicleType: '', zoneId: '' };
  }

  function form(app, allowed) {
    const kind = app.ui.coreForm;
    if (!manage(app) || !allowed.includes(kind)) return '';
    const draft = app.ui.coreDraft || {};
    let fields = '', note = '';
    if (kind === 'zone') {
      fields = input(app, 'name', 'Tên khu vực', draft.name, 'required maxlength="60"')
        + select(app, 'vehicleType', 'Loại xe phục vụ', draft.vehicleType, typeOptions(app, draft.vehicleType))
        + input(app, 'capacity', 'Sức chứa tối đa', draft.capacity, 'type="number" min="0" max="1000" step="1" required')
        + checked('active', 'Khu vực hoạt động', draft.active);
      note = 'Sức chứa là giới hạn của khu. Thêm vị trí cụ thể trong mục Vị trí đỗ; tạo khu không tự tạo chỗ.';
    } else if (kind === 'slot') {
      fields = input(app, 'code', 'Mã vị trí', draft.code, 'required maxlength="20" placeholder="Ví dụ: A-25"')
        + select(app, 'zoneId', 'Khu vực · loại xe', draft.zoneId, [['', 'Chọn khu vực'], ...zones(app).filter(zone => zone.active !== false || zone.id === draft.zoneId).map(zone => [zone.id, `${zone.name} · ${typeName(app, zone.vehicleType)}`])])
        + checked('active', 'Vị trí hoạt động', draft.active)
        + `<input type="hidden" name="originalCode" value="${app.esc(draft.originalCode || '')}">`;
      note = 'Loại xe của vị trí theo khu đã chọn. Ô có xe, giữ chỗ hoặc lịch sử sử dụng được bảo vệ khỏi thay đổi không phù hợp.';
    } else if (kind === 'type') {
      fields = input(app, 'label', 'Tên loại xe', draft.label, 'required maxlength="40"')
        + input(app, 'prefix', 'Mã gợi ý cho vị trí', draft.prefix, 'required maxlength="6" placeholder="Ví dụ: E"')
        + input(app, 'rate', 'Đơn giá · đồng/giờ', draft.rate, 'type="number" min="0" max="1000000000" step="1" required')
        + checked('requiresPlate', 'Phương tiện có biển số', draft.requiresPlate)
        + checked('active', 'Đang nhận loại xe này', draft.active);
      note = 'Tính tròn mỗi giờ bắt đầu, tối thiểu một giờ ngoài thời gian được vé tháng bao phủ. Đổi giá áp dụng cho lượt vào mới; lượt đã vào giữ đơn giá lúc nhận xe.';
    } else if (kind === 'customer') {
      fields = input(app, 'name', 'Họ và tên', draft.name, 'required maxlength="80" autocomplete="name"')
        + input(app, 'phone', 'Số điện thoại', draft.phone, 'required maxlength="20" type="tel" autocomplete="tel"')
        + input(app, 'email', 'Email (không bắt buộc)', draft.email, 'type="email" maxlength="120" autocomplete="email"')
        + checked('active', 'Hồ sơ hoạt động', draft.active);
    } else if (kind === 'vehicle') {
      fields = select(app, 'customerId', 'Khách hàng', draft.customerId, customerOptions(app, draft.customerId))
        + input(app, 'plate', 'Biển số / mã xe', draft.plate, 'required maxlength="20" placeholder="59A-123.45 hoặc XD-001"')
        + select(app, 'vehicleType', 'Loại xe', draft.vehicleType, typeOptions(app, draft.vehicleType))
        + checked('active', 'Phương tiện hoạt động', draft.active);
      note = 'Dùng mã xe riêng cho phương tiện không có biển số. Hồ sơ liên kết này phục vụ tra cứu và cấp vé tháng.';
    } else if (kind === 'pass' || kind === 'renewal') {
      if (kind === 'pass') fields = select(app, 'customerId', 'Khách hàng', draft.customerId, customerOptions(app, draft.customerId))
        + input(app, 'plate', 'Biển số / mã xe đã liên kết', draft.plate, 'required maxlength="20"')
        + select(app, 'vehicleType', 'Loại xe', draft.vehicleType, typeOptions(app, draft.vehicleType));
      else {
        const previous = recordFor(app, 'pass', draft.id);
        fields = `<p class="inline-note core-wide">Gia hạn ${app.esc(previous?.plate || '')} · ${app.esc(customerName(app, previous?.customerId))}. Kỳ cũ ${dateLabel(previous?.startDate)} — ${dateLabel(previous?.endDate)} được giữ trong lịch sử.</p>`;
      }
      fields += input(app, 'startDate', 'Ngày bắt đầu', draft.startDate, 'type="date" min="2020-01-01" max="2099-12-31" required')
        + input(app, 'endDate', 'Ngày kết thúc (bao gồm cả ngày)', draft.endDate, 'type="date" min="2020-01-01" max="2099-12-31" required')
        + input(app, 'price', 'Giá kỳ vé · đồng', draft.price, 'type="number" min="0" max="1000000000" step="1" required')
        + (kind === 'pass' ? checked('active', 'Kỳ vé hoạt động', draft.active) : '');
      note = 'Cấp/gia hạn ghi phiếu thu mô phỏng theo giá kỳ vé. Xe phải có hồ sơ liên kết đúng khách. Quyền lợi vé tháng được chốt khi nhận xe; sửa vé không viết lại phí của lượt cũ.';
    }
    return `<section class="surface core-editor" aria-labelledby="core-form-title"><div class="section-head"><h2 id="core-form-title">${kind === 'renewal' ? 'Gia hạn vé tháng' : `${draft.id || draft.originalCode ? 'Sửa' : 'Thêm'} ${kinds[kind]}`}</h2></div>
      <form data-action="core-save" class="form-grid"><input type="hidden" name="kind" value="${kind}"><input type="hidden" name="id" value="${app.esc(draft.id || '')}">${fields}
      ${note ? `<p class="inline-note core-wide">${note}</p>` : ''}
      ${app.ui.coreError ? `<p class="form-error core-wide" role="alert">${app.esc(app.ui.coreError)}</p>` : ''}
      <div class="form-actions core-wide"><button type="submit" class="button primary">${kind === 'renewal' ? 'Lưu kỳ gia hạn' : 'Lưu thay đổi'}</button>${button(app, 'close', 'Hủy', {}, 'secondary')}</div></form></section>`;
  }

  function lot(app) {
    if (!internal(app)) return '<div class="empty">Mục này dành cho bộ phận vận hành.</div>';
    const view = app.ui.coreLotTab === 'zones' ? 'zones' : 'slots';
    const filter = app.ui.coreLotFilter || { zone: '', status: '' };
    const allSlots = rows(app, 'slots');
    const filtered = allSlots.filter(slot => (!filter.zone || slot.zoneId === filter.zone) && (!filter.status || E.slotStatus(app.state, slot) === filter.status));
    const totals = allSlots.reduce((sum, slot) => { sum[E.slotStatus(app.state, slot)] += 1; return sum; }, { available: 0, occupied: 0, reserved: 0, inactive: 0 });
    let content;
    if (view === 'zones') {
      content = `<section class="surface"><div class="section-head"><h2>Các khu vực</h2></div>${table(['Khu vực', 'Loại xe', 'Vị trí / sức chứa', 'Còn nhận xe', 'Trạng thái', 'Thao tác'], zones(app).map(zone => {
        const slots = allSlots.filter(slot => slot.zoneId === zone.id);
        return `<tr><td><strong>${app.esc(zone.name)}</strong></td><td>${app.esc(typeName(app, zone.vehicleType))}</td><td>${slots.length} / ${zone.capacity}</td><td>${slots.filter(slot => E.slotStatus(app.state, slot) === 'available').length}</td><td>${badge(app, zone.active)}</td><td>${actions(app, 'zone', zone.id, true)}</td></tr>`;
      }), 'Chưa có khu vực. Thêm khu trước, sau đó thêm vị trí đỗ.')}</section>`;
    } else {
      content = `<section class="surface"><form class="core-filter form-grid" data-action="core-filter-lot">${select(app, 'zone', 'Khu vực', filter.zone, [['', 'Tất cả khu vực'], ...zones(app).map(zone => [zone.id, zone.name])], false)}${select(app, 'status', 'Tình trạng vị trí', filter.status, [['', 'Tất cả trạng thái'], ...Object.entries(stateLabel)], false)}<div class="form-actions core-wide"><button type="submit" class="button secondary">Lọc vị trí</button>${button(app, 'reset-lot', 'Xóa bộ lọc')}</div></form></section>
        ${zones(app).filter(zone => !filter.zone || zone.id === filter.zone).map(zone => {
          const slots = filtered.filter(slot => slot.zoneId === zone.id);
          if (!slots.length) return '';
          return `<section class="surface core-zone"><div class="section-head"><div><h2>${app.esc(zone.name)}</h2><p>${app.esc(typeName(app, zone.vehicleType))} · ${slots.length} vị trí trong bộ lọc</p></div></div><div class="availability-grid core-slot-grid">${slots.map(slot => {
            const status = E.slotStatus(app.state, slot);
            return `<div class="slot ${status === 'reserved' ? 'held' : status}"><strong>${app.esc(slot.code)}</strong><span>${stateLabel[status]}</span>${manage(app) ? button(app, 'open', 'Sửa', { kind: 'slot', id: slot.code }) : ''}</div>`;
          }).join('')}</div></section>`;
        }).join('') || '<section class="surface"><div class="empty">Không có vị trí phù hợp. Đổi bộ lọc hoặc thêm vị trí mới.</div></section>'}
        <details class="surface core-details"><summary>Danh sách vị trí & thao tác</summary>${table(['Vị trí', 'Khu vực', 'Loại xe', 'Trạng thái', 'Thao tác'], filtered.map(slot => `<tr><td>${app.esc(slot.code)}</td><td>${app.esc(zones(app).find(zone => zone.id === slot.zoneId)?.name || '—')}</td><td>${app.esc(typeName(app, slot.vehicleType))}</td><td>${stateLabel[E.slotStatus(app.state, slot)]}</td><td>${actions(app, 'slot', slot.code, true)}</td></tr>`), 'Không có vị trí phù hợp.')}</details>`;
    }
    return `${heading(app, 'Bãi đỗ', 'Quản lý khu vực, chỗ đỗ và khả năng nhận xe tại một bãi.', view === 'zones' ? 'zone' : 'slot')}${tabs(app, 'lot', view, [['slots', 'Vị trí đỗ'], ['zones', 'Khu vực']])}${notice(app)}
      <div class="stat-strip"><span class="stat-item"><strong>${totals.available}</strong>còn nhận xe</span><span class="stat-item"><strong>${totals.occupied}</strong>đang có xe</span><span class="stat-item"><strong>${totals.reserved}</strong>giữ chỗ</span><span class="stat-item"><strong>${totals.inactive}</strong>ngừng phục vụ</span></div>
      ${form(app, view === 'zones' ? ['zone'] : ['slot'])}${content}`;
  }

  function catalog(app) {
    if (!internal(app)) return '<div class="empty">Mục này dành cho bộ phận vận hành.</div>';
    return `${heading(app, 'Loại xe & bảng giá', 'Danh mục phương tiện và đơn giá theo giờ. Manager và Admin đều có thể quản lý.', 'type')}${notice(app)}${form(app, ['type'])}
      <section class="surface">${table(['Loại xe', 'Nhận dạng', 'Giá / giờ', 'Trạng thái', 'Thao tác'], types(app).map(type => `<tr><td><strong>${app.esc(type.label)}</strong><div class="muted">Mã vị trí ${app.esc(type.prefix)}</div></td><td>${type.requiresPlate ? 'Biển số' : 'Mã xe / mã vé'}</td><td>${app.money(app.state.rates[type.id])}</td><td>${badge(app, type.active)}</td><td>${actions(app, 'type', type.id, true)}</td></tr>`), 'Chưa có loại xe.')}
      <p class="inline-note">Lượt đang gửi giữ đơn giá đã nhận lúc vào. Loại xe mới bắt đầu với 0 chỗ: thêm khu và vị trí trong mục Bãi đỗ. Loại đang được tham chiếu không được xóa.</p></section>`;
  }

  function reception(app) {
    return `<section class="surface"><div class="section-head"><h2>Đặt chỗ của khách</h2><span class="muted">${rows(app, 'reservations').length} yêu cầu</span></div>${table(['Biển số / mã xe', 'Vị trí', 'Khung giờ', 'Trạng thái'], rows(app, 'reservations').map(item => `<tr><td>${app.esc(item.plate)}<div class="muted">${app.esc(typeName(app, item.vehicleType))}</div></td><td>${app.esc(item.slot)}</td><td>${stamp(app, item.start)}<br>${stamp(app, item.end)}</td><td><span class="badge ${item.status === 'confirmed' ? 'success' : 'neutral'}">${reservationLabel[item.status] || app.esc(item.status)}</span></td></tr>`), 'Chưa có đặt chỗ. Khách có thể đặt ở giao diện Customer.')}
      <p class="inline-note">Khi xe đến, vào mục Vận hành để nhận xe theo biển số. Khách tự tạo hoặc hủy đặt chỗ trong giao diện của mình.</p></section>
      <section class="surface"><div class="section-head"><h2>Yêu cầu hỗ trợ</h2></div>${table(['Thời gian', 'Chủ đề', 'Nội dung', 'Trạng thái'], rows(app, 'support').map(item => `<tr><td>${stamp(app, item.at)}</td><td>${app.esc(item.subject)}</td><td class="core-long-text">${app.esc(item.message)}</td><td>${item.status === 'open' ? 'Đang tiếp nhận' : app.esc(item.status)}</td></tr>`), 'Chưa có yêu cầu hỗ trợ trong phiên demo.')}</section>`;
  }

  function customers(app) {
    if (!internal(app)) return '<div class="empty">Mục này dành cho bộ phận vận hành.</div>';
    const choices = [['customers', 'Khách hàng'], ['vehicles', 'Phương tiện'], ['passes', 'Vé tháng'], ['reception', 'Tiếp nhận']];
    const view = choices.some(([key]) => key === app.ui.coreCustomerTab) ? app.ui.coreCustomerTab : 'customers';
    const kind = { customers: 'customer', vehicles: 'vehicle', passes: 'pass' }[view];
    let content;
    if (view === 'reception') content = reception(app);
    else if (view === 'customers') content = `<section class="surface">${table(['Khách hàng', 'Liên hệ', 'Xe liên kết', 'Trạng thái', 'Thao tác'], rows(app, 'customers').map(item => `<tr><td><strong>${app.esc(item.name)}</strong><div class="muted">${app.esc(item.id)}</div></td><td>${app.esc(item.phone)}<div class="muted">${app.esc(item.email || '—')}</div></td><td>${rows(app, 'vehicles').filter(vehicle => vehicle.customerId === item.id).length}</td><td>${badge(app, item.active)}</td><td>${actions(app, 'customer', item.id)}</td></tr>`), 'Chưa có khách hàng. Thêm hồ sơ để liên kết phương tiện và cấp vé tháng.')}</section>`;
    else if (view === 'vehicles') content = `<section class="surface">${table(['Biển số / mã xe', 'Loại xe', 'Khách hàng', 'Trạng thái', 'Thao tác'], rows(app, 'vehicles').map(item => `<tr><td><strong>${app.esc(item.plate)}</strong></td><td>${app.esc(typeName(app, item.vehicleType))}</td><td>${app.esc(customerName(app, item.customerId))}</td><td>${badge(app, item.active)}</td><td>${actions(app, 'vehicle', item.id)}</td></tr>`), 'Chưa có phương tiện liên kết. Thêm hồ sơ khách trước.')}</section>`;
    else content = `<section class="surface">${table(['Vé / xe', 'Khách hàng', 'Thời hạn', 'Giá kỳ vé', 'Trạng thái', 'Thao tác'], rows(app, 'monthlyPasses').map(item => {
      const status = E.passStatus(app.state, item);
      return `<tr><td><strong>${app.esc(item.plate)}</strong><div class="muted">${app.esc(item.id)} · ${app.esc(typeName(app, item.vehicleType))}</div></td><td>${app.esc(customerName(app, item.customerId))}</td><td>${dateLabel(item.startDate)}<br>đến hết ${dateLabel(item.endDate)}</td><td>${app.money(item.price)}</td><td><span class="badge ${status.key === 'active' ? 'success' : status.key === 'upcoming' ? 'warning' : 'neutral'}">${app.esc(status.label)}</span></td><td><div class="core-row-actions">${actions(app, 'pass', item.id)}${manage(app) ? button(app, 'open', 'Gia hạn', { kind: 'renewal', id: item.id }) : ''}</div></td></tr>`;
    }), 'Chưa có vé tháng. Thêm khách hàng và phương tiện trước khi cấp vé.')}
      <p class="inline-note">Vé có hiệu lực đến hết ngày kết thúc theo giờ Việt Nam. Ngừng vé bằng thao tác Sửa; các kỳ đã sử dụng và chứng từ vẫn được giữ.</p></section>`;
    return `${heading(app, 'Khách & vé', 'Hồ sơ khách, phương tiện liên kết và các kỳ vé tháng.', kind)}${tabs(app, 'customers', view, choices)}${notice(app)}${form(app, view === 'passes' ? ['pass', 'renewal'] : kind ? [kind] : [])}${content}`;
  }

  function history(app) {
    if (!internal(app)) return '<div class="empty">Mục này dành cho bộ phận vận hành.</div>';
    const filter = app.ui.coreHistoryFilter || {};
    const found = rows(app, 'sessions').filter(session => (!filter.query || E.normalize(session.plate).includes(E.normalize(filter.query)) || E.normalize(session.ticket).includes(E.normalize(filter.query)) || E.normalize(session.id).includes(E.normalize(filter.query)))
      && (!filter.vehicleType || session.vehicleType === filter.vehicleType) && (!filter.status || session.status === filter.status)
      && (!filter.from || dayOf(session.entry) >= filter.from) && (!filter.to || dayOf(session.entry) <= filter.to))
      .slice().sort((left, right) => new Date(right.entry) - new Date(left.entry));
    return `${heading(app, 'Tra cứu lượt gửi', 'Tìm toàn bộ lượt đang gửi và đã kết thúc theo biển số, mã vé hoặc ngày vào.')}
      <section class="surface"><form data-action="core-filter-history" class="form-grid core-history-filter">
      ${input(app, 'query', 'Biển số / mã xe / mã vé', filter.query, 'maxlength="40" placeholder="59A-123.45 hoặc VE-2048"')}
      ${select(app, 'vehicleType', 'Loại xe', filter.vehicleType, [['', 'Tất cả loại xe'], ...types(app).map(type => [type.id, type.label])], false)}
      ${input(app, 'from', 'Ngày vào từ', filter.from, 'type="date"')}${input(app, 'to', 'Ngày vào đến (bao gồm cả ngày)', filter.to, 'type="date"')}
      ${select(app, 'status', 'Trạng thái lượt gửi', filter.status, [['', 'Tất cả'], ...Object.entries(sessionLabel)], false)}
      <div class="form-actions"><button type="submit" class="button primary">${app.icon('search')} Tra cứu</button>${button(app, 'reset-history', 'Xóa bộ lọc')}</div>
      ${app.ui.coreHistoryError ? `<p class="form-error core-wide" role="alert">${app.esc(app.ui.coreHistoryError)}</p>` : ''}</form></section>
      <section class="surface"><div class="section-head"><h2>Kết quả tra cứu</h2><span class="muted">${found.length} lượt</span></div>
      ${table(['Xe / mã vé', 'Vị trí', 'Giờ vào', 'Giờ ra', 'Thời gian', 'Phí / đã trả', 'Trạng thái', 'Chi tiết'], found.map(session => {
        const quote = E.quote(app.state, session);
        return `<tr><td><strong>${app.esc(session.plate)}</strong><div class="muted">${app.esc(session.ticket)}</div></td><td>${app.esc(session.slot)}</td><td>${stamp(app, session.entry)}</td><td>${stamp(app, session.exit)}</td><td>${duration(quote.minutes)}</td><td>${app.money(quote.gross)}<div class="muted">Đã trả ${app.money(quote.paid)}</div></td><td><span class="badge ${session.status === 'active' ? 'warning' : 'neutral'}">${sessionLabel[session.status] || app.esc(session.status)}</span></td><td>${button(app, 'detail', 'Xem', { id: session.id })}</td></tr>`;
      }), 'Không có lượt gửi phù hợp. Thử đổi biển số, thời gian hoặc trạng thái.')}</section>`;
  }

  function detail(app, id) {
    const session = rows(app, 'sessions').find(item => item.id === id);
    if (!session) return app.notify('Không tìm thấy lượt gửi này.');
    const quote = E.quote(app.state, session);
    const payments = rows(app, 'transactions').filter(payment => payment.sessionId === session.id);
    const facts = [['Mã vé', session.ticket], ['Loại xe', typeName(app, session.vehicleType)], ['Vị trí', session.slot],
      ['Giờ vào', stamp(app, session.entry)], ['Giờ ra', stamp(app, session.exit)], ['Thời gian gửi', duration(quote.minutes)],
      ['Đơn giá lúc vào', `${app.money(quote.rate ?? session.rateSnapshot)} / giờ`], ['Tổng phí lượt', app.money(quote.gross)], ['Đã thanh toán', app.money(quote.paid)], ['Còn thanh toán', app.money(quote.due)]];
    let content = `<span class="badge ${session.status === 'active' ? 'warning' : 'neutral'}">${sessionLabel[session.status] || app.esc(session.status)}</span><dl class="definition-list core-facts">${facts.map(([label, value]) => `<div><dt>${label}</dt><dd>${app.esc(value)}</dd></div>`).join('')}</dl>`;
    if (quote.monthlyPassId) content += `<p class="inline-note">Áp dụng vé tháng ${app.esc(quote.monthlyPassId)} từ ${stamp(app, quote.coverageStart)} đến ${stamp(app, quote.coverageEnd)}. Được bao phủ ${duration(quote.coveredMinutes || 0)}; thời gian tính phí ${duration(quote.billableMinutes || 0)}.</p>`;
    content += `<h3>Thanh toán của lượt</h3>${payments.length ? payments.map(payment => `<div class="history-row"><div>${app.esc(payment.id)}<small>${stamp(app, payment.at)} · ${payment.method === 'cash' ? 'Tiền mặt' : 'Online'} mô phỏng</small></div><strong>${app.money(payment.amount)}</strong></div>`).join('') : '<p class="muted core-empty-note">Chưa có phiếu thu cho lượt này.</p>'}<div class="form-actions">${button(app, 'close-detail', 'Đóng', {}, 'secondary')}</div>`;
    app.showModal(`Lượt gửi ${app.esc(session.plate)}`, content);
  }

  function handle(app, action, data) {
    if (!internal(app)) { app.notify('Mục này dành cho bộ phận vận hành.'); return false; }
    if (action === 'core-tab') {
      const page = read(data, 'page'), value = read(data, 'value');
      if (page === 'lot' && ['slots', 'zones'].includes(value)) app.ui.coreLotTab = value;
      else if (page === 'customers' && ['customers', 'vehicles', 'passes', 'reception'].includes(value)) app.ui.coreCustomerTab = value;
      app.render(); return true;
    }
    if (action === 'core-close-detail') { app.closeModal(); return true; }
    if (action === 'core-detail') { detail(app, read(data, 'id')); return true; }
    if (action === 'core-reset-history') { app.ui.coreHistoryFilter = {}; app.ui.coreHistoryError = ''; app.render(); return true; }
    if (action === 'core-reset-lot') { app.ui.coreLotFilter = {}; app.render(); return true; }
    if (action === 'core-filter-lot') { app.ui.coreLotFilter = { zone: read(data, 'zone'), status: read(data, 'status') }; app.render(); return true; }
    if (action === 'core-filter-history') {
      const filter = Object.fromEntries(['query', 'vehicleType', 'from', 'to', 'status'].map(key => [key, read(data, key)]));
      app.ui.coreHistoryFilter = filter;
      app.ui.coreHistoryError = filter.from && filter.to && filter.from > filter.to ? 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.' : '';
      app.render(); return !app.ui.coreHistoryError;
    }
    if (!manage(app)) { app.notify('Manager hoặc Admin mới được thay đổi dữ liệu này.'); return false; }
    if (action === 'core-close') { app.ui.coreForm = ''; app.ui.coreError = ''; app.render(); return true; }
    if (action === 'core-open') {
      const kind = read(data, 'kind'), id = read(data, 'id');
      if (!Object.hasOwn(fieldLists, kind)) return false;
      app.ui.coreForm = kind; app.ui.coreDraft = initialDraft(app, kind, id); app.ui.coreError = '';
      app.render();
      document.querySelector('.core-editor input:not([type=hidden]),.core-editor select')?.focus();
      return true;
    }
    if (action === 'core-save') {
      const kind = read(data, 'kind');
      if (!Object.hasOwn(fieldLists, kind) || app.ui.coreForm !== kind) return false;
      const draft = Object.fromEntries(fieldLists[kind].map(key => [key, read(data, key)]));
      for (const key of ['active', 'requiresPlate']) if (fieldLists[kind].includes(key)) draft[key] = draft[key] === 'true';
      app.ui.coreDraft = draft;
      const payload = { ...draft };
      for (const key of ['capacity', 'rate', 'price']) if (Object.hasOwn(payload, key)) payload[key] = Number(payload[key]);
      if (kind === 'slot') payload.vehicleType = zones(app).find(zone => zone.id === payload.zoneId)?.vehicleType || '';
      const operation = { zone: 'save-zone', slot: 'save-slot', type: 'save-vehicle-type', customer: 'save-customer', vehicle: 'save-vehicle', pass: 'save-pass', renewal: 'renew-pass' }[kind];
      const result = E.apply(app.state, { type: operation, ...payload, role: app.ui.role });
      if (result.ok) { app.state = result.state; app.ui.coreForm = ''; app.ui.coreDraft = null; app.ui.coreError = ''; }
      else app.ui.coreError = result.message;
      app.render(); app.notify(result.message); return result.ok;
    }
    if (action === 'core-delete') {
      const kind = read(data, 'kind'), id = read(data, 'id');
      if (!['zone', 'slot', 'type'].includes(kind)) return false;
      const item = recordFor(app, kind, id);
      if (!item) return false;
      const label = item.name || item.label || item.code;
      app.showModal(`Xóa ${kinds[kind]}`, `<p>Bạn muốn xóa <strong>${app.esc(label)}</strong>?</p><p class="inline-note">Chỉ xóa khi không còn dữ liệu tham chiếu. Nếu đã dùng, hãy chuyển sang ngừng hoạt động để giữ lịch sử.</p><div class="form-actions">${button(app, 'confirm-delete', 'Xóa', { kind, id }, 'danger')}${button(app, 'close-detail', 'Giữ lại', {}, 'secondary')}</div>`);
      return true;
    }
    if (action === 'core-confirm-delete') {
      const kind = read(data, 'kind'), id = read(data, 'id');
      if (!['zone', 'slot', 'type'].includes(kind)) return false;
      const result = E.apply(app.state, { type: { zone: 'delete-zone', slot: 'delete-slot', type: 'delete-vehicle-type' }[kind], id, code: id, role: app.ui.role });
      if (result.ok) app.state = result.state;
      app.closeModal(); app.render(); app.notify(result.message); return result.ok;
    }
    return false;
  }

  window.DemoCore = { lot, catalog, customers, history, handle };
}());
