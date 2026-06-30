/* Portal utilities: password visibility toggle + copy-to-clipboard.
   Vanilla, progressive, no dependencies. Safe when the targets are absent. */
(function () {
  "use strict";

  // --- Password visibility toggle ---------------------------------------
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-pw-toggle]");
    if (!btn) return;
    var wrap = btn.closest(".pw-wrap");
    var input = wrap && wrap.querySelector("input");
    if (!input) return;
    var showing = input.getAttribute("type") === "text";
    input.setAttribute("type", showing ? "password" : "text");
    var icon = btn.querySelector("i");
    if (icon) {
      icon.classList.toggle("fa-eye", showing);
      icon.classList.toggle("fa-eye-slash", !showing);
    }
    var showLabel = btn.getAttribute("data-show-label") || "Show password";
    var hideLabel = btn.getAttribute("data-hide-label") || "Hide password";
    btn.setAttribute("aria-label", showing ? showLabel : hideLabel);
  });

  // --- Copy to clipboard -------------------------------------------------
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-copy]");
    if (!btn) return;
    var text = btn.getAttribute("data-copy") || "";
    if (!text) return;
    var done = function () {
      var original = btn.getAttribute("data-copied-label") || "Copied";
      var label = btn.querySelector("[data-copy-label]");
      var prev = label ? label.textContent : null;
      btn.classList.add("is-copied");
      if (label) label.textContent = original;
      setTimeout(function () {
        btn.classList.remove("is-copied");
        if (label && prev !== null) label.textContent = prev;
      }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {});
    } else {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (err) {}
      document.body.removeChild(ta);
    }
  });
})();
