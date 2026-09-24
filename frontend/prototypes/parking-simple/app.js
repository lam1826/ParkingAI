(() => {
  'use strict';
  const E = window.DemoEngine;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => new Intl.NumberFormat('vi-VN').format(value || 0) + ' đ';
  const time = value => new Intl.DateTimeFormat('vi-VN', {hour:'2-digit',minute:'2-digit',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(value));
  const date = value => new Intl.DateTimeFormat('vi-VN', {day:'2-digit',month:'2-digit',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(value));
  const paths = {
    car:'M5 17H3V9l2-5h14l2 5v8h-2M5 17v3H3v-3m16 0v3h2v-3M3 10h18M7 14h2m6 0h2M5 17h14',
    bike:'M5 19a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm14 0a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 15l5-8 5 8H5m5-8h5m-5 0H7m8 8 3-11h3',
    parking:'M6 21V3h7a6 6 0 0 1 0 12H6m0-8h7a2 2 0 0 1 0 4H6',
    calendar:'M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Zm3 10h3m-3 4h6',
    ticket:'M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4V6Zm12 0v3m0 6v3m0-7v2',
    help:'M21 11a9 9 0 1 0-4 7l4 3v-6m-12-7a3 3 0 1 1 4 3l-1 1m0 3v.1',
    camera:'M3 7h4l2-3h6l2 3h4v13H3V7Zm9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
    users:'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM2 21v-3a7 7 0 0 1 14 0v3m0-17a4 4 0 0 1 0 8m3 3a6 6 0 0 1 3 6',
    shield:'m12 2 8 3v7c0 5-8 10-8 10S4 17 4 12V5l8-3Zm-4 10 3 3 5-6',
    settings:'M4 7h16M4 17h16M8 4v6m8 4v6',
    history:'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v6l3 2',
    chart:'M3 3v18h18M7 16v-5m5 5V6m5 10v-8',
    wallet:'M20 8H5a2 2 0 0 1 0-4h13v4M3 6v14h18V8m0 4h-6v4h6',
    arrow:'M4 12h16m-6-6 6 6-6 6',
    plus:'M12 4v16M4 12h16',
    check:'m5 12 4 4L19 6',
    close:'m6 6 12 12M6 18 18 6',
    search:'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 6 6',
    clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v6l4 2',
    user:'M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm-9 9a9 9 0 0 1 18 0',
    logout:'M9 3H3v18h6m4-14 5 5-5 5m-5-5h13',
    reset:'M3 4v6h6M3 10a9 9 0 1 1 1 8',
    spark:'M12 3v3m0 12v3M3 12h3m12 0h3m-9-5 2 4 4 2-4 2-2 4-2-4-4-2 4-2 2-4Z'
  };
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.parking}"/></svg>`;
  const btn = (action,label,kind='primary',extra='') => `<button type="button" class="button ${kind}" data-action="${action}" ${extra}>${label}</button>`;
  const typeOptions = value => E.typesFor(app.state).filter(t=>t.active!==false).map(t=>`<option value="${t.id}" ${value===t.id?'selected':''}>${esc(t.label)}</option>`).join('');
  const identifierLabel = type => E.typeInfo(type,app.state)?.requiresPlate === false ? 'Mã xe / mã vé' : 'Biển số xe';
  const duration = minutes => `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`;
  const internalNavigation = [['overview','chart','Tổng quan'],['operations','car','Vận hành'],['lot','parking','Bãi đỗ'],['history','history','Lịch sử gửi xe'],['customers','users','Khách & vé'],['finance','wallet','Thu chi & báo cáo'],['catalog','parking','Loại xe & bảng giá']];
  const navigation = {
    customer:[['fees','wallet','Phí gửi xe'],['booking','calendar','Đặt chỗ trước'],['tickets','ticket','Vé & lịch sử'],['support','help','Hỗ trợ']],
    manager:internalNavigation,
    staff:internalNavigation.filter(item=>['operations','lot','history','customers','finance'].includes(item[0])),
    admin:[...internalNavigation,['accounts','users','Tài khoản & quyền'],['configuration','settings','Cấu hình bãi'],['audit','history','Nhật ký hoạt động']]
  };
  const names = {customer:'Customer',manager:'Manager',admin:'Admin',staff:'Nhân viên'};
  const seedUsers = () => [
    {id:'u1',name:'Minh Quang',username:'admin_demo',role:'admin',active:true},
    {id:'u2',name:'Ngọc Linh',username:'manager_demo',role:'manager',active:true},
    {id:'u3',name:'Anh Tú',username:'customer_demo',role:'customer',active:true},
    {id:'u4',name:'Quốc Huy',username:'staff_demo',role:'staff',active:true}
  ];
  const firstRole = ['customer','manager','admin','staff'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'customer';
  const app = window.ParkingDemo = {
    state:E.seed(), users:seedUsers(),settings:{name:'ParkingAI · Bãi trung tâm',hours:'00:00 – 24:00'},
    ui:{loggedIn:['customer','manager','admin','staff'].includes(location.hash.slice(1)),userId:seedUsers().find(u=>u.role===firstRole).id,role:firstRole,tab:navigation[firstRole][0][0],plate:'59A-123.45',vehicleType:'car',searched:false,mode:'manual',direction:'entry',selected:null,modal:null,cameraOn:false,cameraResult:null},
    esc,money,time,date,icon,notify,render,dispatch,showModal,closeModal,enterRole:chooseRole,exitSession
  };
  let toastTimer, cameraTimer, modalReturnFocus;
  function notify(message){const el=document.getElementById('toast');el.textContent=message;el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,4800);}
  function dispatch(action){const result=E.apply(app.state,{...action,role:app.ui.role});if(result.ok)app.state=result.state;render();notify(result.message);return result;}
  function head(title,subtitle,actions=''){return `<div class="page-head"><div><h1>${title}</h1><p>${subtitle}</p></div>${actions?`<div class="head-actions">${actions}</div>`:''}</div>`;}
  function canRead(s){return s.owned || app.state.customerAccess.includes(s.id);}
  function lookup(){return E.lookupSession(app.state,app.ui.plate,app.ui.vehicleType);}
  function slotsArt(){return `<svg viewBox="0 0 440 210" role="img" aria-label="Minh họa bãi đỗ xe mẫu"><rect x="12" y="16" width="416" height="180" rx="14" fill="#eaf1f8"/><path d="M12 107h416" stroke="#fff" stroke-width="45"/><path d="M22 107h396" stroke="#b2c6d9" stroke-dasharray="9 10"/><g stroke="#c0d1e1" fill="none" stroke-width="2">${[55,120,185,250,315,380].map(x=>`<path d="M${x} 28v50m0 59v47"/>`).join('')}</g>${[[73,28,'#3e80be'],[203,28,'#a6c0d9'],[333,28,'#417cad'],[138,133,'#97b5cc'],[268,133,'#2f71ad']].map(([x,y,c])=>`<g transform="translate(${x} ${y})"><rect width="31" height="50" rx="9" fill="${c}"/><path d="M5 10h21l-2 8H7ZM7 35h17l2 7H5Z" fill="#e4eff9"/><path d="M2 17v15m27-15v15" stroke="#182f452f" stroke-width="2"/></g>`).join('')}<path d="m210 101 8 6-8 6m8-6h-17" stroke="#88a9c5" stroke-width="2" fill="none"/></svg>`;}
  function availability(){return `<section class="surface availability-panel"><div class="section-head"><h2>Còn chỗ cho chuyến đi của bạn</h2></div><div class="parking-illustration">${slotsArt()}</div>${E.typesFor(app.state).map(v=>v.id).map(t=>`<div class="capacity-row"><span>${esc(E.typeLabel(t,app.state))}</span><span><strong>${E.available(app.state,t)}</strong> / ${app.state.capacity[t]} chỗ nhận xe</span></div><div class="capacity-meter"><div class="capacity-fill" style="width:${E.available(app.state,t)/Math.max(1,app.state.capacity[t])*100}%"></div></div>`).join('')}<p>Bạn có thể đến gửi trực tiếp. Đặt trước khi muốn giữ sẵn một chỗ phù hợp.</p>${btn('goto-booking','Đặt chỗ trước '+icon('arrow'),'quiet')}</section>`;}
  function summary(s){const q=E.quote(app.state,s);return `<div class="section-head"><span class="plate">${esc(s.plate)}</span><span class="badge ${q.due?'warning':'success'}">${q.due?'Chưa thanh toán đủ':'Đã thanh toán'}</span></div><div class="muted" style="font-size:13px">Số tiền còn phải trả</div><div class="fee-total">${money(q.due)}</div><div class="fee-lines"><div class="fee-line"><span>Loại xe</span><span>${esc(E.typeLabel(s.vehicleType,app.state))}</span></div><div class="fee-line"><span>Giờ vào</span><span>${time(s.entry)} · ${date(s.entry)}</span></div><div class="fee-line"><span>Thời gian gửi</span><span>${duration(q.minutes)}</span></div>${q.monthlyPassId?`<div class="fee-line"><span>Vé tháng áp dụng</span><span>${esc(q.monthlyPassId)} · đến hết ${date(new Date(new Date(q.coverageEnd).getTime()-1))}</span></div><div class="fee-line"><span>Thời gian tính phí ngoài vé</span><span>${duration(q.billableMinutes||0)}</span></div>`:''}<div class="fee-line"><span>Phí gửi xe</span><span>${money(q.gross)}</span></div><div class="fee-line"><span>Đã thanh toán</span><span>${money(q.paid)}</span></div></div>`;}
  function customerFees(){const s=lookup();return `${head('Tra phí & thanh toán','Xem thời gian gửi và thanh toán trước khi lấy xe.')}<div class="content-grid"><div><section class="surface"><div class="section-head"><h2>Xe của bạn</h2>${icon('car')}</div><form data-action="customer-lookup"><div class="field"><label for="customer-plate">${identifierLabel(app.ui.vehicleType)}</label><input id="customer-plate" name="plate" value="${esc(app.ui.plate)}" placeholder="Ví dụ: 59A-123.45" maxlength="20" required autocomplete="off"></div><div class="field"><label for="customer-type">Loại xe</label><select id="customer-type" name="vehicleType">${typeOptions(app.ui.vehicleType)}</select></div><button class="button primary full" type="submit">${icon('search')} Tra phí gửi xe</button></form><p class="muted" style="font-size:12px;margin-top:16px">Xe mẫu: ${btn('sample-owned','59A-123.45','quiet small')} ${btn('sample-ticket','59B1-678.90','quiet small')} ${btn('sample-bicycle','XD-001 · Xe đạp','quiet small')}</p></section>${app.ui.searched ? s&&canRead(s)?`<section class="surface fee-panel">${summary(s)}${E.quote(app.state,s).due?btn('open-pay','Thanh toán online '+icon('arrow'),'primary full',`data-id="${s.id}"`):`<div class="receipt-success">${icon('check')}Đã thanh toán phí hiện tại. Bạn có thể đến cổng lấy xe.</div><p class="muted" style="font-size:12px">Phí sẽ được kiểm tra lại khi xe ra nếu bạn gửi thêm thời gian.</p>`}</section>`:s?`<section class="surface"><h2>Xác nhận lượt gửi của bạn</h2><p class="muted" style="font-size:13px;margin-top:8px">Nhập mã trên vé để xem phí của lượt này. Không cần đăng ký sở hữu xe.</p><form data-action="claim" style="margin-top:18px"><div class="field"><label for="ticket">Mã vé</label><input id="ticket" name="ticket" placeholder="Mã vé mẫu: VE-4096" required></div><button class="button primary" type="submit">Xác nhận vé</button></form></section>`:`<section class="surface empty">${icon('search')}Chưa tìm thấy lượt gửi phù hợp. Kiểm tra biển số và loại xe rồi thử lại.</section>`:''}</div>${availability()}</div>`;}
  function bookingList(readonly=false){const rows=app.state.reservations;return rows.length?rows.map(r=>`<div class="booking-row"><div><div class="plate">${esc(r.plate)}</div><p>${esc(E.typeLabel(r.vehicleType,app.state))} · ${time(r.start)} – ${time(r.end)} · ${date(r.start)}</p><p>${esc(r.slot||'Vị trí phù hợp sẽ được giữ')}</p></div><div><span class="badge ${r.status==='confirmed'?'success':'neutral'}">${({confirmed:'Đã giữ chỗ',arrived:'Đã vào bãi',cancelled:'Đã hủy',expired:'Hết hạn'})[r.status]||esc(r.status)}</span>${!readonly&&r.status==='confirmed'?btn('cancel-booking','Hủy','quiet small',`data-id="${r.id}"`):''}</div></div>`).join(''):`<div class="empty">${icon('calendar')}Chưa có đặt chỗ. Bạn vẫn có thể đến gửi trực tiếp.</div>`;}
  function customerBooking(){return `${head('Đặt chỗ trước','Giữ một chỗ phù hợp, thanh toán theo thời gian gửi thực tế.')}<div class="content-grid"><section class="surface"><div class="section-head"><h2>Thông tin đặt chỗ</h2></div><form data-action="reserve"><div class="form-grid"><div class="field"><label for="book-plate">Biển số</label><input id="book-plate" name="plate" placeholder="Ví dụ: 51K-246.80" required maxlength="20"></div><div class="field"><label for="book-type">Loại xe</label><select id="book-type" name="vehicleType">${typeOptions('car')}</select></div><div class="field"><label for="book-start">Giờ đến dự kiến</label><input id="book-start" type="datetime-local" name="start" value="2026-09-23T17:00" required></div><div class="field"><label for="book-end">Giờ về dự kiến</label><input id="book-end" type="datetime-local" name="end" value="2026-09-23T20:00" required></div></div><div class="inline-note">Không thu tiền trước. Chỗ được giữ đến 15 phút sau giờ hẹn; tiền gửi tính từ lúc xe vào.</div><button type="submit" class="button primary full">Giữ chỗ cho tôi ${icon('arrow')}</button></form></section><section class="surface"><div class="section-head"><h2>Lịch sắp đến</h2></div>${bookingList()}</section></div>`;}
  function customerTickets(){
    const owner=app.state.customers?.find(c=>c.owned)||app.state.customers?.[0];
    const passes=(app.state.monthlyPasses||[]).filter(p=>p.customerId===owner?.id);
    const rows=app.state.sessions.filter(s=>s.owned&&s.status==='closed');
    const payments=app.state.transactions.filter(t=>app.ui.customerPayments?.includes(t.id));
    return `${head('Vé & lịch sử','Vé tháng, thời hạn và chứng từ của bạn.')}<div class="content-grid"><section class="surface"><div class="section-head"><h2>Vé tháng của bạn</h2><span class="badge neutral">Dữ liệu mẫu</span></div>${passes.length?passes.map(p=>{const status=E.passStatus(app.state,p);return `<div class="list-row"><div><strong>${esc(p.id)} · ${esc(p.plate)}</strong><p>${esc(E.typeLabel(p.vehicleType,app.state))}</p><p>${esc(p.startDate)} → ${esc(p.endDate)}</p><p>Giá vé: ${money(p.price)}</p></div><span class="badge ${status.key==='active'?'success':'neutral'}">${esc(status.label)}</span></div>`;}).join(''):'<div class="empty">Bạn chưa có vé tháng.</div>'}<p class="inline-note">Liên hệ quản lý để đăng ký hoặc gia hạn. Có thể thử cấp vé ở Manager → Khách & vé → Vé tháng rồi quay lại đây.</p></section><section class="surface"><div class="section-head"><h2>Chứng từ thanh toán</h2></div>${payments.length?payments.map(t=>`<div class="history-row"><div><span class="plate">${esc(t.plate)}</span><small>${date(t.at)} · ${time(t.at)} · Online mô phỏng</small></div><strong>${money(t.amount)}</strong></div>`).join(''):'<div class="empty">Chưa có thanh toán trong lần thử này.</div>'}<div class="divider"></div><h3>Lượt gửi đã kết thúc</h3>${rows.length?rows.map(s=>`<div class="history-row"><div>${esc(s.plate)}<small>${date(s.entry)} · ${time(s.entry)} – ${time(s.exit)}</small></div><span>${money(E.quote(app.state,s).gross)}</span></div>`).join(''):'<p class="muted">Lịch sử xuất hiện sau khi xe ra.</p>'}</section></div>`;
  }
  function customerSupport(){return `${head('Bạn cần hỗ trợ?','Gửi yêu cầu để quản lý bãi tiếp nhận.')}<div class="content-grid"><section class="surface"><form data-action="support"><div class="field"><label for="subject">Vấn đề cần hỗ trợ</label><select id="subject" name="subject"><option>Thanh toán & hoàn tiền</option><option>Đặt chỗ trước</option><option>Mất vé / không tìm thấy lượt</option></select></div><div class="field"><label for="message">Nội dung</label><textarea id="message" name="message" placeholder="Mô tả vấn đề để quản lý hỗ trợ bạn…" required></textarea></div><button class="button primary" type="submit">Gửi yêu cầu</button></form></section><section class="surface"><h2>Yêu cầu của bạn</h2>${app.state.support.length?app.state.support.map(r=>`<div class="list-row"><div><strong>${esc(r.subject)}</strong><p>${esc(r.message)}</p></div><span class="badge warning">Đã tiếp nhận</span></div>`).join(''):'<div class="empty">Chưa có yêu cầu hỗ trợ.</div>'}</section></div>`;}
  function activeTable(){const rows=app.state.sessions.filter(s=>s.status==='active');return `<section class="surface" style="margin-top:24px"><div class="section-head"><div><h2>Xe đang trong bãi <span class="badge neutral">${rows.length}</span></h2><p>Chọn một xe để xem phí, thu tiền hoặc cho xe ra. Xe không có biển số dùng mã xe/mã vé.</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Biển số / mã xe</th><th>Loại xe</th><th>Giờ vào</th><th>Vị trí</th><th>Còn trả</th><th><span class="sr-only">Thao tác</span></th></tr></thead><tbody>${rows.map(s=>`<tr><td class="plate">${esc(s.plate)}</td><td>${esc(E.typeLabel(s.vehicleType,app.state))}</td><td>${time(s.entry)}</td><td>${esc(s.slot)}</td><td>${money(E.quote(app.state,s).due)}</td><td>${btn('select-session','Xem phí','quiet small',`data-id="${s.id}"`)}</td></tr>`).join('')}</tbody></table>${!rows.length?'<div class="empty">Bãi chưa có xe.</div>':''}</div></section>`;}
  function cameraScene(){return `<div class="camera-stage"><div class="camera-label">CAM 01 · Làn ${app.ui.direction==='entry'?'vào':'ra'} · HÌNH MÔ PHỎNG</div><svg viewBox="0 0 500 275" aria-label="Mô phỏng góc nhìn camera tại làn xe" role="img"><path d="M0 65h500v210H0Z" fill="#294359"/><path d="m170 70-95 205m255-205 95 205" stroke="#6b8193" stroke-width="3"/><path d="M250 73v20m0 17v28m0 20v35m0 23v34" stroke="#8b9caa" stroke-width="3"/><g transform="translate(162 70)"><path d="m20 38 16-31h106l16 31 10 13v77H10V51Z" fill="#c7d7e7" stroke="#e2ebf3" stroke-width="2"/><path d="m46 16-13 28h112l-14-28Z" fill="#29465d"/><rect x="26" y="64" width="24" height="12" rx="3" fill="#edf6d9"/><rect x="124" y="64" width="24" height="12" rx="3" fill="#edf6d9"/><rect x="62" y="91" width="52" height="16" rx="2" fill="#f9fcff"/><text x="88" y="102" text-anchor="middle" font-family="Arial" font-size="8" fill="#21364b">${app.ui.direction==='entry'?'51K-246.80':'59A-123.45'}</text><path d="M6 110v26h20v-9m145-17v26h-20v-9" fill="#152737"/></g><rect x="177" y="155" width="145" height="43" rx="4" fill="none" stroke="${app.ui.cameraOn?'#8bddad':'#819db4'}" stroke-width="2" stroke-dasharray="10 5"/></svg><div class="camera-result"><span>${app.ui.cameraResult?esc(app.ui.cameraResult):app.ui.cameraOn?'Camera đang chờ xe…':'Camera chưa bật'}</span><span class="badge ${app.ui.cameraOn?'success':'neutral'}">${app.ui.cameraOn?'Đang quét':'Đã dừng'}</span></div></div>`;}
  function managerOperations(){const s=app.state.sessions.find(x=>x.id===app.ui.selected);return `${head('Vận hành bãi','Nhận xe, kiểm tra phí và xử lý xe ra tại một nơi.',`<div class="segments"><button data-action="mode" data-value="manual" class="${app.ui.mode==='manual'?'active':''}">${icon('car')} Nhập tay</button><button data-action="mode" data-value="camera" class="${app.ui.mode==='camera'?'active':''}">${icon('camera')} Camera</button></div>`)}<div class="stat-strip"><span class="stat-item"><strong>${app.state.sessions.filter(s=>s.status==='active').length}</strong> xe đang gửi</span>${E.typesFor(app.state).map(t=>`<span class="stat-item"><strong>${E.available(app.state,t.id)}</strong> chỗ ${esc(t.label.toLowerCase())}</span>`).join('')}<span class="stat-item">${icon('clock').replace('<svg','<svg style="display:inline-block;width:14px;height:14px;vertical-align:middle"')} ${time(app.state.now)} · giờ demo</span></div><div class="content-grid"><section class="surface"><div class="toolbar"><h2>${app.ui.mode==='manual'?'Nhập thông tin xe':'Nhận diện tự động'}</h2><div class="segments"><button data-action="direction" data-value="entry" class="${app.ui.direction==='entry'?'active':''}">Xe vào</button><button data-action="direction" data-value="exit" class="${app.ui.direction==='exit'?'active':''}">Xe ra</button></div></div>${app.ui.mode==='camera'?`${cameraScene()}<div class="camera-controls">${btn('camera-toggle',app.ui.cameraOn?'Dừng camera':'Bật tự động',app.ui.cameraOn?'secondary':'primary')}${app.ui.cameraOn?btn('camera-simulate','Mô phỏng xe đến làn','secondary'):''}</div><p class="muted" style="font-size:12px;margin-top:16px">Demo mô phỏng nhận diện biển số và loại xe, chưa sử dụng webcam. Xe đủ điều kiện sẽ tự được ghi nhận.</p>`:`<form data-action="${app.ui.direction==='entry'?'checkin':'manager-lookup'}"><div class="field"><label for="operation-plate">${app.ui.direction==='entry'?'Biển số xe':'Biển số / mã xe / mã vé'}</label><input id="operation-plate" name="plate" placeholder="Ví dụ: 51K-246.80" required maxlength="20" autocomplete="off"></div>${app.ui.direction==='entry'?`<div class="field"><label for="operation-type">Loại xe</label><select id="operation-type" name="vehicleType">${typeOptions('car')}</select></div><div class="inline-note">Tự chọn vị trí phù hợp. Xe có thể vào mà không cần đặt trước.</div>`:''}<button class="button primary full" type="submit">${app.ui.direction==='entry'?'Ghi nhận xe vào':'Tra phí & xử lý xe ra'} ${icon('arrow')}</button></form>`}</section><section class="surface fee-panel">${s?`${summary(s)}<div class="fee-line" style="margin-top:12px"><span>Vị trí đỗ</span><span>${esc(s.slot)}</span></div>${s.status==='closed'?'<div class="receipt-success">Lượt gửi đã kết thúc. Vị trí đã được giải phóng.</div>':`<div class="form-actions">${E.quote(app.state,s).due?`${btn('open-pay','Tạo QR cho khách','primary',`data-id="${s.id}"`)}${btn('cash-pay','Thu tiền mặt','secondary',`data-id="${s.id}"`)}`:btn('checkout','Ghi nhận xe ra '+icon('arrow'),'primary full',`data-id="${s.id}"`)}</div><details class="demo-help"><summary>Xem vé của lượt này</summary><p>Mã vé mẫu: <strong>${esc(s.ticket)}</strong></p><p>Khách dùng mã này để tra phí nếu xe chưa liên kết.</p></details>`}`:`<div class="section-head"><h2>Thông tin lượt gửi</h2></div><div class="empty">${icon('ticket')}Nhập biển số hoặc chọn một xe bên dưới.<br>Phí và thao tác thanh toán sẽ hiện tại đây.</div>`}</section></div>${activeTable()}`;}
  function help(){return `<details class="demo-help"><summary>Cách thử nhanh & đối chiếu đề tài</summary><p>1. Manager: vào Khách & vé để thử vé tháng. 2. Vận hành: nhận xe → xem phí → thu tiền → trả xe. 3. Lịch sử và Báo cáo: đối chiếu dữ liệu vừa tạo, sinh AI theo ngày/tuần.</p><div class="demo-tools">${btn('demo-guide','Đối chiếu yêu cầu đề tài','secondary small')}${btn('sample-owned','Khách: thử xe đã liên kết','secondary small')}${btn('sample-ticket','Khách: thử vé VE-4096','secondary small')}${btn('advance','Tăng thời gian thêm 1 giờ','secondary small')}${btn('auth-quick','Thử quyền Nhân viên','quiet small','data-role="staff"')}${btn('reset','Làm lại dữ liệu mẫu','quiet small')}</div><p>Đồng hồ demo: ${date(app.state.now)}/2026, ${time(app.state.now)}. Tải lại trang sẽ khôi phục dữ liệu mẫu. AI/camera/thanh toán mô phỏng.</p></details>`;}

  function render(){
    const u=app.ui,current=app.users.find(user=>user.id===u.userId);
    if(!u.loggedIn||!current?.active){u.loggedIn=false;document.getElementById('app').innerHTML=window.DemoAuth.render(app);return;}
    u.role=current.role;
    if(u.tab!=='profile'&&!navigation[u.role]?.some(item=>item[0]===u.tab))u.tab=navigation[u.role][0][0];
    const nav=navigation[u.role].map(([id,i,label])=>`${u.role==='admin'&&id==='accounts'?'<div class="nav-label admin-section-label">QUẢN TRỊ</div>':''}<button class="nav-item ${u.tab===id?'active':''}" data-action="nav" data-tab="${id}" ${u.tab===id?'aria-current="page"':''}>${icon(i)}${label}</button>`).join('');
    const content=u.tab==='profile'?window.DemoAuth.profile(app):u.role==='customer'?({fees:customerFees,booking:customerBooking,tickets:customerTickets,support:customerSupport}[u.tab]||customerFees)():({overview:()=>window.DemoReports.overview(app),operations:managerOperations,lot:()=>window.DemoCore.lot(app),customers:()=>window.DemoCore.customers(app),history:()=>window.DemoCore.history(app),finance:()=>window.DemoReports.revenue(app),catalog:()=>window.DemoCore.catalog(app)}[u.tab]||(()=>window.AdminDemo.render(app)))();
    document.getElementById('app').innerHTML=`<header class="topbar"><div class="brand"><svg class="brand-mark" viewBox="0 0 38 40" aria-hidden="true"><rect x="1" y="2" width="35" height="35" rx="10" fill="#1767bd"/><path d="M13 28V11h8a6 6 0 0 1 0 12h-8m0-8h8a2 2 0 0 1 0 4h-8" stroke="white" stroke-width="2.5" fill="none"/></svg><span>ParkingAI<small>Một bãi xe. Mọi thứ rõ ràng.</small></span></div><div class="role-switch" role="group" aria-label="Chọn tác nhân để xem demo">${['customer','manager','admin'].map(role=>`<button data-action="role" data-role="${role}" class="${role===u.role?'active':''}" aria-pressed="${role===u.role}">${icon({customer:'user',manager:'car',admin:'shield'}[role])}${names[role]}</button>`).join('')}</div><div class="top-actions"><button class="icon-button" data-action="auth-profile" aria-label="Tài khoản của tôi">${icon('user')}</button><button class="icon-button" data-action="auth-logout" aria-label="Đăng xuất">${icon('logout')}</button></div></header><div class="demo-banner">Bản xem trước · Dữ liệu mẫu · AI, camera và thanh toán mô phỏng${u.role==='staff'?' · Đang thử quyền Nhân viên':''}</div>${u.role==='customer'?`<nav class="customer-nav" aria-label="Menu khách hàng">${nav}</nav>`:''}<div class="app-shell ${u.role==='customer'?'customer':'internal'}">${u.role!=='customer'?`<aside class="sidebar"><div class="nav-label">${u.role==='admin'?'ĐIỀU HÀNH BÃI':'BÃI TRUNG TÂM'}</div>${nav}<div class="sidebar-bottom"><span class="badge success">Bãi đang hoạt động</span><div class="profile-row"><div class="account-avatar">${esc(current.name.slice(0,1))}</div><div>${esc(current.name)}<br><span>${names[u.role]} · tài khoản mẫu</span></div></div></div></aside>`:''}<main class="main ${u.role==='customer'?'customer-main':''}" id="main-content">${content}${help()}<p class="footer-note">${esc(app.settings.name)} · ${esc(app.settings.hours)}<br>Demo để duyệt giao diện và luồng thao tác trước khi triển khai.</p></main></div><div id="chat-mount">${window.DemoChat.render(app)}</div>`;
  }

  function chooseRole(role,userId){
    const user=app.users.find(row=>(userId?row.id===userId:row.role===role)&&row.active);
    if(!user||!navigation[user.role])return notify('Tài khoản mẫu của vai trò này đang bị khóa.');
    clearTimeout(cameraTimer);closeModal();
    app.ui.cameraOn=false;app.ui.loggedIn=true;app.ui.userId=user.id;app.ui.role=user.role;app.ui.tab=navigation[user.role][0][0];app.ui.selected=null;
    location.hash=user.role;render();window.scrollTo(0,0);
  }
  function exitSession(){
    clearTimeout(cameraTimer);closeModal();app.state.audit.unshift({at:app.state.now,text:'Đăng xuất tài khoản mẫu.'});
    app.ui.cameraOn=false;app.ui.loggedIn=false;app.ui.userId=null;app.ui.loginError=null;location.hash='';render();window.scrollTo(0,0);
  }

  function selectSession(id){app.ui.selected=id;render();}
  function qr(){let cells='';for(let y=0;y<25;y++)for(let x=0;x<25;x++){const finder=(ox,oy)=>x>=ox&&x<ox+7&&y>=oy&&y<oy+7&&(x===ox||x===ox+6||y===oy||y===oy+6||(x>=ox+2&&x<=ox+4&&y>=oy+2&&y<=oy+4));const reserved=(x<8&&y<8)||(x>16&&y<8)||(x<8&&y>16);if(finder(0,0)||finder(18,0)||finder(0,18)||(!reserved&&(x*7+y*13+x*y)%5<2))cells+=`<rect x="${x}" y="${y}" width="1" height="1"/>`;}return `<svg class="qr-demo" viewBox="-2 -2 29 29" role="img" aria-label="Hình QR minh họa, không dùng để chuyển tiền"><rect x="-2" y="-2" width="29" height="29" fill="white"/><g fill="#193552">${cells}</g></svg>`;}
  function showModal(title,body){modalReturnFocus=document.activeElement;document.getElementById('modal-root').innerHTML=`<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-header"><h2 id="modal-title">${title}</h2><button class="icon-button" data-action="close-modal" aria-label="Đóng">${icon('close')}</button></div><div class="modal-body">${body}</div></section></div>`;document.body.style.overflow='hidden';document.querySelector('.modal button')?.focus();}
  function closeModal(){document.getElementById('modal-root').innerHTML='';document.body.style.overflow='';app.ui.modal=null;if(modalReturnFocus?.isConnected)modalReturnFocus.focus();}
  function openPay(id,method='online'){const s=app.state.sessions.find(x=>x.id===id);if(!s||s.status!=='active'||(app.ui.role==='customer'&&!canRead(s)))return notify('Bạn chưa có quyền thanh toán lượt này.');app.ui.modal={id,method};const q=E.quote(app.state,s);showModal(method==='cash'?'Xác nhận thu tiền mặt':'Thanh toán phí gửi xe',`<div class="fee-line"><span>Biển số / mã xe</span><strong class="plate">${esc(s.plate)}</strong></div><div class="fee-total" style="text-align:center;font-size:34px;margin:18px 0">${money(q.due)}</div>${method==='online'?qr():''}<p class="qr-label">${method==='online'?'QR minh họa · Không chuyển tiền thật':'Thao tác thử · Không ghi nhận tiền thật'}</p><div class="inline-note">${method==='online'?'Bấm nút bên dưới để mô phỏng kết quả thanh toán thành công.':'Trong ứng dụng thật, chỉ xác nhận sau khi đã nhận tiền của khách.'}</div><button class="button primary full" data-action="confirm-pay">${method==='online'?'Mô phỏng thanh toán thành công':'Xác nhận đã thu · Demo'}</button>`);}
  function autoExit(id){const s=app.state.sessions.find(x=>x.id===id);if(['admin','manager','staff'].includes(app.ui.role)&&app.ui.mode==='camera'&&app.ui.cameraOn&&app.ui.direction==='exit'&&s?.status==='active'&&E.quote(app.state,s).due===0){const r=dispatch({type:'checkout',sessionId:id});app.ui.cameraResult=r.ok?`${s.plate} · Đã tự ghi nhận xe ra`:r.message;render();}}
  function simulateCamera(){if(!app.ui.cameraOn)return;app.ui.cameraResult='Đang nhận diện biển số và loại xe…';render();clearTimeout(cameraTimer);cameraTimer=setTimeout(()=>{if(!app.ui.cameraOn)return;if(app.ui.direction==='entry'){let plate='51K-246.80';if(app.state.sessions.some(s=>E.normalize(s.plate)===E.normalize(plate)&&s.status==='active')){app.ui.cameraResult=plate+' · Xe đã được ghi nhận';render();return;}const r=dispatch({type:'checkin',plate,vehicleType:'car',source:'camera'});if(r.ok)app.ui.selected=r.sessionId;app.ui.cameraResult=r.ok?plate+' · Ô tô · Đã tự ghi nhận vào':r.message;render();}else{const s=app.state.sessions.find(s=>E.normalize(s.plate)===E.normalize('59A-123.45')&&s.status==='active');if(!s){app.ui.cameraResult='59A-123.45 · Không có lượt đang gửi';render();return;}app.ui.selected=s.id;const q=E.quote(app.state,s);app.ui.cameraResult=q.due?`${s.plate} · Chờ thanh toán ${money(q.due)}`:`${s.plate} · Đã thanh toán`;render();autoExit(s.id);}},1000);}
  document.addEventListener('change',event=>{
    if(event.target.id==='slot-type'){app.ui.slotType=event.target.value;document.getElementById('slot-code').value=E.nextSlotCode(app.state,event.target.value);return;}
    const map={'customer-type':['customer-plate','Mã xe / mã vé'], 'book-type':['book-plate','Mã xe (nếu có)'], 'operation-type':['operation-plate','Mã xe (nếu có)']};
    const pair=map[event.target.id];if(!pair)return;
    const unplated=E.typeInfo(event.target.value,app.state)?.requiresPlate===false;
    const input=document.getElementById(pair[0]);if(!input)return;
    document.querySelector(`label[for="${pair[0]}"]`).textContent=unplated?pair[1]:'Biển số xe';
    input.required=event.target.id==='customer-type'||!unplated;
    input.placeholder=unplated?(event.target.id==='customer-type'?'Ví dụ: XD-001 hoặc mã trên vé':'Để trống để hệ thống cấp mã xe'):'Ví dụ: 59A-123.45';
  });
  function allowed(action){
    if(action==='demo-guide'||action==='close-modal'||action.startsWith('auth-'))return true;
    if(!app.ui.loggedIn)return false;
    if(action.startsWith('admin-'))return app.ui.role==='admin';
    if(['checkin','manager-lookup','select-session','checkout','mode','direction','camera-toggle','camera-simulate','cash-pay'].includes(action))return ['admin','manager','staff'].includes(app.ui.role);
    if(['reserve','cancel-booking','claim'].includes(action))return app.ui.role==='customer';
    return true;
  }
  document.addEventListener('submit',event=>{
    const form=event.target.closest('form[data-action]');if(!form)return;event.preventDefault();
    const d=new FormData(form),action=form.dataset.action;
    if(!allowed(action))return notify('Vai trò hiện tại không có quyền thao tác này.');
    if(action.startsWith('auth-'))return window.DemoAuth.handle(app,action,d);
    if(action.startsWith('core-'))return window.DemoCore.handle(app,action,d);
    if(action.startsWith('chat-'))return window.DemoChat.handle(app,action,d);
    if(action.startsWith('report-'))return window.DemoReports.handle(app,action,d);
    if(action.startsWith('admin-')||action.startsWith('catalog-'))return window.AdminDemo.handle(app,action,d);
    if(action==='customer-lookup'){app.ui.plate=String(d.get('plate')).trim().toUpperCase();app.ui.vehicleType=d.get('vehicleType');app.ui.searched=true;render();}
    else if(action==='claim')dispatch({type:'claim',plate:app.ui.plate,vehicleType:app.ui.vehicleType,ticket:String(d.get('ticket')).trim().toUpperCase()});
    else if(action==='reserve')dispatch({type:'reserve',plate:d.get('plate'),vehicleType:d.get('vehicleType'),start:new Date(d.get('start')+'+07:00').toISOString(),end:new Date(d.get('end')+'+07:00').toISOString()});
    else if(action==='checkin'){
      const r=E.apply(app.state,{type:'checkin',role:app.ui.role,plate:d.get('plate'),vehicleType:d.get('vehicleType'),source:'manual'});
      if(r.ok){app.state=r.state;app.ui.selected=r.sessionId;render();}notify(r.message);
    }else if(action==='manager-lookup'){
      const s=app.state.sessions.find(s=>s.status==='active'&&(E.normalize(s.plate)===E.normalize(d.get('plate'))||E.normalize(s.ticket)===E.normalize(d.get('plate'))));
      if(s)selectSession(s.id);else notify('Không tìm thấy lượt đang gửi. Xem Lịch sử để tra toàn bộ lượt.');
    }else if(action==='support')dispatch({type:'support',subject:d.get('subject'),message:d.get('message')});
  });
  document.addEventListener('click',event=>{
    const b=event.target.closest('[data-action]');if(!b||b.closest('form')&&b.type==='submit')return;
    const a=b.dataset.action;
    if(!allowed(a))return notify('Vai trò hiện tại không có quyền thao tác này.');
    if(a==='demo-guide')return window.DemoGuide.show(app);
    if(a.startsWith('auth-'))return window.DemoAuth.handle(app,a,b.dataset);
    if(a.startsWith('core-'))return window.DemoCore.handle(app,a,b.dataset);
    if(a.startsWith('chat-'))return window.DemoChat.handle(app,a,b.dataset);
    if(a.startsWith('report-'))return window.DemoReports.handle(app,a,b.dataset);
    if(a.startsWith('admin-')||a.startsWith('catalog-'))return window.AdminDemo.handle(app,a,b.dataset);
    if(a==='role')return chooseRole(b.dataset.role);
    if(a==='nav'||a==='open-tab'){
      if(navigation[app.ui.role].some(n=>n[0]===b.dataset.tab)){app.ui.tab=b.dataset.tab;render();window.scrollTo(0,0);}return;
    }
    if(a==='reset'){
      const role=app.ui.role;window.DemoChat.reset();clearTimeout(cameraTimer);app.state=E.seed();app.users=seedUsers();
      app.settings={name:'ParkingAI · Bãi trung tâm',hours:'00:00 – 24:00'};
      app.ui={role,loggedIn:true,userId:app.users.find(u=>u.role===role).id,tab:navigation[role][0][0],plate:'59A-123.45',vehicleType:'car',searched:false,mode:'manual',direction:'entry',selected:null,modal:null,cameraOn:false,cameraResult:null};
      closeModal();render();notify('Đã khôi phục dữ liệu mẫu.');
    }else if(a==='goto-booking'){app.ui.tab='booking';render();window.scrollTo(0,0);}
    else if(a==='sample-owned'||a==='sample-ticket'||a==='sample-bicycle'){
      chooseRole('customer');app.ui.plate=a==='sample-owned'?'59A-123.45':a==='sample-bicycle'?'XD-001':'59B1-678.90';app.ui.vehicleType=a==='sample-owned'?'car':a==='sample-bicycle'?'bicycle':'motorbike';app.ui.searched=true;render();
    }else if(a==='cancel-booking')dispatch({type:'cancel-reservation',id:b.dataset.id});
    else if(a==='mode'){clearTimeout(cameraTimer);app.ui.mode=b.dataset.value;app.ui.cameraOn=false;app.ui.cameraResult=null;render();}
    else if(a==='direction'){clearTimeout(cameraTimer);app.ui.direction=b.dataset.value;app.ui.cameraResult=null;render();}
    else if(a==='select-session')selectSession(b.dataset.id);
    else if(a==='open-pay'||a==='cash-pay')openPay(b.dataset.id,a==='cash-pay'?'cash':'online');
    else if(a==='close-modal')closeModal();
    else if(a==='confirm-pay'){
      const modal=app.ui.modal;if(!modal)return;const role=app.ui.role,previous=new Set(app.state.transactions.map(t=>t.id));
      const r=E.apply(app.state,{type:'pay',role,sessionId:modal.id,method:modal.method});
      if(r.ok){app.state=r.state;if(role==='customer')app.ui.customerPayments=[...(app.ui.customerPayments||[]),...r.state.transactions.filter(t=>!previous.has(t.id)).map(t=>t.id)];}
      closeModal();render();notify(r.message);if(r.ok)autoExit(modal.id);
    }else if(a==='checkout')dispatch({type:'checkout',sessionId:b.dataset.id});
    else if(a==='camera-toggle'){clearTimeout(cameraTimer);app.ui.cameraOn=!app.ui.cameraOn;app.ui.cameraResult=null;render();}
    else if(a==='camera-simulate')simulateCamera();
    else if(a==='advance')dispatch({type:'advance',minutes:60});
  });
  document.addEventListener('keydown',event=>{const modal=document.querySelector('.modal');if(!modal)return;if(event.key==='Escape')closeModal();if(event.key==='Tab'){const nodes=[...modal.querySelectorAll('button,input,select,textarea,a[href]')].filter(x=>!x.disabled);const first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});
  render();
})();
