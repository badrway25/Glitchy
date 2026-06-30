/* Phase 64 — refined page motion: staggered card reveal + KPI count-up.
   Reuses the existing [data-reveal] / .is-visible system; adds only what's missing.
   Vanilla, progressive, prefers-reduced-motion safe, no layout shift. */
(function () {
  "use strict";

  var REDUCED = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    // --- Staggered reveal: container gets .is-visible, children cascade via CSS ---
    var groups = Array.prototype.slice.call(document.querySelectorAll("[data-reveal-stagger]"));
    if (REDUCED || !("IntersectionObserver" in window)) {
      groups.forEach(function (g) { g.classList.add("is-visible"); });
    } else {
      var io = new IntersectionObserver(function (entries, obs) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("is-visible"); obs.unobserve(e.target); }
        });
      }, { threshold: 0.08, rootMargin: "0px 0px -8% 0px" });
      groups.forEach(function (g) { io.observe(g); });
    }

    // --- KPI count-up: animate [data-countup] from 0 to its number once visible ---
    var nums = Array.prototype.slice.call(document.querySelectorAll("[data-countup]"));
    function finalText(el) { return el.getAttribute("data-countup") || el.textContent; }
    function run(el) {
      var target = parseFloat((finalText(el) || "").replace(/[^0-9.]/g, ""));
      if (!isFinite(target) || target <= 0) return;            // nothing to animate
      var prefix = el.getAttribute("data-countup-prefix") || "";
      var decimals = (finalText(el).split(".")[1] || "").length;
      var start = null, dur = 900;
      function frame(ts) {
        if (start === null) start = ts;
        var p = Math.min(1, (ts - start) / dur);
        var eased = 1 - Math.pow(1 - p, 3);                    // easeOutCubic
        el.textContent = prefix + (target * eased).toFixed(decimals);
        if (p < 1) requestAnimationFrame(frame);
        else el.textContent = prefix + target.toFixed(decimals);
      }
      requestAnimationFrame(frame);
    }
    if (REDUCED || !("IntersectionObserver" in window)) {
      // leave the server-rendered final values untouched
    } else {
      var io2 = new IntersectionObserver(function (entries, obs) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { run(e.target); obs.unobserve(e.target); }
        });
      }, { threshold: 0.5 });
      nums.forEach(function (el) { io2.observe(el); });
    }
  });
})();
