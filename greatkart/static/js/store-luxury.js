/*
 * Luxury store experience — progressive enhancement (vanilla, no deps).
 *  - Collapsible filter sections (persisted in localStorage) + per-section counts.
 *  - Scroll reveal for product / category cards (IntersectionObserver).
 *  - "Continue your search": remembers the last applied filters (localStorage).
 * Respects prefers-reduced-motion. Without JS the store works fully (sections open).
 */
(function () {
  "use strict";
  var REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  // ---- Collapsible filter sections + active counts ------------------------ #
  function collapsible() {
    var store = {};
    try { store = JSON.parse(localStorage.getItem("gk_filter_collapsed") || "{}"); } catch (e) {}

    document.querySelectorAll("[data-lxf-toggle]").forEach(function (btn) {
      var section = btn.closest("[data-lxf-section]");
      var body = section && section.querySelector("[data-lxf-body]");
      if (!section || !body) return;
      var key = btn.getAttribute("aria-controls") || "";
      if (store[key]) { section.classList.add("is-collapsed"); btn.setAttribute("aria-expanded", "false"); }

      btn.addEventListener("click", function () {
        var collapsed = section.classList.toggle("is-collapsed");
        btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
        try { store[key] = collapsed ? 1 : 0; localStorage.setItem("gk_filter_collapsed", JSON.stringify(store)); } catch (e) {}
      });
    });

    // Per-section active count badge.
    document.querySelectorAll("[data-lxf-section][data-lxf-group]").forEach(function (section) {
      var badge = section.querySelector("[data-lxf-count]");
      if (!badge) return;
      var n = 0;
      section.querySelectorAll('input[type="checkbox"]').forEach(function (c) { if (c.checked) n += 1; });
      // price counts as 1 if any bound is set
      section.querySelectorAll('input[type="number"]').forEach(function (i) { if (i.value) n += 1; });
      if (n > 0) { badge.textContent = n; badge.hidden = false; } else { badge.hidden = true; }
    });
  }

  // ---- Scroll reveal ----------------------------------------------------- #
  function reveal() {
    if (REDUCED || !("IntersectionObserver" in window)) return;
    var targets = document.querySelectorAll(".product-item, .ymal-card, [data-reveal], .collx-card");
    if (!targets.length) return;
    targets.forEach(function (el) { el.classList.add("reveal"); });
    var io = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-in"); obs.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    targets.forEach(function (el) { io.observe(el); });
    // failsafe: reveal everything after 1.4s in case observer never fires
    setTimeout(function () { targets.forEach(function (el) { el.classList.add("is-in"); }); }, 1400);
  }

  // ---- Saved filter view ("Continue your search") ------------------------ #
  function savedFilters() {
    var KEY = "gk_saved_filters";
    var path = location.pathname;
    var qs = location.search.replace(/^\?/, "");
    var onStore = /\/store\/?$/.test(path) || /\/store\/category\//.test(path);
    var hasFilters = /(?:^|&)(color|size|min_price|max_price|rating|sale|new|in_stock|keyword|collection)=/.test(qs);
    if (!onStore) return;

    // Filters applied -> remember this view, no banner.
    if (hasFilters) {
      try { localStorage.setItem(KEY, JSON.stringify({ url: path + location.search })); } catch (e) {}
      return;
    }

    // Clean store page -> offer to resume the last saved search.
    var banner = document.querySelector("[data-lxf-saved]");
    if (!banner || qs) return;
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) {}
    if (!saved || !saved.url) return;
    var link = banner.querySelector("[data-lxf-saved-link]");
    if (link) link.setAttribute("href", saved.url);
    banner.classList.add("is-shown");
    var dismiss = banner.querySelector("[data-lxf-saved-dismiss]");
    if (dismiss) dismiss.addEventListener("click", function (e) {
      e.preventDefault();
      try { localStorage.removeItem(KEY); } catch (_) {}
      banner.classList.remove("is-shown");
    });
  }

  ready(function () { collapsible(); reveal(); savedFilters(); });
})();
