/* Robust colour/size variant dropdowns — vanilla, sortx-style (no Bootstrap, no double-open).
   Toggles .is-open on the .custom-select-dd; closes on outside-click, Escape, and on select.
   Selection itself (writing the hidden input + label) stays in theme.js. */
(function () {
  "use strict";
  var roots = document.querySelectorAll("[data-csdd]");
  if (!roots.length) return;

  roots.forEach(function (root) {
    var btn = root.querySelector("[data-csdd-toggle]");
    if (!btn) return;

    function close() { root.classList.remove("is-open"); btn.setAttribute("aria-expanded", "false"); }
    function open() { root.classList.add("is-open"); btn.setAttribute("aria-expanded", "true"); }

    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();                       // single, controlled toggle
      root.classList.contains("is-open") ? close() : open();
    });

    // Close as soon as an option is chosen (theme.js writes the value on the same click).
    root.addEventListener("click", function (e) {
      if (e.target.closest(".dropdown-item[data-value]")) close();
    });

    document.addEventListener("click", function (e) { if (!root.contains(e.target)) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  });
})();
