(async () => {
  const source = await (await fetch('/src/pages/Expansion/OperationsPanel.jsx')).text();
  const mainSource = await (await fetch('/src/main.jsx')).text();
  const dependency = (text, name) => text.match(new RegExp('["\']([^"\']*/deps/' + name + '\\.js[^"\']*)["\']'))[1];
  const ReactModule = await import(dependency(source, 'react'));
  const React = ReactModule.default || ReactModule;
  const DomModule = await import(dependency(mainSource, 'react-dom_client'));
  const { createRoot } = DomModule.default || DomModule;
  const { default: OperationsPanel } = await import('/src/pages/Expansion/OperationsPanel.jsx');
  const { default: api } = await import('/src/services/api.js');
  const wait = async (condition) => { for (let n = 0; n < 100 && !condition(); n++) await new Promise(r => setTimeout(r, 20)); };
  const tick = () => new Promise(r => setTimeout(r, 30));
  const checks = [];
  const A = { id: 'stay-A', license_plate: '30A-123.45', status: 'active', vehicle_type_id: 1, check_in_time: '2026-09-27T08:00:00+07:00' };
  const B = { ...A, id: 'stay-B', license_plate: '30B-678.90' };
  const types = { data: [{ id: 1, name: 'Xe máy' }] };
  const availability = { data: { slots: [], occupied: 2 } };
  const sessions = { data: [B] };
  const adapters = { loadQuote: async () => null };
  let finish, started;
  api.defaults.adapter = async config => {
    started = true;
    await new Promise(resolve => { finish = resolve; });
    return { data: [A], status: 200, statusText: 'OK', headers: {}, config };
  };
  document.getElementById('root').style.display = 'none';
  const host = document.createElement('main'); host.className = 'prototype-ui'; host.style.padding = '20px'; document.body.appendChild(host);
  const Harness = () => {
    const [selected, onSelect] = React.useState(null);
    return React.createElement(OperationsPanel, { site: { id: 2, role: 'manager' }, availability, vehicleTypes: types, sessions,
      page: { page: 0, size: 25 }, action: { busy: false }, adapters, selected, onSelect,
      onCheckout: () => {}, onDetail: () => {}, onTicket: () => {}, onRefresh: () => {}, initialAction: 'checkout_lookup' });
  };
  const changeQuery = async value => {
    const field = host.querySelector('#operation-query');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true })); await tick();
  };
  for (const scenario of ['select another vehicle', 'edit search', 'switch lookup type']) {
    const root = createRoot(host); root.render(React.createElement(Harness));
    await wait(() => host.querySelector('#operation-query'));
    await changeQuery(A.license_plate);
    started = false;
    host.querySelector('button[type=submit]').click(); await wait(() => started);
    if (scenario === 'select another vehicle') host.querySelector('.data-table button').click();
    else if (scenario === 'edit search') await changeQuery(B.license_plate);
    else [...host.querySelectorAll('button')].find(b => b.textContent === 'Tra bằng mã vé').click();
    await tick(); finish();
    await wait(() => !host.querySelector('button[type=submit]').disabled);
    await tick();
    const selected = host.querySelector('.fee-panel .plate')?.textContent || null;
    checks.push({ name: 'late response after ' + scenario, passed: selected === (scenario === 'select another vehicle' ? B.license_plate : null), actual: selected });
    root.unmount();
  }
  const root = createRoot(host); root.render(React.createElement(Harness));
  await wait(() => host.querySelector('#operation-query'));
  await changeQuery(A.license_plate); started = false;
  host.querySelector('button[type=submit]').click(); await wait(() => started); finish();
  await wait(() => !!host.querySelector('.fee-panel .plate'));
  checks.push({ name: 'unchanged lookup selects matching stay', passed: host.querySelector('.fee-panel .plate')?.textContent === A.license_plate });
  return { checks };
})()
