// The block between BUILD:START and BUILD:END is rewritten by build_banks.py.
// BUILD:START
const VERSION = "key-terms-33c1de985a";
const FILES = [
  "./",
  "./index.html",
  "./play.html",
  "./manifest.json",
  "./banks/banks.js",
  "./icons/apple-touch-icon.png",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./images/cell-chloroplast.svg",
  "./images/cell-nucleus.svg",
  "./images/cell-vacuole.svg",
  "./images/cell-wall.svg",
  "./images/eye-cornea.svg",
  "./images/eye-lens.svg",
  "./images/eye-retina.svg",
  "./images/geo-delta.svg",
  "./images/geo-meander.svg",
  "./images/geo-oxbow-lake.svg",
  "./images/lab-beaker.svg",
  "./images/lab-burette.svg",
  "./images/lab-conical-flask.svg",
  "./images/lab-measuring-cylinder.svg",
  "./images/lab-pipette.svg",
  "./images/lab-test-tube.svg",
  "./images/obj-apple.svg",
  "./images/obj-book.svg",
  "./images/obj-car.svg",
  "./images/obj-fish.svg",
  "./images/obj-house.svg",
  "./images/obj-key.svg",
  "./images/obj-sun.svg",
  "./images/obj-tree.svg",
  "./images/sym-ammeter.svg",
  "./images/sym-battery.svg",
  "./images/sym-cell.svg",
  "./images/sym-diode.svg",
  "./images/sym-fuse.svg",
  "./images/sym-lamp.svg",
  "./images/sym-ldr.svg",
  "./images/sym-resistor.svg",
  "./images/sym-thermistor.svg",
  "./images/sym-voltmeter.svg"
];
// BUILD:END

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);

  // Google Fonts: serve from cache, refresh in the background.
  if (url.hostname.endsWith("fonts.googleapis.com") || url.hostname.endsWith("fonts.gstatic.com")) {
    e.respondWith(caches.open(VERSION).then(async c => {
      const hit = await c.match(e.request);
      const net = fetch(e.request).then(r => { c.put(e.request, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }

  // App files: cache first, then network.
  if (url.origin === location.origin) {
    e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(hit => hit || fetch(e.request)));
  }
});
