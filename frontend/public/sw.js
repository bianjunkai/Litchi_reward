const CACHE = 'family-rewards-shell-v15'

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE)
    const response = await fetch('/', { cache: 'reload' })
    if (!response.ok) throw new Error('Cannot cache app shell')
    const html = await response.clone().text()
    await cache.put('/', response)
    const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"\s]+)"/g)].map(match => match[1])
    await cache.addAll(['/icon.svg', '/manifest.webmanifest', ...assets])
    await self.skipWaiting()
  })())
})
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('family-rewards-shell-') && key !== CACHE) await caches.delete(key)
    }
    await self.clients.claim()
  })())
})
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url)
  // Never cache rewards, authentication, downloads, or mutations.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/')))
  } else if (url.pathname.startsWith('/assets/') || ['/icon.svg','/manifest.webmanifest'].includes(url.pathname)) {
    event.respondWith((async () => (await caches.match(event.request)) || fetch(event.request))())
  }
})
