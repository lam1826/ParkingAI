(function () {
  'use strict';

  const roles = { admin: 'Admin', manager: 'Manager', customer: 'Customer', staff: 'Nhân viên' };
  const roleNotes = {
    admin: 'Toàn bộ chức năng Manager, thêm tài khoản, phân quyền và cấu hình hệ thống',
    manager: 'Vận hành bãi, thu tiền, khách hàng và báo cáo',
    customer: 'Đặt trước, xem phí và thanh toán lượt gửi của mình',
    staff: 'Nhân viên được Manager phân công vận hành',
  };

  function read(data, key) {
    return String(data && typeof data.get === 'function' ? data.get(key) || '' : data?.[key] || '').trim();
  }

  function record(app, text) {
    if (!Array.isArray(app.state.audit)) app.state.audit = [];
    app.state.audit.unshift({ at: app.state.now, text });
  }

  function finish(app, message) {
    app.render();
    app.notify(message);
    return true;
  }

  function accountForm(app) {
    if (!app.ui.adminFormOpen) return '';
    const user = app.users.find(item => String(item.id) === String(app.ui.adminEditingId));
    return `<section class="surface" aria-labelledby="account-form-title">
      <div class="section-head"><h2 id="account-form-title">${user ? 'Sửa tài khoản mẫu' : 'Thêm tài khoản mẫu'}</h2></div>
      <form data-action="admin-save-user" class="form-grid">
        <input type="hidden" name="id" value="${app.esc(user?.id || '')}">
        <label class="field">Họ và tên<input name="name" value="${app.esc(user?.name || '')}" maxlength="80" autocomplete="off" required placeholder="Nguyễn Minh Anh"></label>
        <label class="field">Tên đăng nhập<input name="username" value="${app.esc(user?.username || '')}" minlength="3" maxlength="32" pattern="[a-zA-Z0-9_.-]{3,32}" title="3–32 ký tự: chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang" autocomplete="off" required placeholder="minhanh"></label>
        <label class="field">Vai trò<select name="role">${Object.entries(roles).map(([key, label]) => `<option value="${key}"${(user?.role || 'manager') === key ? ' selected' : ''}>${label}</option>`).join('')}</select></label>
        <p class="inline-note">Tài khoản chỉ nằm trong demo. Mật khẩu mô phỏng: demo123.</p>
        <div class="form-actions"><button class="button primary" type="submit">${user ? 'Lưu thay đổi' : 'Thêm tài khoản'}</button><button class="button secondary" type="button" data-action="admin-close-form">Hủy</button></div>
      </form>
    </section>`;
  }

  function accounts(app) {
    return `<div class="page-head"><div><h1>Tài khoản & phân quyền</h1><p>Admin có toàn bộ quyền Manager và quyền quản trị hệ thống. Customer tự phục vụ.</p></div><button class="button primary" data-action="admin-open-form">${app.icon('plus')} Thêm tài khoản</button></div>
      ${accountForm(app)}
      <section class="surface" aria-labelledby="accounts-title">
        <div class="section-head"><h2 id="accounts-title">Danh sách tài khoản</h2><span class="muted">${app.users.length} tài khoản mẫu</span></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Tài khoản</th><th scope="col">Vai trò</th><th scope="col">Trạng thái</th><th scope="col"><span class="muted">Thao tác</span></th></tr></thead><tbody>
          ${app.users.map(user => `<tr><td><button class="button quiet" data-action="admin-edit" data-id="${app.esc(user.id)}" aria-label="Sửa tài khoản ${app.esc(user.name)}">${app.esc(user.name)}</button><div class="muted">${app.esc(user.username)}</div></td><td><span class="badge neutral">${app.esc(roles[user.role] || user.role)}</span></td><td><span class="badge ${user.active ? 'success' : 'neutral'}">${user.active ? 'Đang hoạt động' : 'Đã khóa'}</span></td><td><button class="button quiet" data-action="admin-toggle" data-id="${app.esc(user.id)}" aria-label="${user.active ? 'Khóa' : 'Mở khóa'} tài khoản ${app.esc(user.name)}">${user.active ? 'Khóa' : 'Mở khóa'}</button></td></tr>`).join('')}
        </tbody></table></div>
      </section>
      <section class="surface" aria-labelledby="role-title"><div class="section-head"><h2 id="role-title">Ba tác nhân chính</h2></div><div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Vai trò</th><th scope="col">Phạm vi sử dụng</th></tr></thead><tbody>${['admin', 'manager', 'customer'].map(role => `<tr><td><strong>${roles[role]}</strong></td><td>${roleNotes[role]}</td></tr>`).join('')}</tbody></table></div><p class="inline-note">Nhân viên là quyền phụ thuộc bộ phận vận hành, không thêm một giao diện tác nhân riêng.</p></section>`;
  }

  function configuration(app) {
    return `<div class="page-head"><div><h1>Cấu hình bãi</h1><p>Thông tin chung của một bãi đỗ xe.</p></div></div>
      <section class="surface" aria-labelledby="lot-title"><div class="section-head"><h2 id="lot-title">Thông tin hiển thị</h2></div>
        <form data-action="admin-lot" class="form-grid">
          <label class="field">Tên bãi<input name="name" value="${app.esc(app.settings.name)}" maxlength="80" required></label>
          <label class="field">Giờ mở cửa<input name="hours" value="${app.esc(app.settings.hours)}" maxlength="60" required placeholder="00:00 – 24:00"></label>
          <div class="form-actions"><button type="submit" class="button primary">Lưu thông tin</button></div>
        </form>
      </section><p class="inline-note">Admin và Manager đều theo dõi khu vực, vị trí đỗ trong mục Bãi đỗ.</p>`;
  }

  function catalog(app) {
    if (!['admin', 'manager'].includes(app.ui.role)) return '<div class="empty"><p>Mục này dành cho Admin và Manager.</p></div>';
    const types = window.DemoEngine.typesFor(app.state);
    const admin = app.ui.role === 'admin';
    const draft = app.ui.catalogDraft || { label: '', prefix: '', rate: '5000', requiresPlate: true };
    return `<div class="page-head"><div><h1>Loại xe & bảng giá</h1><p>Quản lý các loại phương tiện mà bãi phục vụ.</p></div><button type="button" class="button ${app.ui.catalogFormOpen ? 'secondary' : 'primary'}" data-action="catalog-open-form" aria-expanded="${Boolean(app.ui.catalogFormOpen)}" aria-controls="catalog-create">${app.icon('plus')} Thêm loại xe</button></div>
      ${app.ui.catalogFormOpen ? `<section id="catalog-create" class="surface" aria-labelledby="type-form-title"><div class="section-head"><h2 id="type-form-title">Thêm loại xe</h2><span class="badge neutral">DEMO</span></div>
        <form data-action="catalog-add-type" class="form-grid">
          <label class="field">Tên loại xe<input name="label" value="${app.esc(draft.label)}" maxlength="50" required placeholder="Ví dụ: Xe tải nhẹ"></label>
          <label class="field">Mã khu<input name="prefix" value="${app.esc(draft.prefix)}" maxlength="8" required placeholder="Ví dụ: E"><small>Dùng đặt tên vị trí, ví dụ E-01.</small></label>
          <label class="field">Giá gửi · đồng/giờ<input name="rate" type="number" value="${app.esc(draft.rate)}" min="1" max="10000000" step="1" required></label>
          <label class="checkbox-field"><input type="checkbox" name="requiresPlate"${draft.requiresPlate ? ' checked' : ''}><span>Loại xe có biển số</span></label>
          <p class="inline-note">Loại xe mới có 0 vị trí. Sau khi thêm, vào Bãi đỗ để bổ sung chỗ phù hợp. Xe không có biển số được cấp mã xe/mã vé khi gửi.</p>
          <div class="form-actions"><button type="submit" class="button primary">Lưu loại xe</button><button type="button" class="button secondary" data-action="catalog-close-form">Hủy</button></div>
        </form></section>` : ''}
      <section class="surface" aria-labelledby="types-title"><div class="section-head"><h2 id="types-title">Loại xe đang phục vụ</h2><span class="muted">${types.length} loại xe</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Loại xe</th><th scope="col">Mã khu</th><th scope="col">Nhận dạng</th><th scope="col">Vị trí</th><th scope="col">Giá/giờ</th></tr></thead><tbody>${types.map(type => `<tr><td><strong>${app.esc(type.label)}</strong></td><td>${app.esc(type.prefix)}</td><td>${type.requiresPlate ? 'Biển số' : 'Mã xe / mã vé'}</td><td>${Number(app.state.capacity[type.id]) || 0}</td><td>${app.money(app.state.rates[type.id])}</td></tr>`).join('')}</tbody></table></div><div class="form-actions"><button type="button" class="button quiet" data-action="open-tab" data-tab="lot">Quản lý vị trí đỗ ${app.icon('arrow')}</button></div></section>
      ${admin ? `<details class="surface"><summary>Chỉnh sửa bảng giá hiện tại</summary>
      <section aria-labelledby="rates-title"><div class="section-head"><h2 id="rates-title">Giá gửi theo giờ</h2><span class="badge neutral">Dữ liệu mẫu</span></div>
        <form data-action="admin-rates" class="form-grid">
          ${types.map(type => `<label class="field">${app.esc(type.label)} · đồng/giờ<input name="${app.esc(type.id)}" type="number" min="0" max="10000000" step="1000" value="${app.esc(app.state.rates[type.id])}" required></label>`).join('')}
          <p class="inline-note">Bản demo tính tròn mỗi giờ đã bắt đầu, tối thiểu một giờ. Giá mới áp dụng cho xe vào sau khi lưu; lượt đang gửi giữ giá lúc vào.</p>
          <div class="form-actions"><button type="submit" class="button primary">Lưu bảng giá</button></div>
        </form>
      </section></details>` : '<p class="inline-note">Manager có thể thêm loại xe kèm giá ban đầu. Admin chỉnh sửa bảng giá hiện tại.</p>'}`;
  }

  function audit(app) {
    const entries = app.state.audit || [];
    return `<div class="page-head"><div><h1>Nhật ký hoạt động</h1><p>Các thao tác vừa thực hiện trong phiên demo này.</p></div></div>
      <section class="surface" aria-labelledby="audit-title"><div class="section-head"><h2 id="audit-title">Hoạt động gần đây</h2><span class="muted">${entries.length} bản ghi</span></div>
      ${entries.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Thời gian</th><th scope="col">Nội dung</th></tr></thead><tbody>${entries.slice(0, 100).map(item => `<tr><td class="tabular">${app.esc(app.time(item.at))}</td><td>${app.esc(item.text)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty"><p>Chưa có hoạt động trong phiên này.</p><p class="muted">Thử ghi nhận xe vào hoặc thay đổi bảng giá, rồi quay lại đây.</p></div>'}
      </section>`;
  }

  function render(app) {
    if (app.ui.tab === 'overview') return window.DemoReports.overview(app);
    if (app.ui.tab === 'finance') return window.DemoReports.revenue(app);
    return ({ accounts, configuration, catalog, audit }[app.ui.tab] || accounts)(app);
  }

  function handle(app, action, data) {
    if (action.startsWith('catalog-')) {
      if (!['admin', 'manager'].includes(app.ui.role)) {
        app.notify('Chỉ Admin và Manager được quản lý loại xe.');
        return true;
      }
      if (action === 'catalog-open-form') {
        if (app.ui.catalogFormOpen) return true;
        app.ui.catalogFormOpen = true;
        app.render();
        if (typeof document !== 'undefined') document.querySelector('form[data-action="catalog-add-type"] input[name="label"]')?.focus();
        return true;
      }
      if (action === 'catalog-close-form') {
        app.ui.catalogFormOpen = false;
        app.ui.catalogDraft = null;
        app.render();
        if (typeof document !== 'undefined') document.querySelector('[data-action="catalog-open-form"]')?.focus();
        return true;
      }
      if (action === 'catalog-add-type') {
        const draft = { label: read(data, 'label'), prefix: read(data, 'prefix'), rate: read(data, 'rate'), requiresPlate: ['on', 'true', '1'].includes(read(data, 'requiresPlate')) };
        app.ui.catalogDraft = draft;
        const result = window.DemoEngine.apply(app.state, { type: 'add-vehicle-type', role: app.ui.role, ...draft, rate: Number(draft.rate) });
        if (!result.ok) {
          app.notify(result.message);
          return true;
        }
        app.state = result.state;
        app.ui.catalogDraft = null;
        app.ui.catalogFormOpen = false;
        return finish(app, result.message);
      }
      return false;
    }
    if (!action.startsWith('admin-')) return false;
    if (action === 'admin-open-form' || action === 'admin-edit') {
      app.ui.adminFormOpen = true;
      app.ui.adminEditingId = action === 'admin-edit' ? read(data, 'id') : null;
      app.render();
      return true;
    }
    if (action === 'admin-close-form') {
      app.ui.adminFormOpen = false;
      app.ui.adminEditingId = null;
      app.render();
      return true;
    }
    if (action === 'admin-save-user') {
      const id = read(data, 'id');
      const name = read(data, 'name');
      const username = read(data, 'username').toLowerCase();
      const role = read(data, 'role');
      const user = app.users.find(item => String(item.id) === id);
      if (!name || name.length > 80 || !/^[a-z0-9_.-]{3,32}$/.test(username) || !Object.hasOwn(roles, role)) {
        app.notify('Kiểm tra họ tên, tên đăng nhập và vai trò.');
        return true;
      }
      if (id && !user) {
        app.notify('Tài khoản không còn trong bản demo.');
        return true;
      }
      if (app.users.some(item => item !== user && item.username.toLowerCase() === username)) {
        app.notify('Tên đăng nhập đã có. Chọn một tên khác.');
        return true;
      }
      if (user?.active && user.role === 'admin' && role !== 'admin' && app.users.filter(item => item.active && item.role === 'admin').length === 1) {
        app.notify('Cần giữ ít nhất một tài khoản Admin hoạt động.');
        return true;
      }
      if (user) Object.assign(user, { name, username, role });
      else app.users.push({ id: 'demo-' + Date.now(), name, username, role, active: true });
      record(app, `${user ? 'Sửa' : 'Thêm'} tài khoản mẫu ${username} · ${roles[role]}.`);
      app.ui.adminFormOpen = false;
      app.ui.adminEditingId = null;
      return finish(app, user ? 'Đã cập nhật tài khoản mẫu.' : 'Đã thêm tài khoản mẫu.');
    }
    if (action === 'admin-toggle') {
      const user = app.users.find(item => String(item.id) === read(data, 'id'));
      if (!user) return true;
      if (user.active && user.role === 'admin' && app.users.filter(item => item.active && item.role === 'admin').length === 1) {
        app.notify('Cần giữ ít nhất một tài khoản Admin hoạt động.');
        return true;
      }
      user.active = !user.active;
      record(app, `${user.active ? 'Mở khóa' : 'Khóa'} tài khoản mẫu ${user.username}.`);
      return finish(app, `Đã ${user.active ? 'mở khóa' : 'khóa'} tài khoản ${user.username}.`);
    }
    if (action === 'admin-lot') {
      const name = read(data, 'name');
      const hours = read(data, 'hours');
      if (!name || name.length > 80 || !hours || hours.length > 60) {
        app.notify('Nhập tên bãi và giờ mở cửa hợp lệ.');
        return true;
      }
      Object.assign(app.settings, { name, hours });
      record(app, 'Cập nhật thông tin hiển thị của bãi.');
      return finish(app, 'Đã lưu thông tin bãi trong bản demo.');
    }
    if (action === 'admin-rates') {
      if (app.ui.role !== 'admin') {
        app.notify('Chỉ Admin được sửa bảng giá hiện tại.');
        return true;
      }
      const types = window.DemoEngine.typesFor(app.state);
      const rates = Object.fromEntries(types.map(type => [type.id, Number(read(data, type.id))]));
      if (types.some(type => !read(data, type.id)) || Object.values(rates).some(value => !Number.isInteger(value) || value < 0 || value > 10000000)) {
        app.notify('Nhập mức phí từ 0 đến 10.000.000 đồng.');
        return true;
      }
      Object.assign(app.state.rates, rates);
      record(app, `Cập nhật bảng giá: ${types.map(type => `${type.label} ${app.money(rates[type.id])}/giờ`).join('; ')}.`);
      return finish(app, 'Đã lưu bảng giá cho các lượt vào mới.');
    }
    return false;
  }

  window.AdminDemo = { render, handle, catalog };
})();
