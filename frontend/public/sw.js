const CACHE='spare-shell-v1';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/','/icon-192.png','/manifest.webmanifest']))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==location.origin)return;
 // Never cache financial or provider responses.
 if(url.pathname.startsWith('/assets/')){event.respondWith(caches.open(CACHE).then(async cache=>{const hit=await cache.match(event.request);if(hit)return hit;const r=await fetch(event.request);if(r.ok)cache.put(event.request,r.clone());return r}));return}
 if(event.request.mode==='navigate')event.respondWith(fetch(event.request).catch(()=>caches.match('/')));
});
