/* Premium fashion rebrand — lightweight, dependency-free enhancements.
   Reveal-on-scroll (IntersectionObserver), native lazy images, add-to-cart
   button feedback. Respects prefers-reduced-motion. ~1.5KB. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  // Enable reveal styling only when JS runs (content stays visible without JS).
  document.documentElement.classList.add("js-anim");

  ready(function () {
    /* 1. Reveal-on-scroll: auto-tag common content blocks, then observe. */
    var sel = ".home-section, .lux-feature, .lux-strip, .pdp-card, .reviews-card, " +
              ".summary-card, .dash-card, .p-card, .product-card";
    var nodes = Array.prototype.slice.call(document.querySelectorAll(sel));
    nodes.forEach(function (n) {
      if (!n.hasAttribute("data-reveal")) n.setAttribute("data-reveal", "");
    });
    function revealAll() { nodes.forEach(function (n) { n.classList.add("is-visible"); }); }

    if (reduce || !("IntersectionObserver" in window)) {
      revealAll();
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
            io.unobserve(e.target);
          }
        });
      }, { threshold: 0.06, rootMargin: "0px 0px -40px 0px" });
      nodes.forEach(function (n) { io.observe(n); });
      // Safety net: never leave content hidden (slow scroll / capture / odd cases).
      window.addEventListener("load", function () { setTimeout(revealAll, 1600); });
    }

    /* 2. Native lazy-loading for product imagery (no layout work, just a hint). */
    document.querySelectorAll(".p-media img, .product-card img, .media-skeleton img")
      .forEach(function (img) {
        if (!img.hasAttribute("loading")) img.setAttribute("loading", "lazy");
        if (!img.hasAttribute("decoding")) img.setAttribute("decoding", "async");
      });

    /* 3. Add-to-cart: subtle pressed/loading feedback (form posts then navigates). */
    document.querySelectorAll('form[action*="add_cart"]').forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector('button[type="submit"]');
        if (btn && !btn.disabled) {
          btn.dataset._label = btn.innerHTML;
          btn.innerHTML = '<i class="fas fa-circle-notch fa-spin mr-2"></i> ' +
            (btn.textContent.trim() || "Adding…");
          btn.style.opacity = ".85";
        }
      });
    });
  });
})();
