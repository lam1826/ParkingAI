(function () {
  'use strict';

  const E = window.DemoEngine;
  const A = window.DemoAnalytics;
  const DAY = 86400000;
  const isInternal = app => ['admin', 'manager'].includes(app.ui.role);
  const isOperator = app => ['admin', 'manager', 'staff'].includes(app.ui.role);
  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const day = value => {
    const ms = new Date(value).getTime();
    return Number.isFinite(ms) ? new Date(ms + 7 * 3600000).toISOString().slice(0, 10) : '';
  };
  const dayLabel = value => String(value).split('-').reverse().join('/');
  const typeList = app => E.typesFor(app.state);
  const typeName = (app, value) => E.typeInfo(value, app.state)?.label || 'Chưa xác định';
  const methodName = value => value === 'cash' ? 'Tiền mặt' : value === 'online' ? 'Online' : 'Khác';
  const read = (data, key) => String(typeof data?.get === 'function' ? data.get(key) || '' : data?.[key] || '').trim();
  const denied = () => '<div class="empty"><p>Mục này dành cho Admin và Manager.</p></div>';

  function range(app) {
    const today = day(app.state.now);
    return app.ui.reportFilter || { start: today, end: today };
  }

  function receipts(app, filter) {
    return A.aggregate(app.state, filter).receipts || [];
  }

  function total(items) {
    return items.reduce((sum, item) => sum + number(item.amount), 0);
  }

  function link(app, tab, text, kind = 'quiet') {
    return `<button type="button" class="button ${kind}" data-action="open-tab" data-tab="${tab}">${app.esc(text)} ${app.icon('arrow')}</button>`;
  }

  function overview(app) {
    if (!isInternal(app)) return denied();
    const state = app.state;
    const today = day(state.now);
    const now = new Date(state.now).getTime();
    const summary = A.aggregate(state, { start: today, end: today });
    const active = state.sessions.filter(item => item.status === 'active' && new Date(item.entry).getTime() <= now);
    const entries = summary.totals?.arrivals || 0;
    const exits = summary.totals?.departures || 0;
    const paid = receipts(app, { start: today, end: today });
    const due = active.reduce((sum, item) => sum + E.quote(state, item).due, 0);
    const unpaid = active.filter(item => E.quote(state, item).due > 0).length;
    const bookings = (state.reservations || []).filter(item => item.status === 'confirmed' && day(item.start) === today && new Date(item.start).getTime() + 15 * 60000 >= now && new Date(item.end).getTime() > now).sort((a, b) => new Date(a.start) - new Date(b.start));
    const support = (state.support || []).filter(item => ['open', 'pending', 'reviewing'].includes(item.status)).length;
    const free = typeList(app).reduce((sum, type) => sum + E.available(state, type.id), 0);
    const capacity = summary.current?.capacity || 0;
    const cards = [[active.length, 'Xe đang gửi'], [free, 'Chỗ nhận xe ngay'], [entries, 'Lượt vào hôm nay'], [exits, 'Lượt ra hôm nay']];
    const alerts = [
      ...(free === 0 ? [`<div class="overview-alert"><div><strong>Chưa còn chỗ nhận xe ngay</strong><p>Kiểm tra vị trí đang có xe và chỗ giữ trước.</p></div>${link(app, 'lot', 'Xem bãi đỗ')}</div>`] : []),
      ...(support ? [`<div class="overview-alert"><div><strong>${support} yêu cầu hỗ trợ đang chờ</strong><p>Khách đã gửi nội dung trong bản demo.</p></div>${link(app, 'customers', 'Xem yêu cầu')}</div>`] : []),
      ...(bookings.length ? [`<div class="overview-alert"><div><strong>${bookings.length} đặt chỗ sẽ đến hôm nay</strong><p>Giữ chỗ đến 15 phút sau giờ hẹn.</p></div>${link(app, 'customers', 'Xem khách đặt trước')}</div>`] : []),
    ];
    return `<div class="page-head"><div><h1>Tổng quan bãi đỗ</h1><p>Hôm nay, ${dayLabel(today)} · cập nhật theo đồng hồ demo ${app.esc(app.time(state.now))}.</p></div>${link(app, 'operations', 'Vào vận hành', 'primary')}</div>
      <div class="overview-metrics">${cards.map(([value, label]) => `<div class="overview-metric"><span>${label}</span><strong class="tabular">${value}</strong></div>`).join('')}</div>
      <section class="surface" aria-labelledby="overview-money-title"><div class="section-head"><h2 id="overview-money-title">Thu tiền hôm nay</h2><span class="badge neutral">DEMO</span></div>
        <div class="split"><div class="fee-lines"><div class="fee-line"><span>Đã thu hôm nay</span><strong>${app.money(total(paid))}</strong></div><div class="fee-line"><span>Phiếu thu đã ghi nhận</span><strong>${paid.length}</strong></div></div><div class="fee-lines"><div class="fee-line"><span>Còn phải thu tại thời điểm này</span><strong>${app.money(due)}</strong></div><div class="fee-line"><span>Lượt đang gửi còn phí</span><strong>${unpaid}</strong></div></div></div>
        <p class="inline-note">Tiền đã thu chỉ tính phiếu thu ghi nhận hôm nay. Khoản còn phải thu là phí hiện tại của các xe đang gửi và có thể tăng theo thời gian.</p>
      </section>
      <section class="surface" aria-labelledby="overview-lot-title"><div class="section-head"><h2 id="overview-lot-title">Tình trạng toàn bãi</h2><span class="muted">${active.length}/${capacity} vị trí đang có xe</span></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Loại xe</th><th scope="col">Đang gửi</th><th scope="col">Nhận xe ngay</th><th scope="col">Giữ trước</th><th scope="col">Sức chứa</th></tr></thead><tbody>${typeList(app).map(type => {
          const occupied = active.filter(item => item.vehicleType === type.id).length;
          const available = E.available(state, type.id);
          const limit = number(state.capacity[type.id]);
          return `<tr><td><strong>${app.esc(type.label)}</strong></td><td>${occupied}</td><td><span class="badge ${available ? 'success' : 'warning'}">${available}</span></td><td>${Math.max(0, limit - occupied - available)}</td><td>${limit}</td></tr>`;
        }).join('')}</tbody></table></div>
      </section>
      ${alerts.length ? `<section class="surface" aria-labelledby="overview-alerts-title"><div class="section-head"><h2 id="overview-alerts-title">Cần theo dõi</h2></div>${alerts.join('')}</section>` : ''}
      <div class="overview-links">${link(app, 'customers', 'Khách & vé') + link(app, 'finance', 'Báo cáo & AI') + link(app, 'lot', 'Sơ đồ bãi')}${app.ui.role === 'admin' ? link(app, 'accounts', 'Quản lý tài khoản') : ''}</div>`;
  }

  function receiptsReport(app) {
    if (!isInternal(app)) return denied();
    const filter = range(app);
    const rows = receipts(app, filter);
    const sessions = new Map(app.state.sessions.map(item => [item.id, item]));
    const sums = typeList(app).map(type => ({ ...type, rows: rows.filter(item => sessions.get(item.sessionId)?.vehicleType === type.id) }));
    const monthly = rows.filter(item => item.source === 'monthly' || item.monthlyPassId);
    const unknown = rows.filter(item => !monthly.includes(item) && !typeList(app).some(type => type.id === sessions.get(item.sessionId)?.vehicleType));
    if (monthly.length) sums.push({ id: 'monthly', label: 'Vé tháng', rows: monthly });
    if (unknown.length) sums.push({ id: 'unknown', label: 'Chưa xác định', rows: unknown });
    const online = total(rows.filter(item => item.method === 'online'));
    const cash = total(rows.filter(item => item.method === 'cash'));
    const other = total(rows.filter(item => !['online', 'cash'].includes(item.method)));
    return `<section class="surface" aria-labelledby="report-total-title"><div class="section-head"><h2 id="report-total-title">Tổng tiền đã thu</h2><button type="button" class="button secondary small" data-action="report-export">Xuất CSV</button></div>
        <div class="stat-strip"><div class="stat-item"><strong>${app.money(total(rows))}</strong> tổng thu</div><div class="stat-item"><strong>${rows.length}</strong> phiếu thu</div></div>
        <div class="fee-lines"><div class="fee-line"><span>Tiền mặt</span><strong>${app.money(cash)}</strong></div><div class="fee-line"><span>Online</span><strong>${app.money(online)}</strong></div>${other ? `<div class="fee-line"><span>Khác</span><strong>${app.money(other)}</strong></div>` : ''}</div>
        <p class="inline-note">Chỉ cộng tiền đã được ghi nhận bằng phiếu thu. Phí chưa trả và đặt chỗ chưa thu tiền không được tính vào tổng này.</p>
      </section>
      <section class="surface" aria-labelledby="report-types-title"><div class="section-head"><h2 id="report-types-title">Thu theo loại xe</h2></div><div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Loại xe</th><th scope="col">Phiếu thu</th><th scope="col">Đã thu</th></tr></thead><tbody>${sums.map(type => `<tr><td>${app.esc(type.label)}</td><td>${type.rows.length}</td><td><strong>${app.money(total(type.rows))}</strong></td></tr>`).join('')}</tbody></table></div></section>
      <section class="surface" aria-labelledby="report-receipts-title"><div class="section-head"><h2 id="report-receipts-title">Chi tiết phiếu thu</h2><span class="muted">${rows.length} phiếu</span></div>${rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Mã phiếu</th><th scope="col">Ngày, giờ</th><th scope="col">Xe / mã vé</th><th scope="col">Loại xe</th><th scope="col">Hình thức</th><th scope="col">Số tiền</th></tr></thead><tbody>${rows.map(item => {
        const session = sessions.get(item.sessionId);
        return `<tr><td>${app.esc(item.id)}</td><td class="tabular">${dayLabel(day(item.at))} ${app.esc(app.time(item.at))}</td><td class="plate">${app.esc(item.plate || session?.ticket || '—')}</td><td>${item.source === 'monthly' || item.monthlyPassId ? 'Vé tháng' : app.esc(typeName(app, session?.vehicleType))}</td><td>${methodName(item.method)}</td><td><strong>${app.money(number(item.amount))}</strong></td></tr>`;
      }).join('')}</tbody></table></div>` : '<div class="empty"><p>Chưa có phiếu thu trong khoảng thời gian này.</p><p class="muted">Bạn có thể chọn 7 ngày để xem dữ liệu mẫu trước đó, hoặc thử thu tiền một lượt gửi.</p></div>'}</section>`;
  }

  function flow(app, result) {
    const { totals, daily, hourly, current, peakHours } = result;
    const maximum = Math.max(1, ...daily.map(row => row.movements));
    return `<section class="surface"><div class="section-head"><h2>Lượt xe trong kỳ</h2><span class="badge neutral">Giờ Việt Nam</span></div><div class="stat-strip"><div class="stat-item"><strong>${totals.arrivals}</strong> lượt vào</div><div class="stat-item"><strong>${totals.departures}</strong> lượt ra</div><div class="stat-item"><strong>${totals.movements}</strong> tổng vào + ra</div></div>
      ${totals.movements ? `<p class="inline-note">Cao điểm theo tổng lượt vào + ra: ${peakHours.map(row => `${row.label} (${row.movements} lượt)`).join('; ')}.</p>` : '<div class="empty"><p>Chưa có lượt vào/ra trong kỳ đã chọn.</p><p>Chọn 7 ngày để xem lịch sử mẫu hoặc ghi nhận xe ở mục Vận hành.</p></div>'}
      ${daily.length <= 14 ? `<div class="chart-bars" role="img" aria-label="Tổng lượt vào và ra theo ngày; số liệu chi tiết ở bảng bên dưới">${daily.map(row => `<div class="chart-column"><span>${row.movements}</span><div class="chart-bar ${row.movements === maximum ? 'peak' : ''}" style="height:${Math.max(2, row.movements * 120 / maximum)}px"></div><span class="chart-label">${dayLabel(row.day).slice(0, 5)}</span></div>`).join('')}</div>` : ''}
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Ngày</th><th>Lượt vào</th><th>Lượt ra</th><th>Tổng</th></tr></thead><tbody>${daily.map(row => `<tr><td>${dayLabel(row.day)}</td><td>${row.arrivals}</td><td>${row.departures}</td><td>${row.movements}</td></tr>`).join('')}</tbody></table></div>
      <details class="demo-help"><summary>Xem lưu lượng theo khung giờ</summary><div class="table-wrap"><table class="data-table"><thead><tr><th>Khung giờ</th><th>Vào</th><th>Ra</th><th>Tổng</th></tr></thead><tbody>${hourly.map(row => `<tr><td>${row.label}</td><td>${row.arrivals}</td><td>${row.departures}</td><td>${row.movements}</td></tr>`).join('')}</tbody></table></div></details></section>
      <section class="surface"><div class="section-head"><h2>Chỗ trống hiện tại</h2><span class="badge neutral">${app.esc(app.time(current.asOf))}</span></div><p class="inline-note">${app.esc(current.note)} ${current.capacity ? `${current.occupied}/${current.capacity} vị trí có xe (${current.occupancyPercent}%).` : 'Chưa cấu hình vị trí đỗ.'}</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Khu vực</th><th>Có xe</th><th>Nhận xe ngay</th><th>Giữ trước</th><th>Tạm ngừng</th><th>Tổng ô</th></tr></thead><tbody>${current.byZone.map(row => `<tr><td>${app.esc(row.name)}</td><td>${row.occupied}</td><td>${row.free}</td><td>${row.reserved}</td><td>${row.inactive}</td><td>${row.capacity}</td></tr>`).join('')}</tbody></table></div></section>`;
  }

  function aiReports(app) {
    const form = app.ui.aiReportForms?.[app.ui.role] || { kind: 'report', period: 'day', anchorDate: A.day(app.state.now), question: '' };
    const error = app.ui.aiReportErrors?.[app.ui.role];
    const history = (app.state.aiReports || []).filter(row => row.role === app.ui.role);
    const selected = history.find(row => row.id === app.ui.aiReportSelected) || history[0];
    const select = (name, options) => `<select name="${name}">${options.map(([value, text]) => `<option value="${value}" ${form[name] === value ? 'selected' : ''}>${text}</option>`).join('')}</select>`;
    return `<section class="surface"><div class="section-head"><h2>Phân tích bãi đỗ</h2><span class="badge neutral">AI mô phỏng</span></div><p class="inline-note">Dùng số liệu của bản DEMO để thử báo cáo, hỏi đáp và gợi ý nhân sự. Chưa gọi AI thật. Mỗi kết quả lưu cả dữ liệu đầu vào để đối chiếu.</p>
      <form data-action="report-ai-generate" class="form-grid"><label class="field">Nội dung${select('kind', [['report', 'Báo cáo lưu lượng'], ['question', 'Hỏi đáp dữ liệu'], ['staff', 'Gợi ý nhân sự']])}</label><label class="field">Kỳ phân tích${select('period', [['day', 'Một ngày'], ['week', '7 ngày đến ngày chọn']])}</label><label class="field">Ngày kết thúc<input type="date" name="anchorDate" value="${app.esc(form.anchorDate)}" required></label><label class="field">Câu hỏi (cho mục Hỏi đáp)<input name="question" maxlength="600" value="${app.esc(form.question)}" placeholder="Khung giờ nào đông nhất?"></label><div class="form-actions"><button type="submit" class="button primary">Tạo phân tích</button></div></form>
      ${error ? `<p class="form-error" role="alert">${app.esc(error)}</p>` : ''}</section>
      ${selected ? `<section class="surface"><div class="section-head"><h2>Kết quả đã lưu</h2><span class="muted">${app.esc(app.date(selected.at))} ${app.esc(app.time(selected.at))}</span></div><div class="chat-message assistant" style="white-space:pre-line">${app.esc(selected.output)}</div><details class="demo-help"><summary>Xem dữ liệu đầu vào đã chốt</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px">${app.esc(JSON.stringify(selected.input, null, 2))}</pre></details></section>` : '<section class="surface empty"><p>Chưa có phân tích đã lưu cho vai trò này.</p><p>Chọn kỳ ngày hoặc tuần rồi bấm Tạo phân tích.</p></section>'}
      ${history.length ? `<section class="surface"><div class="section-head"><h2>Lịch sử phân tích</h2><span class="muted">${history.length} bản · chỉ lưu trong phiên DEMO</span></div>${history.map(row => `<div class="list-row"><div><strong>${{ report: 'Báo cáo lưu lượng', question: 'Hỏi đáp dữ liệu', staff: 'Gợi ý nhân sự' }[row.input.kind]}</strong><p>${dayLabel(row.input.periodRange.start)} – ${dayLabel(row.input.periodRange.end)}${row.input.question ? ' · ' + app.esc(row.input.question) : ''}</p></div><button type="button" class="button quiet small" data-action="report-ai-open" data-id="${app.esc(row.id)}">${selected?.id === row.id ? 'Đang xem' : 'Xem lại'}</button></div>`).join('')}</section>` : ''}`;
  }

  function revenue(app) {
    if (!isOperator(app)) return denied();
    const tabs = [...(isInternal(app) ? [['money', 'Thu chi']] : []), ['flow', 'Lưu lượng'], ['ai', 'AI']];
    const tab = tabs.some(([key]) => key === app.ui.reportTab) ? app.ui.reportTab : tabs[0][0];
    const filter = range(app);
    const result = A.aggregate(app.state, filter);
    return `<div class="page-head"><div><h1>Báo cáo & AI</h1><p>Lưu lượng, chỗ trống${isInternal(app) ? ' và tiền đã thu' : ''} từ dữ liệu DEMO.</p></div></div><div class="toolbar"><div class="segments" aria-label="Loại báo cáo">${tabs.map(([key, text]) => `<button type="button" class="${key === tab ? 'active' : ''}" aria-pressed="${key === tab}" data-action="report-tab" data-tab="${key}">${text}</button>`).join('')}</div></div>
      ${tab === 'ai' ? aiReports(app) : `<section class="surface"><div class="section-head"><h2>Khoảng thời gian</h2><div class="form-actions"><button type="button" class="button quiet small" data-action="report-period" data-days="1">Hôm nay</button><button type="button" class="button quiet small" data-action="report-period" data-days="7">7 ngày</button></div></div><form data-action="report-filter" class="form-grid"><label class="field">Từ ngày<input type="date" name="start" value="${app.esc(filter.start)}" required></label><label class="field">Đến ngày<input type="date" name="end" value="${app.esc(filter.end)}" required></label><div class="form-actions"><button type="submit" class="button primary">Xem báo cáo</button></div></form></section>${!result.ok ? `<p class="form-error" role="alert">${app.esc(result.error)}</p>` : `${result.warnings.length ? `<p class="inline-note warning">${app.esc(result.warnings.join(' '))}</p>` : ''}${tab === 'money' ? receiptsReport(app) : flow(app, result)}`}`}`;
  }

  function csvCell(value) {
    let text = String(value ?? '');
    if (/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }

  function handle(app, action, data) {
    if (!action.startsWith('report-')) return false;
    if (!isOperator(app)) {
      app.notify('Báo cáo vận hành dành cho nhân viên và quản lý bãi.');
      return true;
    }
    if (action === 'report-tab') {
      const tab = read(data, 'tab');
      if (['flow', 'ai'].includes(tab) || (tab === 'money' && isInternal(app))) app.ui.reportTab = tab;
      app.render(); return true;
    }
    if (action === 'report-ai-generate') {
      const form = { kind: read(data, 'kind'), period: read(data, 'period'), anchorDate: read(data, 'anchorDate'), question: read(data, 'question') };
      app.ui.aiReportForms = { ...(app.ui.aiReportForms || {}), [app.ui.role]: form };
      const result = A.generate(app.state, { ...form, role: app.ui.role });
      app.ui.aiReportErrors = { ...(app.ui.aiReportErrors || {}), [app.ui.role]: result.ok ? '' : result.text };
      if (result.ok) {
        const history = app.state.aiReports || [];
        const id = `AI-${Math.max(0, ...history.map(row => Number(row.id.slice(3)) || 0)) + 1}`;
        app.state.aiReports = [{ id, role: app.ui.role, at: app.state.now, input: JSON.parse(JSON.stringify(result.input)), output: result.text }, ...history].slice(0, 30);
        app.ui.aiReportSelected = id;
        app.notify('Đã lưu đầu vào và kết quả AI mô phỏng trong phiên này.');
      }
      app.render(); return true;
    }
    if (action === 'report-ai-open') {
      const row = (app.state.aiReports || []).find(item => item.id === read(data, 'id') && item.role === app.ui.role);
      if (row) app.ui.aiReportSelected = row.id;
      app.render(); return true;
    }
    if (action === 'report-filter') {
      const start = read(data, 'start');
      const end = read(data, 'end');
      const result = A.aggregate(app.state, { start, end });
      if (!result.ok) {
        app.notify(result.error);
        return true;
      }
      app.ui.reportFilter = { start, end };
      app.render();
      return true;
    }
    if (action === 'report-period') {
      const days = Number(read(data, 'days'));
      if (![1, 7].includes(days)) return true;
      const end = day(app.state.now);
      const start = new Date(new Date(end + 'T00:00:00Z').getTime() - (days - 1) * DAY).toISOString().slice(0, 10);
      app.ui.reportFilter = { start, end };
      app.render();
      return true;
    }
    if (action === 'report-export') {
      if (!isInternal(app)) { app.notify('Xuất phiếu thu chỉ dành cho Manager và Admin.'); return true; }
      const filter = range(app);
      const rows = receipts(app, filter);
      const sessions = new Map(app.state.sessions.map(item => [item.id, item]));
      const dataRows = [['Mã phiếu thu DEMO', 'Ngày', 'Giờ (Việt Nam)', 'Mã lượt', 'Biển số / mã vé', 'Loại xe', 'Hình thức', 'Số tiền (VND)'], ...rows.map(item => {
        const session = sessions.get(item.sessionId);
        return [item.id, day(item.at), app.time(item.at), item.sessionId, item.plate || session?.ticket || '', item.source === 'monthly' || item.monthlyPassId ? 'Vé tháng' : typeName(app, session?.vehicleType), methodName(item.method), number(item.amount)];
      })];
      const blob = new Blob(['\ufeff' + dataRows.map(row => row.map(csvCell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `parkingai-thu-DEMO-${filter.start}-${filter.end}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      app.notify(`Đã xuất ${rows.length} phiếu thu DEMO ra CSV.`);
      return true;
    }
    return false;
  }

  window.DemoReports = { overview, revenue, handle };
})();
