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
  const { ExpansionProvider } = await import('/src/context/ExpansionContext.jsx');
  const { AuthContext } = await import('/src/context/AuthContext.jsx');
  const { default: api } = await import('/src/services/api.js');
  const tick = () => new Promise(resolve => setTimeout(resolve, 25));
  const wait = async (condition, label) => {
    for (let n = 0; n < 120; n++) { if (condition()) return; await tick(); }
    throw new Error('Lookup regression timed out: ' + label);
  };
  const checks = [], requests = [];
  const check = (name, passed, actual) => checks.push({ name, passed: Boolean(passed), ...(actual === undefined ? {} : { actual }) });
  const failure = (config, status, detail) => Object.assign(new Error(detail), { config, response: { status, data: { detail } } });
  const stay = { id: 'lookup-refresh-stay', license_plate: '30A-999.99', vehicle_type_id: 1, check_in_time: '2026-10-02T13:13:18+07:00', status: 'active' };
  const other = { ...stay, id: 'other-stay', license_plate: '30B-888.88' };
  // The completed/cash shape is the contract observed from actual isolated
  // FastAPI checkout + payment-status: balance_due remains the cashier share,
  // even though the cash receipt has settled it. It is not outstanding debt.
  // payOS is enabled for this lot (CL-ONLINE #79 hides "Thanh toán online" when it
  // is not); can_quote stays false so no QR quote can be requested by the fixture.
  const activeBalance = { session_id: stay.id, session_status: 'active', enabled: true, supported: true,
    gross_fee: 50000, online_paid: 0, balance_due: 50000, paid_through: null,
    server_now: '2026-10-02T14:23:18+07:00', latest_quote: null, can_quote: false, message: null };
  const completedBalance = { ...activeBalance, session_status: 'completed',
    message: 'Lượt gửi đã kết thúc. Số liệu bên dưới là phí và các khoản thanh toán của lượt này.' };
  window.__PARKINGAI_CONFIG__ = { SINGLE_SITE_ID: 2 };
  document.getElementById('root').style.display = 'none';
  const host = document.createElement('main'); host.className = 'prototype-ui'; host.style.padding = '20px'; document.body.appendChild(host);
  let root;
  const mount = (Component, role) => {
    root?.unmount();
    localStorage.setItem('token', 'isolated-fixture-token');
    root = createRoot(host);
    root.render(React.createElement(MemoryRouter, null,
      React.createElement(AuthContext.Provider, { value: { user: { role } } },
        React.createElement(ExpansionProvider, null, React.createElement(Component)))));
  };
  const change = async (selector, value) => {
    const input = host.querySelector(selector);
    const prototype = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
    await tick();
  };
  const button = (label, scope = host) => [...scope.querySelectorAll('button')].find(node => node.textContent === label);
  const click = (label, scope = host) => {
    const node = button(label, scope);
    if (!node || node.disabled) throw new Error('Expected enabled control: ' + label);
    node.click();
  };
  const fee = () => host.querySelector('.fee-panel');
  const paymentActions = () => [...(fee()?.querySelectorAll('button') || [])].filter(node =>
    !node.disabled && /Thanh toán online|Tạo QR cho khách|Thu tiền mặt|Chuyển khoản|Ghi nhận xe ra|Kiểm tra phí & xe ra/.test(node.textContent));
  const common = (config, role) => {
    if (config.url.endsWith('/capabilities')) return { site_analytics_enabled: true, sites_enabled: true };
    if (config.url.endsWith('/sites')) return [{ id: 2, name: 'Bãi kiểm thử', role }];
    if (config.url.endsWith('/vehicle-types')) return [{ id: 1, name: 'Ô tô', is_active: true }];
    return [];
  };
  let phase, statusReads, statusResponse, rejectStatus, holdStatus, releaseStatus;
  const customerAdapter = async config => {
    await tick(); requests.push({ phase, method: config.method, url: config.url });
    let data = common(config, 'customer');
    // The site serves vehicle type 1 (review 05/10 #78 offers only served types).
    if (config.url.endsWith('/availability')) data = { slots: [{ id: 1, vehicle_type_id: 1, is_occupied: true, available_now: false, reserved: false }] };
    else if (config.url.endsWith('/fee-lookup')) data = { session: { ...stay }, access: { kind: 'owned' }, payment_status: { ...activeBalance } };
    else if (config.url.endsWith('/payment-status')) {
      statusReads += 1;
      if (holdStatus && statusReads === 3) await new Promise(resolve => { releaseStatus = resolve; });
      if (rejectStatus && statusReads >= 2) throw failure(config, 503, 'Không tải được số dư hiện tại.');
      data = { ...statusResponse };
    }
    return { data, status: 200, statusText: 'OK', headers: {}, config };
  };
  const customerReady = async (balanceOnOpen = activeBalance) => {
    statusReads = 0; statusResponse = activeBalance; rejectStatus = false; holdStatus = false; releaseStatus = null;
    api.defaults.adapter = customerAdapter; mount(CustomerFees, 'customer');
    await wait(() => host.querySelector('#customer-type option[value="1"]'), 'customer types');
    await change('#customer-plate', stay.license_plate); await change('#customer-type', '1');
    host.querySelector('button[type=submit]').click();
    await wait(() => fee()?.querySelector('.fee-total')?.textContent.includes('50.000'), 'active fee lookup');
    statusResponse = balanceOnOpen;
    [...host.querySelectorAll('button')].find(node => node.textContent.includes('Thanh toán online')).click();
    await wait(() => statusReads === 1 && document.querySelector('[aria-label="Thanh toán phí lượt gửi"]')?.innerText.includes('50.000'), 'customer payment modal');
  };
  const closePayment = async (settle = true) => {
    // An invalid refresh intentionally clears the selected stay, which may
    // already close its dialog before this next user action.
    const dialog = document.querySelector('[role="dialog"]');
    if (dialog) click('Đóng', dialog);
    await tick();
    if (settle) await wait(() => !host.querySelector('#customer-plate')?.disabled, 'lookup revalidation after closing payment');
  };
  for (const state of ['completed', 'cancelled']) {
    phase = 'customer-' + state; await customerReady();
    statusResponse = state === 'completed' ? completedBalance : { ...activeBalance, session_status: 'cancelled', can_quote: false };
    click('Cập nhật số dư', document);
    await wait(() => statusReads >= 3, phase + ' summary refresh'); await tick(); await tick();
    check(phase + ' payment dialog rejects new payment', !button('Lập đề nghị thanh toán QR', document));
    await closePayment();
    const text = fee()?.innerText || '';
    check(phase + ' summary has no debt or new payment action', !text.includes('Chưa thanh toán đủ') && !text.includes('Số tiền còn phải trả') && paymentActions().length === 0, text);
    check(phase + ' state is visible rather than silently retaining active data', state === 'completed' ? text.includes('Đã thu khi ra') && text.includes('50.000') : /hủy/i.test(text), text);
    check(phase + ' does not show increasing active parking duration', !text.includes('Thời gian gửi'));
  }
  for (const state of ['completed', 'cancelled']) {
    phase = 'customer-close-without-refresh-' + state;
    await customerReady({ ...completedBalance, session_status: state });
    check(phase + ' initial modal recognizes terminal state', document.querySelector('[aria-label="Thanh toán phí lượt gửi"]')?.innerText.includes('Lượt đã kết thúc.'));
    await closePayment();
    const text = fee()?.innerText || '';
    check(phase + ' close revalidates outer summary without explicit refresh', !text.includes('Chưa thanh toán đủ') && !text.includes('Số tiền còn phải trả') && paymentActions().length === 0 && (state === 'completed' ? text.includes('Đã thu khi ra') : /hủy/i.test(text)), text);
  }
  phase = 'customer-still-active'; await customerReady();
  statusResponse = { ...activeBalance, gross_fee: 60000, online_paid: 20000, balance_due: 40000, server_now: '2026-10-02T15:23:18+07:00' };
  click('Cập nhật số dư', document);
  await wait(() => statusReads >= 3, 'active customer refresh'); await tick(); await tick(); await closePayment();
  check(phase + ' refresh keeps active balance credit and elapsed time current', fee()?.innerText.includes('60.000') && fee()?.innerText.includes('20.000') && fee()?.innerText.includes('2 giờ 10 phút') && fee()?.querySelector('.fee-total')?.innerText.includes('40.000') && paymentActions().length === 1, fee()?.innerText);
  for (const invalid of ['wrong-session', 'invalid-balance', 'unavailable']) {
    phase = 'customer-' + invalid; await customerReady();
    statusResponse = invalid === 'wrong-session' ? { ...completedBalance, session_id: 'someone-elses-stay' }
      : invalid === 'invalid-balance' ? { ...completedBalance, balance_due: -1 } : activeBalance;
    rejectStatus = invalid === 'unavailable';
    click('Cập nhật số dư', document);
    await wait(() => statusReads >= 3, phase + ' refresh finished'); await tick(); await tick();
    await closePayment();
    check(phase + ' cannot offer stale payment after untrusted refresh', paymentActions().length === 0 && !fee()?.querySelector('.fee-total'), host.innerText);
  }
  for (const race of ['pending', 'changed-token']) {
    phase = 'customer-' + race; await customerReady();
    statusResponse = completedBalance; holdStatus = true;
    click('Cập nhật số dư', document);
    await wait(() => releaseStatus, phase + ' delayed summary response');
    await closePayment(false);
    check(phase + ' pending refresh offers no actionable payment', paymentActions().length === 0);
    check(phase + ' lookup input is protected while refresh runs', host.querySelector('#customer-plate').disabled && host.querySelector('#customer-type').disabled);
    if (race === 'changed-token') localStorage.setItem('token', 'different-isolated-session');
    releaseStatus(); await tick(); await tick(); await tick();
    check(phase + ' late response cannot revive an actionable old balance', paymentActions().length === 0, fee()?.innerText || 'cleared');
  }
  let role, rows, quote, quoteError, quoteReads, holdQuote, releaseQuote;
  const operatorAdapter = async config => {
    await tick(); requests.push({ phase, method: config.method, url: config.url, params: config.params });
    let data = common(config, role);
    if (config.url.endsWith('/availability')) data = { occupied: rows.length, slots: [] };
    // payOS is enabled, so staff see "Tạo QR cho khách" + "Thu tiền mặt" (CL-ONLINE #79
    // reads this status; without payOS the pair is "Thu tiền mặt" + "Chuyển khoản").
    else if (config.url.endsWith('/payment-status')) data = { session_id: config.url.split('/').at(-2), session_status: 'active',
      enabled: true, supported: true, gross_fee: 10000, online_paid: 0, balance_due: 10000, can_quote: false, message: null };
    else if (config.url.endsWith('/sessions')) data = config.params?.license_plate ? [{ ...stay }] : rows.map(row => ({ ...row }));
    else if (config.url.endsWith('/checkout-quote')) {
      quoteReads += 1;
      if (holdQuote) await new Promise(resolve => { releaseQuote = resolve; });
      if (quoteError) throw failure(config, quoteError, quoteError === 409 ? 'Lượt gửi đã kết thúc.' : 'Không tải được phí hiện tại.');
      data = { ...quote };
    }
    return { data, status: 200, statusText: 'OK', headers: {}, config };
  };
  const operatorReady = async (selectedOffPage = false) => {
    rows = selectedOffPage ? [other] : [stay]; quoteReads = 0; quoteError = null; holdQuote = false; releaseQuote = null;
    quote = { session_id: stay.id, license_plate: stay.license_plate, parking_fee: 10000, online_paid: 0,
      balance_due: 10000, duration_minutes: 60, check_in_time: stay.check_in_time };
    api.defaults.adapter = operatorAdapter; mount(SitesWorkspace, role);
    await wait(() => host.querySelector('.data-table button'), phase + ' operator list');
    if (selectedOffPage) {
      click('Xe ra'); await wait(() => host.querySelector('#operation-query'), 'exit lookup');
      await change('#operation-query', stay.license_plate); host.querySelector('button[type=submit]').click();
    } else host.querySelector('.data-table button').click();
    await wait(() => fee()?.querySelector('.fee-total')?.textContent.includes('10.000'), phase + ' initial quote');
  };
  const refreshOperator = () => {
    button('Làm mới dữ liệu').closest('details').open = true;
    click('Làm mới dữ liệu');
  };
  for (role of ['manager', 'admin']) {
    phase = role + '-departed'; await operatorReady();
    rows = []; quoteError = 409; refreshOperator();
    await wait(() => host.innerText.includes('Bãi chưa có xe.'), phase + ' updated list'); await tick(); await tick();
    check(phase + ' refresh never retains departed payment actions', paymentActions().length === 0 && !fee()?.querySelector('.fee-total'), fee()?.innerText);
    check(phase + ' refresh verifies selection independently of old rows', quoteReads > 1 || !fee()?.querySelector('.plate'), { quoteReads });
  }
  role = 'manager';
  for (const scenario of ['active', 'off-page', 'unavailable', 'wrong-session']) {
    phase = 'manager-' + scenario; await operatorReady(scenario === 'off-page');
    quote = { ...quote, parking_fee: 30000, online_paid: 20000, balance_due: 10000, duration_minutes: 130 };
    if (scenario === 'wrong-session') quote.session_id = other.id;
    quoteError = scenario === 'unavailable' ? 503 : null; holdQuote = true;
    const before = quoteReads; refreshOperator();
    await wait(() => releaseQuote, phase + ' refreshed quote starts');
    check(phase + ' pending refresh hides stale fee and payment actions', !fee()?.querySelector('.fee-total') && paymentActions().length === 0, fee()?.innerText);
    holdQuote = false; releaseQuote();
    await wait(() => scenario === 'unavailable' ? fee()?.innerText.includes('Không tải được phí hiện tại.')
      : scenario === 'wrong-session' ? fee()?.querySelector('[role="alert"]') : fee()?.innerText.includes('30.000'), phase + ' refreshed quote finishes');
    if (scenario === 'wrong-session') {
      check(phase + ' mismatched quote never exposes another stay balance or checkout actions', !fee()?.querySelector('.fee-total') && paymentActions().length === 0, fee()?.innerText);
      continue;
    }
    if (scenario === 'unavailable') {
      check(phase + ' failed refresh keeps no stale fee or cashier action', !fee()?.querySelector('.fee-total') && paymentActions().length === 0, fee()?.innerText);
      quoteError = null; click('Thử lại', fee());
      await wait(() => fee()?.innerText.includes('30.000'), 'quote recovery');
      check(phase + ' retry restores verified payment actions', paymentActions().length === 2);
    } else {
      const text = fee().innerText;
      check(phase + ' refresh includes current fee online credit and elapsed time', text.includes('30.000') && text.includes('20.000') && text.includes('2 giờ 10 phút') && quoteReads > before, text);
      check(phase + ' active selection is retained with current payment actions', fee().querySelector('.plate')?.textContent === stay.license_plate && paymentActions().length === 2);
      if (scenario === 'off-page') check(phase + ' selected stay absent from current page remains valid', !host.querySelector('.data-table').innerText.includes(stay.license_plate));
    }
  }
  check('fixtures never submit payment checkout or other business writes', requests.every(request => request.method === 'get' || request.url.endsWith('/fee-lookup')));
  return { checks, requests, fixture_scope: 'Actual React pages; isolated API contract responses only. Cash completed follows real backend lifecycle shape; no production mutations.' };
})()
