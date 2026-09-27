(async () => {
  const source = await (await fetch('/src/pages/Expansion/CustomerPortal.jsx')).text();
  const mainSource = await (await fetch('/src/main.jsx')).text();
  const dependency = (text, name) => text.match(new RegExp('["\']([^"\']*/deps/' + name + '\\.js[^"\']*)["\']'))[1];
  const ReactModule = await import(dependency(source, 'react'));
  const React = ReactModule.default || ReactModule;
  const DomModule = await import(dependency(mainSource, 'react-dom_client'));
  const { createRoot } = DomModule.default || DomModule;
  const { MemoryRouter } = await import(dependency(source, 'react-router-dom'));
  const { default: Portal } = await import('/src/pages/Expansion/CustomerPortal.jsx');
  const { default: Panel } = await import('/src/pages/Expansion/CustomerSupportPanel.jsx');
  const { default: api } = await import('/src/services/api.js');
  const tick = () => new Promise(r => setTimeout(r, 30));
  const wait = async (condition) => { for (let n = 0; n < 100 && !condition(); n++) await tick(); };
  const checks = []; let posted;
  window.__PARKINGAI_CONFIG__ = { SINGLE_SITE_ID: 2 };
  api.defaults.adapter = async config => {
    await tick(); let data = [];
    if (config.url.endsWith('/sites')) data = [{ id: 1, name: 'Bãi lịch sử' }, { id: 2, name: 'Bãi đang dùng' }, { id: 3, name: 'Bãi khác' }];
    else if (config.url.endsWith('/profile')) data = { linked: true };
    else if (config.method === 'post' && config.url.endsWith('/support-requests')) {
      posted = JSON.parse(config.data);
      if (!posted.site_id) throw Object.assign(new Error('missing site'), { config, response: { status: 422, data: { detail: 'Hãy chọn bãi xe cần hỗ trợ.' } } });
      data = { id: 'fixture-support', status: 'open', messages: [] };
    } else if (config.url.endsWith('/fixture-support')) data = { id: 'fixture-support', status: 'open', messages: [] };
    return { data, status: 200, statusText: 'OK', headers: {}, config };
  };
  document.getElementById('root').style.display = 'none';
  const host = document.createElement('main'); host.className = 'prototype-ui'; host.style.padding = '20px'; document.body.appendChild(host);
  const change = async (field, value) => {
    Object.getOwnPropertyDescriptor(field.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true })); await tick();
  };
  let root;
  for (const detailed of [false, true]) {
    root = createRoot(host);
    root.render(React.createElement(MemoryRouter, { initialEntries: ['/portal?tab=support'] }, React.createElement(detailed ? Panel : Portal, { linked: true, refunds: { data: [], loading: false, reload: async () => {} } })));
    await wait(() => host.querySelector('textarea'));
    if (detailed) await change(host.querySelector('input'), 'Không tìm được lượt gửi');
    await change(host.querySelector('textarea'), 'Xin kiểm tra lượt gửi tại bãi đang dùng.');
    await wait(() => !host.querySelector('button[type=submit]').disabled);
    posted = null; host.querySelector('button[type=submit]').click(); await wait(() => posted);
    checks.push({ name: (detailed ? 'detailed' : 'overview') + ' unlinked support routes to configured site', passed: posted?.site_id === 2, actual_site: posted?.site_id || null });
    await tick(); root.unmount();
  }
  root = createRoot(host);
  root.render(React.createElement(MemoryRouter, { initialEntries: ['/portal?tab=support'] }, React.createElement(Portal)));
  await wait(() => host.querySelector('textarea'));
  return { checks };
})()
