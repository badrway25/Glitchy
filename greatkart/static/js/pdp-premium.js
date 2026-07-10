/* PDP premium behaviours (colour-driven gallery + description read-more).
 *
 * Colour-driven gallery: when the shopper picks a colour, the main image
 * crossfades to that colour's primary mockup and the thumbnail rail narrows to
 * the images mapped to that colour. The mapping is PERSISTED server-side
 * (ProductColorImage, built offline at sync time / by the management command)
 * and shipped as JSON in #pdpColorImages — no network call happens here.
 * Unknown colour or no mapping -> graceful no-op (default gallery stays).
 *
 * Selection plumbing stays in theme.js (writes #colorInput + label); this file
 * only OBSERVES colour clicks, so ordering vs. theme.js doesn't matter.
 */
(function () {
  "use strict";

  var onReady = function (fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  };

  onReady(function () {
    /* ---------- description read-more (independent of the gallery) ---------- */
    var overview = document.getElementById("pdpOverview");
    var toggle = document.querySelector("[data-overview-toggle]");
    if (overview && toggle) {
      var moreLabel = toggle.textContent;
      toggle.addEventListener("click", function () {
        var clamped = overview.classList.toggle("is-clamped");
        toggle.textContent = clamped ? moreLabel : (toggle.getAttribute("data-label-less") || moreLabel);
      });
    }

    /* ---------- colour-driven gallery ---------- */
    var main = document.getElementById("pdpMainImg");
    var mapEl = document.getElementById("pdpColorImages");
    if (!main || !mapEl) return;

    var colorMap = {};
    try { colorMap = JSON.parse(mapEl.textContent) || {}; } catch (e) { return; }
    if (!Object.keys(colorMap).length) return;

    var thumbs = Array.prototype.slice.call(document.querySelectorAll(".pdp-thumb[data-image-id]"));
    var lightboxImg = document.querySelector("#pdpLightbox img");
    var swapGeneration = 0;

    function swapMain(url) {
      if (!url || main.getAttribute("src") === url) return;
      /* generation counter: a slow preload from an EARLIER colour pick must not
         land after a newer one and revert the main image */
      var generation = ++swapGeneration;
      var pre = new Image();
      pre.onload = function () {
        if (generation !== swapGeneration) return;
        main.classList.add("pdp-img-swap");
        window.setTimeout(function () {
          if (generation !== swapGeneration) return;
          main.src = url;
          if (lightboxImg) lightboxImg.src = url;
          main.classList.remove("pdp-img-swap");
        }, 160); /* matches the CSS opacity transition */
      };
      pre.src = url;
    }

    function applyColor(color) {
      swapGeneration++; /* any new pick invalidates in-flight preloads (even fallback picks) */
      var entry = colorMap[(color || "").toLowerCase()];
      if (!entry || !entry.images || !entry.images.length) {
        /* elegant fallback: unknown colour -> full default gallery, no swap */
        thumbs.forEach(function (t) { t.classList.remove("pdp-thumb-hidden"); });
        return;
      }
      var wanted = {};
      entry.images.forEach(function (id) { wanted[String(id)] = true; });
      var visible = thumbs.filter(function (t) { return wanted[t.getAttribute("data-image-id")]; });
      if (visible.length) {
        thumbs.forEach(function (t) {
          t.classList.toggle("pdp-thumb-hidden", !wanted[t.getAttribute("data-image-id")]);
        });
      } else {
        thumbs.forEach(function (t) { t.classList.remove("pdp-thumb-hidden"); });
      }
      if (entry.primary) {
        swapMain(entry.primary);
        thumbs.forEach(function (t) {
          t.classList.toggle("active", t.getAttribute("data-img") === entry.primary);
        });
      }
    }

    /* observe colour picks (theme.js writes the hidden input in its own handler) */
    document.addEventListener("click", function (e) {
      var item = e.target.closest && e.target.closest(
        '.custom-select-dd .dropdown-item[data-target-input="colorInput"]');
      if (item) applyColor(item.getAttribute("data-value") || "");
    });

    /* restore state when the browser brings the page back with a colour pre-set */
    var input = document.getElementById("colorInput");
    if (input && input.value) applyColor(input.value);
  });
})();
