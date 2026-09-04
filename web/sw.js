// 妈妈的消息 · 浏览器版的 Service Worker
// 只做一件事：把 Python 运行时（约 10 MB，按版本号 URL 缓存优先）和本站文件（网络优先、断网回退缓存）存下来，
// 让"下载过一次之后断网也能用"成立。不碰用户的记录——那些只在页面内存里（Pyodide 的虚拟文件系统），从不经过这里。
const CACHE = "mama-message-v1";
const RUNTIME_RE = /\/pyodide(@|\/v?)0\.26\.4\//;   // jsDelivr 的 /pyodide/v0.26.4/full/ 和 unpkg 的 /pyodide@0.26.4/

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(clients.claim()));

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.searchParams.has("probe")) return;                          // 页面探测下载源的请求，不缓存
  if (RUNTIME_RE.test(url.pathname)) { e.respondWith(cacheFirst(req)); return; }
  if (url.origin === location.origin) { e.respondWith(networkFirst(req)); }
});

async function cacheFirst(req) {
  const c = await caches.open(CACHE);
  const hit = await c.match(req);
  if (hit) return hit;
  const r = await fetch(req);
  if (r.ok) c.put(req, r.clone());
  return r;
}

async function networkFirst(req) {
  const c = await caches.open(CACHE);
  try {
    const r = await fetch(req);
    if (r.ok) c.put(req, r.clone());
    return r;
  } catch (err) {
    const hit = await c.match(req);
    if (hit) return hit;
    throw err;
  }
}
