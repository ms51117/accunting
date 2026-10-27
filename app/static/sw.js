const CACHE_NAME = 'accounting-pwa-v1';
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon.svg',
  '/static/icons/apple-touch-icon.png',
  '/static/css/jalalidatepicker.min.css',
  '/static/js/bootstrap.bundle.min.js',
  '/static/js/jalalidatepicker.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css'
];

// Install: Cache critical static shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Pre-cache partial failure (some external CDNs may be restricted):', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: Clean up older caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Network-first for HTML pages (to ensure fresh data), Cache-first for static assets
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Ignore non-GET requests (e.g. POST form submissions)
  if (req.method !== 'GET') {
    return;
  }

  // Static assets (CSS, JS, Images, Fonts) -> Cache-first with background revalidate
  if (
    url.pathname.startsWith('/static/') ||
    url.hostname.includes('cdn.jsdelivr.net') ||
    url.pathname.match(/\.(png|jpg|jpeg|svg|css|js|woff2|woff|ttf)$/)
  ) {
    event.respondWith(
      caches.match(req).then((cachedResp) => {
        const fetchPromise = fetch(req).then((networkResp) => {
          if (networkResp && networkResp.status === 200) {
            const respClone = networkResp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, respClone));
          }
          return networkResp;
        }).catch(() => cachedResp);
        return cachedResp || fetchPromise;
      })
    );
    return;
  }

  // HTML pages / API routes -> Network-first with cache fallback
  event.respondWith(
    fetch(req)
      .then((networkResp) => {
        if (networkResp && networkResp.status === 200) {
          const respClone = networkResp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, respClone));
        }
        return networkResp;
      })
      .catch(() => {
        return caches.match(req).then((cached) => {
          if (cached) return cached;
          return caches.match('/');
        });
      })
  );
});
