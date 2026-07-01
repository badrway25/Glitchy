/* Glitchy admin — sober motion layer (Phase 69). Progressive enhancement only: the dashboard
   renders fully WITHOUT this file (server-computed inline widths/offsets). JS just replays the
   values from zero for flair. prefers-reduced-motion => no animation, no layout shift, no CDN. */
(function () {
  "use strict";
  var REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function countUp(el) {
    var target = parseFloat(el.getAttribute("data-gl-count"));
    if (isNaN(target)) return;
    if (REDUCED) { el.textContent = target; return; }
    var dur = 900, t0 = null;
    function step(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased);
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = target;
    }
    el.textContent = "0";
    requestAnimationFrame(step);
  }

  function animateWithin(root) {
    // bars: replay width from 0 -> inline target
    root.querySelectorAll("[data-gl-bar]").forEach(function (b) {
      var to = b.getAttribute("data-gl-bar") + "%";
      if (REDUCED) { b.style.width = to; return; }
      b.style.width = "0%";
      requestAnimationFrame(function () { requestAnimationFrame(function () { b.style.width = to; }); });
    });
    // sparkline: replay height
    root.querySelectorAll("[data-gl-bar-h]").forEach(function (b) {
      var to = b.getAttribute("data-gl-bar-h") + "%";
      if (REDUCED) { b.style.height = to; return; }
      b.style.height = "0%";
      requestAnimationFrame(function () { requestAnimationFrame(function () { b.style.height = to; }); });
    });
    // ring: replay stroke-dashoffset from full circumference -> target
    root.querySelectorAll("[data-gl-ring-to]").forEach(function (arc) {
      var circ = arc.getAttribute("data-gl-ring");
      var to = arc.getAttribute("data-gl-ring-to");
      if (REDUCED) { arc.setAttribute("stroke-dashoffset", to); return; }
      arc.setAttribute("stroke-dashoffset", circ);
      requestAnimationFrame(function () { requestAnimationFrame(function () { arc.setAttribute("stroke-dashoffset", to); }); });
    });
    root.querySelectorAll("[data-gl-count]").forEach(countUp);
  }

  onReady(function () {
    var cards = document.querySelectorAll("[data-gl-reveal]");
    if (REDUCED || !("IntersectionObserver" in window)) {
      cards.forEach(function (c) { c.classList.add("is-in"); });
      animateWithin(document);
      return;
    }
    var io = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        el.classList.add("is-in");
        animateWithin(el);
        obs.unobserve(el);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    cards.forEach(function (c) { io.observe(c); });
  });
})();
