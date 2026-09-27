(async () => {
  const source = await (await fetch('/src/pages/Expansion/CustomerFees.jsx')).text();
  const mainSource = await (await fetch('/src/main.jsx')).text();
  const dependency = (text, name) => text.match(new RegExp('["\']([^"\']*/deps/' + name + '\\.js[^"\']*)["\']'))[1];
  const ReactModule = await import(dependency(source, 'react'));
  const React = ReactModule.default || ReactModule;
  const DomModule = await import(dependency(mainSource, 'react-dom_client'));
  const { createRoot } = DomModule.default || DomModule;
  const { MemoryRouter } = await import(dependency(source, 'react-router-dom'));
  const { default: OperationsPanel } = await import('/src/pages/Expansion/OperationsPanel.jsx');
  const { default: api } = await import('/src/services/api.js');
  const tick = () => new Promise(resolve => setTimeout(resolve, 30));
  const wait = async condition => {
    for (let n = 0; n < 100 && !condition(); n++) await tick();
    if (!condition()) throw Error('Camera fixture timeout');
  };
  let finish, posted;
  const checks = [];
  const observation = { id: 'review-observation', camera_id: 1, suggested_plate: '30A12345', review_status: 'pending',
    ocr_status: 'recognized', captured_at: '2026-09-27T10:00:00+07:00', observed_at: '2026-09-27T10:00:00+07:00', detections: [] };
  api.defaults.adapter = async config => {
    let data = {};
    if (config.url.endsWith('/cameras')) data = [
      { id: 1, name: 'Entry camera', direction: 'entry', is_active: true },
      { id: 2, name: 'Exit camera', direction: 'exit', is_active: true },
      { id: 3, name: 'Other entry camera', direction: 'entry', is_active: true },
    ];
    else if (config.url.endsWith('/automation')) data = { enabled: false, minimum_confidence: .97, max_age_seconds: 15 };
    else if (config.url.endsWith('/vision/observations')) data = { items: [observation] };
    else if (config.url.endsWith('/review')) { posted = true; data = await new Promise(resolve => { finish = resolve; }); }
    else if (config.url.endsWith('/image')) data = new Blob(['fixture'], { type: 'image/png' });
    return { data, status: 200, statusText: 'OK', headers: {}, config };
  };
  document.getElementById('root').style.display = 'none';
  const host = document.createElement('main'); host.className = 'prototype-ui'; host.style.padding = '20px'; document.body.appendChild(host);
  const remote = data => ({ data, loading: false, error: '', reload: async () => {} });
  const button = text => [...host.querySelectorAll('button')].find(b => b.textContent.trim() === text);
  const state = () => ({ lane: host.querySelector('[aria-label="Hướng xe"] .active')?.textContent,
    mode: host.querySelector('[aria-label="Cách nhận xe"] .active')?.textContent,
    plate: host.querySelector('#operation-plate')?.value || '' });
  for (const scenario of ['switch lane', 'switch mode', 'unchanged camera']) {
    const root = createRoot(host);
    root.render(React.createElement(MemoryRouter, null, React.createElement(OperationsPanel, {
      site: { id: 2, role: 'manager' }, availability: remote({ occupied: 0, slots: [] }),
      vehicleTypes: remote([{ id: 1, name: 'Ô tô' }]), sessions: remote([]), page: { page: 0, size: 25 },
      action: { busy: false }, adapters: { loadQuote: async () => null }, selected: null, onSelect: () => {},
      onCheckout: () => {}, onDetail: () => {}, onTicket: () => {}, onReservations: () => {}, onRefresh: async () => {},
    })));
    await wait(() => button('Camera')); button('Camera').click();
    await wait(() => host.querySelector('#camera-recent-frame option[value="review-observation"]'));
    const choice = host.querySelector('#camera-recent-frame');
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(choice, observation.id);
    choice.dispatchEvent(new Event('change', { bubbles: true }));
    await wait(() => button('Dùng biển số & kiểm tra thủ công'));
    posted = false; button('Dùng biển số & kiểm tra thủ công').click(); await wait(() => posted); await tick();
    if (scenario === 'switch lane') {
      checks.push({ name: 'pending review locks in-place camera, frame, plate and upload controls',
        passed: ['#operation-camera', '#camera-recent-frame', '#camera-confirmed-plate', 'input[type=file]'].every(selector => host.querySelector(selector)?.disabled)
          && button('Bật tự động').disabled });
      button('Xe ra').click(); await wait(() => host.querySelector('.camera-label')?.textContent.includes('Exit camera'));
    } else if (scenario === 'switch mode') {
      button('Nhập tay').click(); await wait(() => host.querySelector('#operation-plate'));
    }
    finish({ ...observation, review_status: 'accepted', confirmed_plate: '30A12345' });
    await tick(); await tick();
    const actual = state();
    const expected = scenario === 'switch lane' ? { lane: 'Xe ra', mode: 'Camera', plate: '' }
      : { lane: 'Xe vào', mode: 'Nhập tay', plate: scenario === 'unchanged camera' ? '30A12345' : '' };
    checks.push({ name: 'review response after ' + scenario, passed: JSON.stringify(actual) === JSON.stringify(expected), actual });
    if (scenario !== 'unchanged camera') root.unmount();
  }
  return { checks };
})()
