/* Pacer Service Worker (§17.4) — 앱 셸 캐시 + 웹푸시.
   본격 캐싱 전략(정적=cache-first / 데이터 API=network-first)·폼 상태 보존은 P0에서 확장. */
const SHELL_CACHE = "pacer-shell-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// 네비게이션은 network-first, 실패 시 캐시 셸로 폴백
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.mode !== "navigate") return;
  event.respondWith(
    fetch(request).catch(() => caches.match(request).then((r) => r || caches.match("/"))),
  );
});

// 웹푸시 수신 → 알림 표시 (§17.4)
self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "Pacer";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "",
      data: { url: data.url || "/dashboard?source=push" },
    }),
  );
});

// 알림 클릭 → 해당 리포트로 딥링크 (§17.4)
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/dashboard";
  event.waitUntil(self.clients.openWindow(url));
});
