(async () => {
  const source = await (await fetch('/src/pages/Expansion/CustomerFees.jsx')).text();
  const mainSource = await (await fetch('/src/main.jsx')).text();
  const dependency = (text, name) => text.match(new RegExp('["\']([^"\']*/deps/' + name + '\\.js[^"\']*)["\']'))[1];
  const ReactModule = await import(dependency(source, 'react'));
  const React = ReactModule.default || ReactModule;
  const DomModule = await import(dependency(mainSource, 'react-dom_client'));
  const { createRoot } = DomModule.default || DomModule;
  const { MemoryRouter } = await import(dependency(source, 'react-router-dom'));
  const { default: CameraOperations } = await import('/src/pages/Expansion/CameraOperations.jsx');
  const { default: api } = await import('/src/services/api.js');
  const wait = async (condition, label) => {
    for (let n = 0; n < 250; n++) { if (condition()) return; await new Promise(resolve => setTimeout(resolve, 30)); }
    throw Error('Timed out: ' + label);
  };
  const checks = [];
  const check = (name, passed) => checks.push({name, passed: Boolean(passed)});
  let enabled = false, liveUploads = 0, paused = false, rows = [], processes = [];
  const frame = (id, capture_source) => ({id, camera_id: 1, site_id: 2, capture_source,
    captured_at: new Date().toISOString(), observed_at: new Date().toISOString(),
    ocr_status: 'no_plate', suggested_plate: null, review_status: 'pending', image_url: '/fixture.jpg'});
  api.defaults.adapter = async config => {
    let data = {};
    if (config.url.endsWith('/cameras')) data = [{id: 1, name: 'Camera kiểm thử', direction: 'entry', is_active: true, edge_enabled: true, health: 'unseen', last_received_at: null}];
    else if (config.url.endsWith('/automation')) { if (config.method === 'put') enabled = true; data = {enabled, minimum_confidence: .97, max_age_seconds: 15}; }
    else if (config.url.endsWith('/vision/observations')) data = [...rows];
    else if (config.url.endsWith('/vision/live-frames')) {
      liveUploads++;
      if (paused) throw {response: {status: 409, data: {detail: {code: 'camera_review_required', message: 'Camera có 20 ảnh chưa đọc được biển số đang chờ kiểm tra. Tự động tạm dừng để giữ ảnh đối chiếu.'}}}};
      data = frame('native-' + liveUploads, 'live_camera'); rows.push(data);
    } else if (config.url.endsWith('/process')) { const id = config.url.split('/').at(-2); processes.push(id); data = {state: 'manual', reason: 'Fixture requires human review'}; }
    else if (config.url.endsWith('/vision/status')) data = {available: true};
    else if (config.url.endsWith('/fixture.jpg')) data = new Blob([], {type: 'image/jpeg'});
    return {data, status: 200, statusText: 'OK', headers: {}, config};
  };
  document.getElementById('root').style.display = 'none';
  const host = document.createElement('main'); host.className = 'prototype-ui'; host.style.padding = '12px'; document.body.appendChild(host);
  const root = createRoot(host);
  window.__cameraSourceCleanup = () => root.unmount();
  root.render(React.createElement(MemoryRouter, null, React.createElement(CameraOperations,
    {site: {id: 2, role: 'manager'}, onManual: () => {}, onPassage: () => {}, onCheckout: () => {}})));
  const button = text => [...host.querySelectorAll('button')].find(item => item.textContent.trim() === text);
  const setSource = value => {
    const select = host.querySelector('#camera-capture-source');
    select.value = value; select.dispatchEvent(new Event('change', {bubbles: true}));
  };
  await wait(() => button('Bật tự động') && !button('Bật tự động').disabled, 'initial enabled button');
  check('actual document policy allows camera', document.featurePolicy.allowsFeature('camera'));
  check('media API is native, never JavaScript overridden', String(navigator.mediaDevices.getUserMedia).includes('[native code]'));
  check('edge token defaults to this-device camera, not assumed connected', host.querySelector('#camera-capture-source').value === 'live_camera');
  button('Bật tự động').click();
  await wait(() => liveUploads > 0 && button('Dừng tự động') && host.querySelector('video').videoWidth > 0, 'native media capture starts despite saved edge token');
  check('native webcam captured a real browser-generated frame', host.querySelector('video').srcObject?.getVideoTracks().some(track => track.readyState === 'live') && liveUploads > 0);
  button('Dừng tự động').click();
  await wait(() => button('Bật tự động') && !host.querySelector('#camera-capture-source').disabled, 'stop before source switch');
  const uploadsBeforeEdge = liveUploads;
  setSource('edge');
  await wait(() => host.querySelector('#camera-capture-source').value === 'edge', 'external source selection');
  button('Bật tự động').click();
  await wait(() => button('Dừng tự động') && host.innerText.includes('Chờ nguồn ảnh'), 'offline source waiting state');
  check('unseen external feed is waiting, not advertised as running capture', !host.querySelector('.camera-result').innerText.includes('Tự động đang bật'));
  check('external mode neither opens nor uploads from webcam', !host.querySelector('video').srcObject?.getVideoTracks().some(track => track.readyState === 'live') && liveUploads === uploadsBeforeEdge);
  rows = [frame('edge-fresh', 'edge')];
  await wait(() => processes.includes('edge-fresh') && host.querySelector('.camera-result').innerText.includes('Tự động đang bật'), 'edge receipt becomes active');
  check('actual edge frame restores processing without token-health inference', processes.includes('edge-fresh'));
  rows = rows.map(row => ({...row, observed_at: new Date(Date.now() - 31000).toISOString(), captured_at: new Date(Date.now() - 31000).toISOString()}));
  await wait(() => host.innerText.includes('Chờ nguồn ảnh'), 'stale source returns to waiting');
  check('stale external receipts stop claiming an active source', host.innerText.includes('Đang chờ ảnh từ camera ngoài'));
  button('Dừng tự động').click();
  await wait(() => button('Bật tự động') && !host.querySelector('#camera-capture-source').disabled, 'stop external');
  setSource('live_camera'); paused = true;
  await wait(() => !button('Bật tự động').disabled, 'webcam ready to resume');
  button('Bật tự động').click();
  await wait(() => host.innerText.includes('Camera có 20 ảnh') && button('Bật tự động'), 'typed backpressure pauses capture');
  const pausedUploads = liveUploads;
  check('unreadable backlog keeps preview available for operator inspection', host.querySelector('video').srcObject?.getVideoTracks().some(track => track.readyState === 'live'));
  await new Promise(resolve => setTimeout(resolve, 4300));
  check('persistent quota conflict stops repeated uploads', liveUploads === pausedUploads);
  check('operator receives concrete review guidance', host.innerText.includes('Tự động tạm dừng để giữ ảnh đối chiếu'));
  paused = false;
  button('Bật tự động').click();
  await wait(() => liveUploads > pausedUploads && button('Dừng tự động'), 'resume after server review');
  check('manual resume can capture again after backlog is reviewed', liveUploads > pausedUploads);
  button('Dừng tự động').click();
  await wait(() => button('Bật tự động'), 'final stop');
  return {checks, actual: {liveUploads, processes, physicalCameraTested: false, fixtureApi: true}};
})()
