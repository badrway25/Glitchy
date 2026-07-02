/* Product card image carousel (store grid) — Phase 75 rewrite.
 * TRANSFORM-based (translateX by active index), not native scroll: deterministic across all
 * browsers/devices (no scroll-snap "snaps back" ambiguity), so clicking prev/next visibly
 * changes the image. Vanilla, dependency-free, idempotent init (safe to call again after
 * dynamic DOM updates). Prev/next + keyboard + pointer swipe. Respects prefers-reduced-motion.
 * No-ops for single-image cards. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initOne(g) {
    if (g.dataset.glCarousel === "1") return;      // idempotent
    var track = g.querySelector(".pcard-track");
    var slides = g.querySelectorAll(".pcard-slide");
    if (!track || slides.length < 2) { return; }   // single image -> no controls
    g.dataset.glCarousel = "1";
    g.dataset.galleryCount = String(slides.length);

    var dots = g.querySelectorAll(".pcard-dot");
    var prev = g.querySelector("[data-card-prev]");
    var next = g.querySelector("[data-card-next]");
    var i = 0;

    function render() {
      track.style.transform = "translateX(" + (-i * 100) + "%)";
      for (var d = 0; d < dots.length; d++) dots[d].classList.toggle("is-on", d === i);
      if (prev) prev.hidden = i <= 0;
      if (next) next.hidden = i >= slides.length - 1;
      g.setAttribute("data-active-index", String(i));
    }
    function go(n) {
      var clamped = Math.max(0, Math.min(slides.length - 1, n));
      if (clamped === i) return;
      i = clamped;
      render();
    }
    render();

    if (prev) prev.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation(); go(i - 1);
    });
    if (next) next.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation(); go(i + 1);
    });

    // keyboard on the focusable track
    track.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") { e.preventDefault(); go(i + 1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(i - 1); }
    });

    // pointer swipe (touch/pen) — a real swipe moves the carousel; a tap still opens the PDP
    var x0 = null, swiped = false;
    g.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "mouse") return;       // mouse uses the arrows
      x0 = e.clientX; swiped = false;
    }, { passive: true });
    g.addEventListener("pointermove", function (e) {
      if (x0 === null) return;
      if (Math.abs(e.clientX - x0) > 10) swiped = true;
    }, { passive: true });
    g.addEventListener("pointerup", function (e) {
      if (x0 === null) return;
      var dx = e.clientX - x0;
      if (Math.abs(dx) > 40) { go(dx < 0 ? i + 1 : i - 1); }
      x0 = null;
    }, { passive: true });
    // suppress the slide's link navigation right after a swipe
    track.addEventListener("click", function (e) {
      if (swiped) { e.preventDefault(); e.stopPropagation(); swiped = false; }
    }, true);
  }

  function initProductCardGalleries(root) {
    var scope = root || document;
    var gals = scope.querySelectorAll("[data-card-gallery]");
    Array.prototype.forEach.call(gals, initOne);
  }
  // expose for re-init after dynamic inserts (quick view, infinite scroll, etc.)
  window.initProductCardGalleries = initProductCardGalleries;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initProductCardGalleries(); });
  } else {
    initProductCardGalleries();
  }
})();
