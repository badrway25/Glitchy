/* Advanced shop filters: mobile drawer open/close + filter_clear analytics. Vanilla. */
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var drawer = document.getElementById("filterDrawer");
    if (drawer) {
      function open() {
        drawer.hidden = false;
        document.body.style.overflow = "hidden";
        requestAnimationFrame(function () {
          drawer.classList.add("is-open");
          var first = drawer.querySelector("input, a, button");
          if (first) first.focus();
        });
      }
      function close() {
        drawer.classList.remove("is-open");
        document.body.style.overflow = "";
        setTimeout(function () { drawer.hidden = true; }, 250);
      }
      document.querySelectorAll("[data-open-filters]").forEach(function (b) {
        b.addEventListener("click", open);
      });
      drawer.querySelectorAll("[data-drawer-close]").forEach(function (b) {
        b.addEventListener("click", close);
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && drawer.classList.contains("is-open")) close();
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
  });
})();
