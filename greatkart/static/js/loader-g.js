/* Global premium loader — the Glitchy "G" with tricolore glitch strokes.
 *
 * Philosophy: the loader must NEVER cost performance or flicker. It is hidden at first paint
 * (no animation runs while [hidden]) and only appears when something is genuinely slow:
 *   - full-page navigations (internal link clicks / form submits) that take longer than SHOW_DELAY;
 *   - explicit AJAX operations via the public API: window.glLoader.show(label) / .hide().
 * bfcache-safe (pageshow hides it), fail-open (auto-hide watchdog), reduced-motion handled in CSS,
 * accessible (role=status + translated label rendered server-side in base.html).
 */
(function () {
  "use strict";

  var SHOW_DELAY = 220;   // only show if the operation is slower than this (no flicker)
  var MIN_VISIBLE = 450;  // once shown, keep visible at least this long (no flash-out)
  var WATCHDOG = 12000;   // absolute safety: never stay up longer than this

  var el = null, showTimer = null, shownAt = 0, watchdog = null;

  function node() {
    if (!el) el = document.getElementById("glxLoader");
    return el;
  }

  function reallyShow() {
    var n = node();
    if (!n) return;
    n.hidden = false;
    n.setAttribute("aria-hidden", "false");
    // double-rAF so the transition runs from opacity:0
    requestAnimationFrame(function () { requestAnimationFrame(function () { n.classList.add("glx-on"); }); });
    shownAt = Date.now();
    clearTimeout(watchdog);
    watchdog = setTimeout(hide, WATCHDOG);
  }

  function show() {
    if (!node() || showTimer || (shownAt && !node().hidden)) return;
    showTimer = setTimeout(function () { showTimer = null; reallyShow(); }, SHOW_DELAY);
  }

  function hide() {
    clearTimeout(showTimer); showTimer = null;
    clearTimeout(watchdog); watchdog = null;
    var n = node();
    if (!n || n.hidden) { shownAt = 0; return; }
    var wait = Math.max(0, MIN_VISIBLE - (Date.now() - shownAt));
    setTimeout(function () {
      n.classList.remove("glx-on");
      setTimeout(function () { n.hidden = true; n.setAttribute("aria-hidden", "true"); shownAt = 0; }, 240);
    }, wait);
  }

  // ---- full-page navigation wiring -------------------------------------------------------
  // Internal link clicks: show while the browser fetches the next page. Skip anchors,
  // downloads, new tabs, modified-key clicks and anything opted out via data-no-loader.
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download") || a.hasAttribute("data-no-loader")) return;
    var href = a.getAttribute("href") || "";
    if (href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:") || href.startsWith("javascript:")) return;
    if (a.origin && a.origin !== location.origin) return;
    // same-page hash change only
    if (a.pathname === location.pathname && a.search === location.search && a.hash) return;
    show();
  }, false);

  // Form submits that actually navigate (AJAX handlers preventDefault before this runs).
  document.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return;
    var f = e.target;
    if (!f || f.hasAttribute("data-no-loader") || f.target === "_blank") return;
    show();
  }, false);

  // bfcache restore / navigation cancelled (e.g. ESC) — never leave the loader stuck.
  window.addEventListener("pageshow", hide);
  window.addEventListener("pagehide", function () { clearTimeout(showTimer); showTimer = null; });

  // ---- public API for AJAX flows ---------------------------------------------------------
  window.glLoader = { show: show, hide: hide };
})();
