/* Role-scoped, deterministic sample assistant. No network or real LLM. */
(() => {
  'use strict';
  const E = window.DemoEngine;
  const A = window.DemoAnalytics;
  const histories = { customer: [], staff: [], manager: [], admin: [] };
  const drafts = { customer: '', staff: '', manager: '', admin: '' };
  let open = false;
  const robot = '<svg viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="8" width="18" height="15" rx="5"/><path d="M14 8V4m-2 0h4M2 13v5m24-5v5m-16-3v2m8-2v2m-7 4h6"/></svg>';
  const normalize = text => String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();

  function publicContext(app) {
    return {
      at: app.state.now,
      hours: app.settings.hours,
      vehicles: E.typesFor(app.state).filter(t => t.active !== false).map(t => ({ id:t.id, label:t.label, price:app.state.rates[t.id], free:E.available(app.state,t.id), capacity:Number(app.state.capacity[t.id])||0, requiresPlate:t.requiresPlate }))
    };
  }
  function reply(app, question) {
    const q = normalize(question);
    const context = publicContext(app);
    const customer = app.ui.role === 'customer';
    if (app.ui.role === 'staff' && A.financialQuestion(question)) return 'Nhân viên chỉ xem lưu lượng và chỗ trống. Báo cáo thu dành cho Manager và Admin.';
    const privateQuestion = /doanh thu|bao cao thu|tong thu|thu chi|so tien thu|da thu|nhan su|nhan vien|tai khoan|khach hang|lich su xe|danh sach xe|tong quan|xe trong bai|xe dang gui|so luot|cao diem|gio dong/.test(q);
    if (customer && privateQuestion) return 'Mình có thể giúp bạn về giá gửi xe, chỗ còn trống, đặt trước và cách thanh toán. Báo cáo thu, thông tin nhân viên và hoạt động nội bộ chỉ dành cho quản lý bãi.';
    const analysis = () => A.generate(app.state, { kind: /nhan su|chia ca|bo tri nhan vien/.test(q) ? 'staff' : 'question',
      period: /tuan|7 ngay/.test(q) ? 'week' : 'day', anchorDate: A.day(app.state.now), question, role: app.ui.role }).text;
    if (!customer && (A.financialQuestion(q) || /bao cao|luu luong|cao diem|dong nhat|nhan su|chia ca|bo tri nhan vien|tong quan|luot vao|luot ra/.test(q))) return analysis();
    let requested = context.vehicles;
    const named = context.vehicles.filter(t=>q.includes(normalize(t.label)));
    if (named.length) requested = named.filter(t=>!named.some(other=>other.id!==t.id && normalize(other.label).includes(normalize(t.label))));
    else if (/xe dap dien/.test(q)) requested = requested.filter(t=>t.id==='ebike');
    else if (/xe dap/.test(q)) requested = requested.filter(t=>t.id==='bicycle');
    else if (/xe may/.test(q)) requested = requested.filter(t=>t.id==='motorbike');
    else if (/o to|xe hoi/.test(q)) requested = requested.filter(t=>t.id==='car');
    if (/\bgia\b|bang phi|phi gui|bao nhieu tien|tinh phi/.test(q)) {
      if (!requested.length) return 'Chưa có loại xe phù hợp trong bảng giá mẫu. Bạn có thể hỏi “Bảng giá gửi xe” để xem các loại bãi đang phục vụ.';
      return 'Bảng giá mẫu hiện tại:\n' + requested.map(t=>`${t.label}: ${app.money(t.price)}/giờ.`).join('\n') + '\n\nTính tròn mỗi giờ đã bắt đầu, tối thiểu một giờ. Lượt đang gửi giữ bảng giá lúc vào; tra phí để xem số tiền chính xác của lượt đó.';
    }
    if (/cho trong|con.*cho|suc chua|cho khong|bai.*trong/.test(q) && !/dat cho|giu cho|dat truoc/.test(q)) {
      if (!requested.length) return 'Chưa có loại xe phù hợp trong dữ liệu mẫu. Bạn có thể hỏi “Còn chỗ không?” để xem toàn bãi.';
      return `Chỗ có thể nhận xe lúc ${app.time(context.at)} (giờ demo):\n` + requested.map(t=>t.capacity ? `${t.label}: còn ${t.free}/${t.capacity} chỗ.` : `${t.label}: chưa có vị trí được cấu hình, hiện chưa nhận xe.`).join('\n') + '\n\nĐã trừ các vị trí đang có xe và chỗ được giữ trước.' + (requested.some(t=>t.free>0) ? ' Bạn có thể đến gửi trực tiếp nếu còn vị trí phù hợp.' : customer ? ' Hiện chưa có chỗ nhận các loại xe này.' : ' Vào Bãi đỗ để kiểm tra hoặc thêm vị trí phù hợp.');
    }
    if (/dat cho|dat ve|giu cho|dat truoc/.test(q)) return 'Vào “Đặt chỗ trước”, chọn loại xe và giờ đến/về dự kiến. Xe có biển số thì nhập biển số; xe đạp không có biển số sẽ được cấp mã xe. Không thu tiền đặt trước; chỉ tính phí từ lúc xe thực sự vào. Giữ chỗ đến 15 phút sau giờ hẹn. Bạn cũng có thể đến gửi trực tiếp, không bắt buộc đặt chỗ.';
    if (/thanh toan|ma ve|qr|mat ve/.test(q)) return 'Mở “Phí gửi xe”, chọn đúng loại xe và nhập biển số hoặc mã xe/mã vé. Nếu lượt chưa liên kết, xác nhận bằng mã trên vé, rồi chọn thanh toán. QR và kết quả thanh toán trong demo này chỉ là mô phỏng. Nếu mất vé, gửi yêu cầu trong mục Hỗ trợ.';
    if (/gio mo|mo cua|dong cua/.test(q)) return `Giờ mở cửa mẫu: ${context.hours}. Bạn có thể hỏi thêm giá gửi xe hoặc chỗ còn trống.`;
    if (!customer) {
      if (/tai khoan/.test(q) && app.ui.role==='admin') return `Trong demo có ${app.users.length} tài khoản mẫu, ${app.users.filter(u=>u.active).length} đang hoạt động. Vào “Tài khoản” để quản lý vai trò và trạng thái. Không có thông tin đăng nhập thật trong bản thử.`;
      return analysis();
    }
    return 'Mình hỗ trợ bạn tra bảng giá, chỗ còn trống, giờ mở cửa, cách đặt trước và thanh toán. Bạn thử hỏi “Giá gửi xe đạp?” hoặc “Còn chỗ ô tô không?” nhé. Câu trả lời đang dùng dữ liệu mẫu của demo.';
  }
  function render(app) {
    const role=app.ui.role;
    const customer=role==='customer';
    const questions=customer?['Giá gửi xe','Còn chỗ không?','Đặt chỗ thế nào?']:['Lưu lượng hôm nay','Cao điểm tuần này','Gợi ý nhân sự'];
    const messages=histories[role];
    const greeting=customer?'Chào bạn! Mình giúp bạn xem giá, tìm chỗ trống và hướng dẫn đặt trước.':'Chào bạn! Mình có thể tóm tắt lưu lượng ngày/tuần, chỗ trống và gợi ý khung trực từ số liệu DEMO.';
    return `<div class="chat-widget">${open?`<section class="chat-window" role="dialog" aria-modal="false" aria-labelledby="chat-title"><header class="chat-header"><div class="chat-avatar">${robot}</div><div><h2 id="chat-title">Trợ lý ParkingAI</h2><p>${customer?'Hỗ trợ khách hàng':'Trợ lý quản lý bãi'} · ${app.esc(role==='admin'?'Admin':role==='manager'?'Manager':role==='staff'?'Staff':'Customer')}</p></div><button type="button" class="chat-close" data-action="chat-close" aria-label="Thu gọn chatbot">${app.icon('close')}</button></header><div class="chat-disclaimer">Demo trả lời theo dữ liệu mẫu · Chưa kết nối AI thật</div><div class="chat-messages" role="log" aria-live="polite" aria-relevant="additions text"><div class="bubble assistant">${app.esc(greeting)}</div>${messages.map(m=>`<div class="bubble ${m.role}"><span class="sr-only">${m.role==='user'?'Bạn':'Trợ lý'}: </span>${app.esc(m.text)}</div>`).join('')}</div><div class="chat-suggestions">${questions.map(q=>`<button type="button" data-action="chat-suggest" data-question="${app.esc(q)}">${app.esc(q)}</button>`).join('')}</div><form data-action="chat-send" class="chat-compose"><label class="sr-only" for="chat-input">Câu hỏi cho trợ lý ParkingAI</label><textarea id="chat-input" name="question" rows="1" maxlength="600" placeholder="Nhập câu hỏi…" required>${app.esc(drafts[role])}</textarea><button type="submit" aria-label="Gửi câu hỏi">${app.icon('arrow')}</button></form></section>`:''}<button type="button" class="chat-launcher ${open?'is-open':''}" data-action="${open?'chat-close':'chat-open'}" aria-expanded="${open}" aria-label="${open?'Thu gọn chatbot':'Mở chatbot ParkingAI'}">${open?app.icon('close'):robot}</button>${!open?'<span class="chat-launcher-label">Hỏi ParkingAI</span>':''}</div>`;
  }
  function focusInput() { requestAnimationFrame(()=>{document.getElementById('chat-input')?.focus();const messages=document.querySelector('.chat-messages');if(messages)messages.scrollTop=messages.scrollHeight;}); }
  function refresh(app) { const mount=document.getElementById('chat-mount'); if(mount)mount.innerHTML=render(app); }
  function handle(app,action,data) {
    if(!action.startsWith('chat-'))return false;
    if(action==='chat-open'){open=true;refresh(app);focusInput();return true;}
    if(action==='chat-close'){open=false;refresh(app);document.querySelector('.chat-launcher')?.focus();return true;}
    const question=String(action==='chat-suggest'?data.question:data.get('question')||'').trim().slice(0,600);
    if(!question)return true;
    histories[app.ui.role].push({role:'user',text:question},{role:'assistant',text:reply(app,question)});
    if(histories[app.ui.role].length>30)histories[app.ui.role].splice(0,2);
    drafts[app.ui.role]='';open=true;refresh(app);focusInput();return true;
  }
  document.addEventListener('input',e=>{if(e.target.id==='chat-input')drafts[window.ParkingDemo.ui.role]=e.target.value;});
  document.addEventListener('keydown',e=>{if(e.target.id==='chat-input'&&e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();e.target.form.requestSubmit();}if(e.key==='Escape'&&open&&!document.querySelector('.modal'))handle(window.ParkingDemo,'chat-close',{});});
  window.DemoChat={render,handle,reply,reset(){for(const role of Object.keys(histories)){histories[role]=[];drafts[role]='';}open=false;}};
})();
