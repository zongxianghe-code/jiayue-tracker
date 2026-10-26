const C='jy-v9';
const SHELL=['./','./index.html','./ref.json','./apple-touch-icon.png','./manifest.json','./icon-192.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))));self.clients.claim()});
// Stale-while-revalidate for the app shell: open instantly from cache, refresh cache in background.
// (textdb data is cross-origin and never touched here.)
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==location.origin)return;
 const nav=e.request.mode==='navigate';const key=nav?'./':e.request;
 e.respondWith(caches.open(C).then(async c=>{
  const hit=await c.match(key,{ignoreSearch:true});
  const net=fetch(e.request,{cache:'no-cache'}).then(r=>{if(r&&r.ok)c.put(key,r.clone());return r}).catch(()=>null);
  if(hit){e.waitUntil(net);return hit}
  return (await net)||c.match('./')}))});
