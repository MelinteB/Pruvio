/* Permission requests run in the actual browser click, never a server callback. */
window.PruvsPush = (() => {
  let config, state, registration, currentId;
  const $ = id => document.getElementById(id);
  const status = text => { $('push-status').textContent = text; };
  async function api(path, method = 'GET', data) {
    const response = await fetch('/notifications-api/' + path, {method, cache: 'no-store',
      headers: {'Authorization': 'Bearer ' + config.token, 'Content-Type': 'application/json'},
      body: data === undefined ? undefined : JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Notification request failed.');
    return result;
  }
  function keyBytes(value) {
    const raw = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4));
    return Uint8Array.from(raw, c => c.charCodeAt(0));
  }
  function localGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function localSet(key, value) { try { localStorage.setItem(key, value); } catch {} }
  function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
  async function refresh() {
    state = await api('state');
    const holder = $('push-preferences'); holder.replaceChildren();
    const names = {push_enabled:'Device push notifications', email_enabled:'Email fallback when push is unavailable',
      receipts:'Receipt processing results', bills:'Bills settled or reopened', reminders:'Payment reminders'};
    for (const [key, value] of Object.entries(state.preferences)) {
      const label = node('label', ''); label.style.cssText = 'display:block;padding:6px 0';
      const input = document.createElement('input'); input.type = 'checkbox'; input.id = 'pref-' + key; input.checked = value;
      label.append(input, document.createTextNode(' ' + names[key])); holder.append(label);
    }
    $('push-save').disabled = false;
    const devices = $('push-devices'); devices.replaceChildren();
    for (const d of state.devices) {
      const row = node('div', `${d.label}: ${!d.active ? 'disabled' : d.confirmed_at ? 'test confirmed' : 'awaiting test confirmation'}${d.id === currentId ? ' (this device)' : ''}`);
      row.style.cssText = 'padding:10px 0;border-bottom:1px solid #e0e8f6';
      if (d.active) {
        const button = node('button', 'Disable'); button.className = 'pruvio-secondary'; button.style.marginLeft = '10px';
        button.onclick = () => action(async () => { await api('disable', 'POST', {device_id:d.id}); await refresh(); }); row.append(button);
      }
      devices.append(row);
    }
    if (!state.devices.length) devices.append(node('p', 'No devices registered yet.'));
    const history = $('push-history'); history.replaceChildren();
    for (const event of state.events) {
      const row = node('div', ''); row.style.cssText = 'padding:12px 0;border-bottom:1px solid #e0e8f6';
      const link = node('a', event.title); link.href = event.url; link.className = 'pruvio-link';
      row.append(link, node('p', event.body), node('small', `${new Date(event.created_at+'Z').toLocaleString()} · ${event.status.replaceAll('_', ' ')}`));
      history.append(row);
    }
    if (!state.events.length) history.append(node('p', 'No notifications yet.'));
    const current = state.devices.find(d => d.id === currentId && d.active && d.current_login);
    $('push-test').disabled = !current || !state.enabled;
    $('push-disable').disabled = !current;
    if (!state.enabled) status('Device notifications are not configured yet. Email and your in-app history remain available.');
    else if (current?.confirmed_at) status('Test notification confirmed on this device. Notifications are ready.');
    else if (current) status('Permission granted. Tap Send test notification, then tap the notification you receive.');
  }
  async function action(fn) { try { await fn(); } catch (error) { status(error.message || 'Please try again.'); } }
  async function sendTest() {
    await api('test', 'POST', {device_id: currentId});
    status('Test queued. Leave Pruvs or lock your phone, then tap the notification to confirm. If nothing arrives, check device settings and refresh this page.');
  }
  async function init(value) {
    config = value; currentId = localGet('pruvs-push-device');
    $('push-save').onclick = () => action(async () => {
      const preferences = {};
      for (const key of Object.keys(state.preferences)) preferences[key] = $('pref-' + key).checked;
      await api('preferences', 'PUT', preferences); status('Notification preferences saved.');
    });
    $('push-test').onclick = () => action(sendTest);
    $('push-disable').onclick = () => action(async () => {
      await api('disable', 'POST', {device_id: currentId});
      const sub = await registration?.pushManager.getSubscription(); if (sub) await sub.unsubscribe();
      const shown = await registration?.getNotifications(); for (const n of shown || []) n.close();
      currentId = null; localSet('pruvs-push-device',''); await refresh(); status('Notifications disabled on this device.');
    });
    const ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
    const help = $('push-help');
    if (ios && !standalone) {
      help.textContent = 'iPhone / iPad: open Pruvs in Safari, tap Share → Add to Home Screen, then open Pruvs from that icon and sign in. Requires iOS / iPadOS 16.4 or later.';
      await refresh(); status('Add Pruvs to your Home Screen to enable device notifications.'); return;
    }
    help.textContent = ios
      ? 'If notifications are blocked: open Settings → Notifications → Pruvs → Allow Notifications. Enable Lock Screen and Banners as desired. Return here and reload. Focus settings can silence alerts.'
      : /Android/.test(navigator.userAgent)
      ? 'If blocked: open your browser’s settings → Site settings → Notifications → pruvs.io and allow notifications. Also allow your browser/Pruvs in Android Settings → Apps → Notifications. Menu names vary by device. Return here and reload.'
      : 'If blocked: open the site permissions beside the address bar and allow notifications for pruvs.io. Also enable your browser in the operating system notification settings. Return here and reload.';
    if (!window.isSecureContext || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
      await refresh(); status('Push notifications are unavailable in this browser. Use email fallback or a supported browser over HTTPS.'); return;
    }
    try {
      registration = await navigator.serviceWorker.register('/service-worker.js?v=6.12.0', {scope:'/'});
      await navigator.serviceWorker.ready;
      if (localGet('pruvs-push-account') !== config.account) {
        const old = await registration.pushManager.getSubscription(); if (old) await old.unsubscribe();
        for (const n of await registration.getNotifications()) n.close();
        currentId = null; localSet('pruvs-push-device','');
      }
      await refresh();
      $('push-enable').disabled = !state.enabled;
      if (Notification.permission === 'denied') status('Notifications are blocked. Follow the settings instructions below, then reload this page.');
      $('push-enable').onclick = () => {
        // Call synchronously from the click to preserve iOS user activation.
        const permission = Notification.permission === 'default' ? Notification.requestPermission() : Promise.resolve(Notification.permission);
        action(async () => {
          if (await permission !== 'granted') { status('Permission was not granted. Follow the settings instructions below.'); return; }
          $('push-enable').disabled = true;
          try {
            let sub = await registration.pushManager.getSubscription();
            if (!sub) sub = await registration.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:keyBytes(state.public_key)});
            const result = await api('subscribe','POST',{subscription:sub.toJSON(), label:ios?'iPhone / iPad':/Android/.test(navigator.userAgent)?'Android':'Desktop browser'});
            currentId = result.device_id; localSet('pruvs-push-device',currentId); localSet('pruvs-push-account',config.account);
            await refresh(); await sendTest();
          } finally { $('push-enable').disabled = false; }
        });
      };
      const params = new URLSearchParams(location.hash.slice(1));
      if (params.has('confirm')) {
        const code = params.get('confirm'); history.replaceState(null,'',location.pathname);
        const result = await api('confirm','POST',{code});
        currentId = result.device_id; localSet('pruvs-push-device',currentId); await refresh();
        status('Test notification confirmed on this device. Notifications are ready.');
      }
    } catch (error) { status(error.message || 'Could not prepare notifications. Reload and try again.'); }
  }
  return {init};
})();
