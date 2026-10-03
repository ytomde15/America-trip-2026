/* 圏外でもページを開けるようにする仕組み（Service Worker）
   ・電波があるとき：いつもどおり最新を取りに行き、取れたものを端末に控える
   ・圏外・5秒待っても取れないとき：端末に控えた前回の内容を出す
   控えるのは このサイトのページ（index.html・stable.html）だけ。 */
var CACHE = 'trip-2026-v1';
var FILES = ['./', 'index.html', 'stable.html'];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE)
      .then(function (c) { return c.addAll(FILES); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(keys.filter(function (k) { return k !== CACHE; })
          .map(function (k) { return caches.delete(k); }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  if (new URL(req.url).origin !== self.location.origin) return;

  e.respondWith(
    caches.open(CACHE).then(function (cache) {
      var timeout = new Promise(function (resolve, reject) {
        setTimeout(function () { reject(new Error('timeout')); }, 5000);
      });
      return Promise.race([fetch(req), timeout])
        .then(function (res) {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        })
        .catch(function () {
          return cache.match(req, { ignoreSearch: true }).then(function (hit) {
            return hit || cache.match('index.html');
          });
        });
    })
  );
});
