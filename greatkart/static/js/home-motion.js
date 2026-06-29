/* Phase 58 — premium homepage motion.
   Vanilla, dependency-free, progressive-enhancement. Respects
   prefers-reduced-motion. No layout shift, rAF-throttled, IO-based.
     1. Hero parallax (translateY the hero image as you scroll; Ken Burns is CSS)
     2. "The Edit" cards: staggered reveal-on-scroll
     3. Subtle pointer tilt on the cards (desktop fine-pointer only)
   ~1.6KB. No-ops when the homepage markup is absent. */
(function () {
  "use strict";
  var motionMq = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  var reduce = !!(motionMq && motionMq.matches);
  function reduceNow() { return motionMq ? motionMq.matches : reduce; }

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    /* 1. Hero parallax ----------------------------------------------------- */
    var hero = document.querySelector(".hero-x");
    var heroPic = hero && hero.querySelector(".hero-x-pic");
    if (hero && heroPic && !reduce) {
      var ticking = false;
      function update() {
        ticking = false;
        var rect = hero.getBoundingClientRect();
        if (rect.bottom < 0 || rect.top > window.innerHeight) return; // off-screen
        var shift = Math.max(-60, Math.min(60, rect.top * -0.12));
        heroPic.style.transform = "translate3d(0," + shift.toFixed(1) + "px,0)";
      }
      function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(update); } }
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
      update();
    }

    /* 2. Edit cards: staggered reveal -------------------------------------- */
    var cards = Array.prototype.slice.call(document.querySelectorAll(".edit-card[data-reveal]"));
    function revealAll() { cards.forEach(function (c) { c.classList.add("is-visible"); }); }
    if (cards.length) {
      if (reduce || !("IntersectionObserver" in window)) {
        revealAll();
      } else {
        var io = new IntersectionObserver(function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) { e.target.classList.add("is-visible"); io.unobserve(e.target); }
          });
        }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
        cards.forEach(function (c) { io.observe(c); });
        // Safety net: never leave content hidden.
        window.addEventListener("load", function () { setTimeout(revealAll, 1800); });
      }
    }

    /* 3. Subtle pointer tilt (desktop, fine pointer, motion allowed) ------- */
    var fine = window.matchMedia && window.matchMedia("(hover:hover) and (pointer:fine)").matches;
    if (cards.length && fine && !reduce) {
      cards.forEach(function (card) {
        var raf = null;
        card.addEventListener("mousemove", function (ev) {
          // Honor a reduced-motion preference toggled AFTER load, too.
          if (reduceNow()) { card.style.transform = ""; return; }
          if (raf) return;
          raf = requestAnimationFrame(function () {
            raf = null;
            var r = card.getBoundingClientRect();
            var px = (ev.clientX - r.left) / r.width - 0.5;
            var py = (ev.clientY - r.top) / r.height - 0.5;
            card.style.transform = "translateY(-4px) perspective(900px) rotateX(" +
              (py * -2.6).toFixed(2) + "deg) rotateY(" + (px * 2.6).toFixed(2) + "deg)";
          });
        });
        card.addEventListener("mouseleave", function () { card.style.transform = ""; });
      });
    }

    /* 4. Rotating tagline (reduced-motion: keep the first line only) -------- */
    var rotator = document.querySelector("[data-rotator]");
    if (rotator && !reduce) {
      var rots = Array.prototype.slice.call(rotator.querySelectorAll(".rot"));
      if (rots.length > 1) {
        var ri = 0;
        setInterval(function () {
          if (reduceNow()) return;            // respect a mid-session toggle
          rots[ri].classList.remove("is-on");
          ri = (ri + 1) % rots.length;
          rots[ri].classList.add("is-on");
        }, 3800);
      }
    }
  });
})();
