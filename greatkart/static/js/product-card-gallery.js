/* Phase 61 — product card image carousel (store grid).
   Vanilla, dependency-free, progressive enhancement on top of CSS scroll-snap.
   Prev/next buttons scroll one slide; dots reflect position and end-arrows hide
   at the bounds; the track is keyboard-scrollable (Arrow keys); native touch
   swipe on mobile. Respects prefers-reduced-motion. No-ops when no gallery exists. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var galleries = Array.prototype.slice.call(document.querySelectorAll("[data-card-gallery]"));
    galleries.forEach(function (g) {
      var track = g.querySelector(".pcard-track");
      var slides = g.querySelectorAll(".pcard-slide");
      var dots = g.querySelectorAll(".pcard-dot");
      var prev = g.querySelector("[data-card-prev]");
      var next = g.querySelector("[data-card-next]");
      if (!track || slides.length < 2) return;

      function index() {
        return track.clientWidth ? Math.round(track.scrollLeft / track.clientWidth) : 0;
      }
      function go(i) {
        i = Math.max(0, Math.min(slides.length - 1, i));
        track.scrollTo({ left: i * track.clientWidth, behavior: reduce ? "auto" : "smooth" });
      }
      function update() {
        var i = index();
        for (var d = 0; d < dots.length; d++) dots[d].classList.toggle("is-on", d === i);
        if (prev) prev.hidden = i <= 0;
        if (next) next.hidden = i >= slides.length - 1;
      }
      update();

      if (prev) prev.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation(); go(index() - 1);
      });
      if (next) next.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation(); go(index() + 1);
      });

      track.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight") { e.preventDefault(); go(index() + 1); }
        else if (e.key === "ArrowLeft") { e.preventDefault(); go(index() - 1); }
      });

      var ticking = false;
      track.addEventListener("scroll", function () {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function () { ticking = false; update(); });
      }, { passive: true });

      window.addEventListener("resize", function () { update(); }, { passive: true });
    });
  });
})();
