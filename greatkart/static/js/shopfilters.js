/* Advanced shop filters: mobile drawer open/close + filter_clear analytics. Vanilla. */
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var drawer = document.getElementById("filterDrawer");
    if (drawer) {
      var panel = drawer.querySelector(".filter-drawer-panel");
      var lastOpener = null;
      function focusables() {
        return Array.prototype.slice.call(panel.querySelectorAll(
          'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea,[tabindex]:not([tabindex="-1"])'
        )).filter(function (el) { return el.offsetParent !== null; });
      }
      function open(e) {
        lastOpener = (e && e.currentTarget) || document.activeElement;
        drawer.hidden = false;
        document.body.style.overflow = "hidden";
        requestAnimationFrame(function () {
          drawer.classList.add("is-open");
          var f = focusables();
          if (f.length) f[0].focus();
        });
      }
      function close() {
        drawer.classList.remove("is-open");
        document.body.style.overflow = "";
        setTimeout(function () { drawer.hidden = true; }, 280);
        if (lastOpener && lastOpener.focus) lastOpener.focus();
      }
      document.querySelectorAll("[data-open-filters]").forEach(function (b) {
        b.addEventListener("click", open);
      });
      drawer.querySelectorAll("[data-drawer-close]").forEach(function (b) {
        b.addEventListener("click", close);
      });
      // "Show results" in the sticky footer submits the in-sheet filter form.
      var applyBtn = drawer.querySelector("[data-sheet-apply]");
      if (applyBtn) applyBtn.addEventListener("click", function () {
        var form = drawer.querySelector("[data-filter-form]");
        if (form) form.requestSubmit ? form.requestSubmit() : form.submit();
      });
      document.addEventListener("keydown", function (e) {
        if (!drawer.classList.contains("is-open")) return;
        if (e.key === "Escape") { close(); return; }
        if (e.key === "Tab") {  // focus trap
          var f = focusables(); if (!f.length) return;
          var first = f[0], last = f[f.length - 1], a = document.activeElement;
          if (e.shiftKey && (a === first || !panel.contains(a))) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && (a === last || !panel.contains(a))) { e.preventDefault(); first.focus(); }
        }
      });
    }

    // Clean shareable URLs: drop empty fields before the filter form submits.
    document.querySelectorAll("[data-filter-form]").forEach(function (form) {
      form.addEventListener("submit", function () {
        form.querySelectorAll("input, select").forEach(function (el) {
          if ((el.type === "radio" || el.type === "checkbox")) {
            if (!el.checked) el.disabled = true;          // unchecked -> omit
            else if (el.value === "") el.disabled = true; // "Any" rating radio -> omit
          } else if (el.value === "" || el.value == null) {
            el.disabled = true;                            // empty number/text -> omit
          }
        });
      });
    });

    // filter_clear analytics (Reset / Clear filters links)
    document.querySelectorAll("[data-filter-clear]").forEach(function (a) {
      a.addEventListener("click", function () { if (window.gkTrack) window.gkTrack("filter_clear", {}); });
    });

    // Self-contained sort dropdown (no Bootstrap) — one toggle, robust open/close.
    document.querySelectorAll("[data-sortx]").forEach(function (root) {
      var btn = root.querySelector("[data-sortx-toggle]");
      if (!btn) return;
      function close() { root.classList.remove("is-open"); btn.setAttribute("aria-expanded", "false"); }
      function open() { root.classList.add("is-open"); btn.setAttribute("aria-expanded", "true"); }
      btn.addEventListener("click", function (e) {
        e.stopPropagation();                       // don't let the document handler immediately re-close
        root.classList.contains("is-open") ? close() : open();
      });
      document.addEventListener("click", function (e) { if (!root.contains(e.target)) close(); });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    });
  });
})();
