(async () => {
  const source = await (await fetch('/src/pages/Expansion/CustomerFees.jsx')).text();
  const main = await (await fetch('/src/main.jsx')).text();
  const dependency = (text, name) => text.match(new RegExp('["\']([^"\']*/deps/' + name + '\\.js[^"\']*)["\']'))[1];
  const ReactModule = await import(dependency(source, 'react'));
  const React = ReactModule.default || ReactModule;
  const DomModule = await import(dependency(main, 'react-dom_client'));
  const { createRoot } = DomModule.default || DomModule;
  const { MemoryRouter } = await import(dependency(source, 'react-router-dom'));
  const { default: CustomerFees } = await import('/src/pages/Expansion/CustomerFees.jsx');
  const { default: SitesWorkspace } = await import('/src/pages/Expansion/SitesWorkspace.jsx');
  const { AuthContext } = await import('/src/context/AuthContext.jsx');
  const { default: api } = await import('/src/services/api.js');
  const delay = () => new Promise(resolve => setTimeout(resolve, 30));
  const checks = [], requests = [];
  const check = (name, passed) => checks.push({ name, passed: !!passed });
  const wait = async (condition) => { for (let n = 0; n < 100 && !condition(); n++) await delay(); };
  window.__PARKINGAI_CONFIG__ = { SINGLE_SITE_ID: 2 };
  let manager = false, failedSites = false;
  api.defaults.adapter = async config => {
    await delay();
    let data = [];
    if (config.url.endsWith('/sites')) {
      requests.push('sites');
      if (failedSites) throw Object.assign(new Error('fixture site outage'), { config, response: { status: 503, data: { detail: 'Bãi tạm thời chưa tải được.' } } });
      data = manager ? [] : [{ id: 2, name: 'Bãi kiểm thử', role: 'customer' }];
    } else if (config.url.endsWith('/vehicle-types')) data = [{ id: 1, name: 'Xe máy', is_active: true }, { id: 2, name: 'Ô tô', is_active: true }];
    else if (config.url.endsWith('/availability')) data = { slots: [{ id: 1, vehicle_type_id: 2, available_now: true }] };
    else if (config.url.endsWith('/fee-lookup')) {
      const body = JSON.parse(config.data);
      requests.push(body);
      if (body.ticket_proof !== 'PAP1.fixture') throw Object.assign(new Error('fixture private lookup'), { config, response: { status: 404, data: { detail: 'Chưa xác minh được lượt gửi.' } } });
      data = { session: { id: 'fixture-stay', license_plate: '30A-123.45', vehicle_type_id: 2, status: 'active', check_in_time: '2026-09-27T08:00:00+07:00' }, access: { kind: 'ticket' }, payment_status: { session_id: 'fixture-stay', gross_fee: 20000, online_paid: 0, balance_due: 20000, server_now: '2026-09-27T09:00:00+07:00' } };
    }
    return { data, status: 200, statusText: 'OK', headers: {}, config };
  };
  document.getElementById('root').style.display = 'none';
  const host = document.createElement('main');
  host.className = 'prototype-ui'; host.style.padding = '20px'; document.body.appendChild(host);
  let root = createRoot(host);
  const render = (component, role = 'customer') => root.render(React.createElement(MemoryRouter, null, React.createElement(AuthContext.Provider, { value: { user: { role } } }, React.createElement(component))));
  const change = async (selector, value) => {
    const input = host.querySelector(selector);
    const prototype = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
    await delay();
  };
  render(CustomerFees);
  await wait(() => host.querySelector('#customer-type option[value="2"]'));
  check('customer must explicitly choose vehicle type', host.querySelector('#customer-type')?.value === '' && host.querySelector('button[type=submit]')?.disabled);
  check('completed stays have a history link', !!host.querySelector('a[href="/portal?tab=tickets"]'));
  await change('#customer-plate', '30a12345'); await change('#customer-type', '2');
  host.querySelector('button[type=submit]').click();
  await wait(() => host.querySelector('#ticket'));
  check('private 404 offers ticket proof and type guidance', host.innerText.includes('Kiểm tra lại biển số và loại xe') && !!host.querySelector('#ticket'));
  check('lookup submits chosen type and compact plate', requests.some(r => r?.vehicle_type_id === 2 && r.license_plate === '30A12345' && r.site_id === 2));
  await change('#ticket', 'PAP1.fixture'); host.querySelector('#ticket').closest('form').querySelector('button').click();
  await wait(() => host.querySelector('.fee-total'));
  check('valid ticket renders actual balance and duration', host.querySelector('.fee-total')?.textContent.includes('20.000') && host.innerText.includes('1 giờ 0 phút'));
  await change('#customer-plate', '30A99999');
  check('editing query clears previous vehicle balance', !host.querySelector('.fee-total'));
  root.unmount(); root = createRoot(host); manager = true; render(SitesWorkspace, 'manager');
  await wait(() => host.innerText.includes('Tài khoản chưa được cấp quyền'));
  check('unassigned manager has precise recovery instructions', host.innerText.includes('Công cụ vận hành khác') && host.innerText.includes('Nhân sự được phân công'));
  const before = requests.filter(r => r === 'sites').length;
  [...host.querySelectorAll('button')].find(b => b.textContent === 'Làm mới').click();
  await wait(() => requests.filter(r => r === 'sites').length > before);
  check('manager can reload assigned sites', requests.filter(r => r === 'sites').length > before);
  failedSites = true;
  [...host.querySelectorAll('button')].find(b => b.textContent === 'Làm mới')?.click();
  await wait(() => host.innerText.includes('Bãi tạm thời chưa tải được.'));
  check('site network error is not reported as missing membership', host.innerText.includes('Bãi tạm thời chưa tải được.') && !host.innerText.includes('Tài khoản chưa được cấp quyền'));
  root.unmount(); root = createRoot(host); manager = false; failedSites = false; render(CustomerFees);
  await wait(() => host.querySelector('#customer-type option[value="2"]'));
  return { checks };
})()
