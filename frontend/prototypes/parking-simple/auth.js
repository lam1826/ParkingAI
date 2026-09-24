/* Preview authentication only. No network, secrets or security boundary. */
(() => {
  'use strict';
  const labels = {admin:'Admin',manager:'Manager',staff:'Nhân viên',customer:'Customer'};
  const read = (data,key) => String(typeof data?.get === 'function' ? data.get(key) || '' : data?.[key] || '').trim();
  function render(app) {
    const draft=app.ui.loginDraft || {username:'manager_demo',password:''};
    return `<main class="login-shell"><section class="login-intro"><div class="brand">ParkingAI</div><h1>Một bãi xe.<br>Mọi thao tác rõ ràng.</h1><p>Thử nhận xe, thu phí, quản lý vé tháng và xem báo cáo từ dữ liệu mẫu. Chọn vai trò để khám phá giao diện phù hợp.</p><div class="login-note">Dữ liệu chỉ tồn tại trong tab này. Đăng nhập, AI, camera và thanh toán đều được mô phỏng để duyệt thiết kế.</div></section><section class="surface login-form"><h2>Đăng nhập</h2><p class="muted">Dùng tài khoản mẫu để thử quyền truy cập.</p><form data-action="auth-login"><label class="field">Tên đăng nhập<input name="username" value="${app.esc(draft.username)}" required autocomplete="off" placeholder="manager_demo"></label><label class="field">Mật khẩu demo<input name="password" type="password" value="${app.esc(draft.password)}" required autocomplete="off" placeholder="demo123"></label>${app.ui.loginError?`<p class="form-error" role="alert">${app.esc(app.ui.loginError)}</p>`:''}<button class="button primary full" type="submit">Đăng nhập bản demo ${app.icon('arrow')}</button></form><p class="inline-note">Mật khẩu mẫu dùng chung: <strong>demo123</strong>. Chỉ có hiệu lực trong bản mô phỏng.</p><div class="divider"></div><h3>Xem nhanh từng giao diện</h3><div class="login-roles">${['admin','manager','customer'].map(role=>`<button class="button secondary" data-action="auth-quick" data-role="${role}">${labels[role]}</button>`).join('')}</div><button class="button quiet full" data-action="auth-quick" data-role="staff">Thử quyền Nhân viên bãi xe</button><button class="button quiet full" data-action="demo-guide">Đối chiếu chức năng với đề tài</button></section></main>`;
  }
  function profile(app) {
    const user=app.users.find(row=>row.id===app.ui.userId);
    return `<div class="page-head"><div><h1>Tài khoản của tôi</h1><p>Thông tin và quyền trong phiên xem trước.</p></div></div><section class="surface narrow-surface"><form data-action="auth-profile-save"><label class="field">Họ tên<input name="name" value="${app.esc(user?.name)}" maxlength="80" required></label><label class="field">Email<input type="email" name="email" value="${app.esc(user?.email||'')}" maxlength="100"></label><dl class="definition-list"><div><dt>Tên đăng nhập</dt><dd>${app.esc(user?.username)}</dd></div><div><dt>Vai trò</dt><dd>${labels[user?.role]||''}</dd></div></dl><div class="form-actions"><button class="button primary" type="submit">Lưu thông tin</button><button class="button secondary" type="button" data-action="auth-logout">Đăng xuất</button></div></form></section>`;
  }
  function handle(app,action,data) {
    if(action==='auth-logout'){app.exitSession();return true;}
    if(action==='auth-profile'){app.ui.tab='profile';app.render();return true;}
    if(action==='auth-profile-save'){
      const name=read(data,'name'),email=read(data,'email');
      const user=app.users.find(row=>row.id===app.ui.userId&&row.active);
      if(!user||!name||name.length>80||email.length>100){app.notify('Kiểm tra tên và email.');return true;}
      Object.assign(user,{name,email});app.state.audit.unshift({at:app.state.now,text:'Cập nhật hồ sơ tài khoản mẫu '+user.username+'.'});app.render();app.notify('Đã lưu thông tin trong bản demo.');return true;
    }
    if(action!=='auth-login'&&action!=='auth-quick')return false;
    const quick=action==='auth-quick';
    const username=read(data,'username').toLowerCase();
    const password=read(data,'password');
    const user=quick?app.users.find(row=>row.role===read(data,'role')&&row.active):app.users.find(row=>row.username.toLowerCase()===username);
    if(!user||!user.active||(!quick&&password!=='demo123')){
      app.ui.loginDraft={username,password:''};app.ui.loginError='Tên đăng nhập, mật khẩu hoặc trạng thái tài khoản không phù hợp.';app.render();return true;
    }
    app.ui.loginError=null;app.enterRole(user.role,user.id);
    app.state.audit.unshift({at:app.state.now,text:'Đăng nhập mô phỏng: '+user.username+' ('+labels[user.role]+').'});
    app.notify('Đã vào giao diện '+labels[user.role]+'.');return true;
  }
  window.DemoAuth={render,profile,handle};
})();
