/* Home trust cards — Phase 76.
 * Equal-height cards are pure CSS; this only adds the progressive-enhancement detail modal:
 * clamp each description to 2 lines and reveal a discreet "Read more" ONLY when the text
 * actually overflows; clicking it opens a native <dialog> (free focus-trap + ESC + backdrop)
 * with the full copy. No JS -> full text stays visible (accessible, SEO-safe). */
(function () {
  "use strict";
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var root = document.querySelector("[data-lux-features]");
    var dialog = document.getElementById("luxFeatureDialog");
    if (!root) return;

    var cards = root.querySelectorAll(".lux-feature");
    Array.prototype.forEach.call(cards, function (card) {
      var p = card.querySelector("p");
      var more = card.querySelector("[data-lux-more]");
      if (!p || !more) return;
      card.classList.add("lux-clamp");
      // reveal the trigger only if the clamped copy is actually truncated
      if (p.scrollHeight - p.clientHeight > 2) {
        card.classList.add("lux-overflow");
      } else {
        more.remove();
      }
      if (!dialog || !dialog.showModal) return;   // no <dialog> support -> leave full text (unclamped fallback below)
      more.addEventListener("click", function () {
        var title = card.querySelector("h4");
        var ic = card.querySelector(".lux-ic");
        var dIc = dialog.querySelector("[data-lux-dialog-ic]");
        dialog.querySelector("[data-lux-dialog-title]").textContent = title ? title.textContent.trim() : "";
        dialog.querySelector("[data-lux-dialog-text]").textContent = p.textContent.trim();
        if (dIc) dIc.innerHTML = ic ? ic.innerHTML : "";
        dialog.showModal();
      });
    });

    if (dialog && dialog.showModal) {
      // close via the ✕ button and via a backdrop click; ESC is handled natively
      dialog.addEventListener("click", function (e) {
        if (e.target === dialog || e.target.closest("[data-lux-close]")) dialog.close();
      });
    } else {
      // no <dialog>: don't clamp (keep everything readable) and drop the triggers
      Array.prototype.forEach.call(cards, function (card) {
        card.classList.remove("lux-clamp", "lux-overflow");
        var m = card.querySelector("[data-lux-more]");
        if (m) m.remove();
      });
    }
  });
})();
