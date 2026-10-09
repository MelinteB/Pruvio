const CACHE = 'pruvs-shell-v6.12.0';

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
      icon: '/static/pruvs-192.png', badge: '/static/pruvs-192.png',
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

const STATIC = [
  '/static/manifest.webmanifest?v=6.11.1',
  '/static/pruvs-logo.png',
  '/static/pruvs-mark.png',
  '/static/pruvs-32.png?v=6.11.1',
  '/static/pruvs-180.png?v=6.11.1',
  '/static/pruvs-192.png?v=6.11.1',
  '/static/pruvs-512.png?v=6.11.1'
];

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

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const isNavigation = event.request.mode === 'navigate';
  if (isNavigation) {
    // Never cache authenticated HTML/navigation responses.
    event.respondWith(fetch(event.request));
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const url = new URL(event.request.url);
        if (url.pathname.startsWith('/static/')) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, copy)).catch(() => undefined);
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
