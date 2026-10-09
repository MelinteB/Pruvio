const CACHE = 'pruvs-shell-v6.12.2';

// v6.12: device notifications also work when no Pruvs page is open.
self.addEventListener('push', event => {
  event.waitUntil((async () => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (_) {}
    let url = '/notifications';
    try {
      const candidate = new URL(data.url || url, self.location.origin);
      if (candidate.origin === self.location.origin && candidate.pathname.startsWith('/notifications')) url = candidate.href;
    } catch (_) {}
    await self.registration.showNotification(data.title || 'Pruvs', {
      body: data.body || 'You have an update in Pruvs.',
      icon: '/static/pruvs-notification-192.png?v=6.12.2', badge: '/static/pruvs-notification-96.png?v=6.12.2',
      tag: data.tag || 'pruvs-update', data: {url}
    });
  })());
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    let url = new URL(event.notification.data?.url || '/notifications', self.location.origin);
    if (url.origin !== self.location.origin || !url.pathname.startsWith('/notifications')) url = new URL('/notifications', self.location.origin);
    const windows = await self.clients.matchAll({type:'window', includeUncontrolled:true});
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(url.href); await client.focus(); return;
      }
    }
    await self.clients.openWindow(url.href);
  })());
});

const STATIC = ['/static/pruvs-notification-192.png?v=6.12.2', '/static/pruvs-notification-96.png?v=6.12.2'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC)).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => (key.startsWith('pruvio-shell-') || key.startsWith('pruvs-shell-')) && key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

// PRUVS_6122_NOTIFICATIONS: never intercept API, auth or HTML navigation.
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || request.mode === 'navigate') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) return;
  event.respondWith(
    fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {}));
      }
      return response;
    }).catch(async () => (await caches.match(request)) || Response.error())
  );
});
