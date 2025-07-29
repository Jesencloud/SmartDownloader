// Empty service worker to prevent 404 errors
// This file is intentionally empty to satisfy browser requests
self.addEventListener('install', function(event) {
    // Skip waiting to activate immediately
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    // Claim all clients
    event.waitUntil(self.clients.claim());
}); 