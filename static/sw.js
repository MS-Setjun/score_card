const CACHE_NAME = 'notts-scorecard-shell-v1';
const SHELL_FILES = [
  '/',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-512-maskable.png'
];

self.addEventListener('install', function(event){
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache){
      return cache.addAll(SHELL_FILES);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(event){
  event.waitUntil(
    caches.keys().then(function(names){
      return Promise.all(
        names.filter(function(n){ return n !== CACHE_NAME; })
             .map(function(n){ return caches.delete(n); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(event){
  var url = new URL(event.request.url);

  // Never cache API calls — matches, teams, divisions, venues must always be fresh.
  if(url.pathname.startsWith('/api/')){
    event.respondWith(fetch(event.request).catch(function(){
      return new Response(JSON.stringify({error:'offline'}), {
        status: 503, headers: {'Content-Type':'application/json'}
      });
    }));
    return;
  }

  // App shell: cache-first so the app opens instantly, falling back to network.
  event.respondWith(
    caches.match(event.request).then(function(cached){
      if(cached) return cached;
      return fetch(event.request).then(function(response){
        if(response && response.ok && event.request.method === 'GET'){
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function(cache){ cache.put(event.request, copy); });
        }
        return response;
      });
    })
  );
});
