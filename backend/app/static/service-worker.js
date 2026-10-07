const CACHE = 'pruvs-shell-v6.10.0';
const STATIC = [
  '/static/manifest.webmanifest?v=6.10.0',
  '/static/pruvs-logo.png',
  '/static/pruvs-mark.png',
  '/static/pruvs-32.png?v=6.10.0',
  '/static/pruvs-180.png?v=6.10.0',
  '/static/pruvs-192.png?v=6.10.0',
  '/static/pruvs-512.png?v=6.10.0'
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
