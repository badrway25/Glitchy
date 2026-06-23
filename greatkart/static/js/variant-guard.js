/* Variant guard — blocks PDP "Add to cart" until colour AND size are chosen, with a
   premium modal (no browser alert) and visual highlight of the missing selector.
   Capturing submit listener so it runs BEFORE the spinner/analytics handlers. Vanilla. */
(function () {
  "use strict";
  var form = document.getElementById("pdpForm");
  if (!form) return;

  var modal = document.getElementById("variantGuard");
  var msgEl = document.getElementById("vgMsg");
  var I18N = {};
  try { I18N = JSON.parse(document.getElementById("vgI18n").textContent); } catch (e) {}

  var lastMissing = [];   // which selectors were missing, to focus on confirm

  function wrap(field) { return document.querySelector('[data-vg-wrap="' + field + '"]'); }

  function clearInvalid(field) {
    var w = wrap(field);
    if (w) { w.classList.remove("vg-invalid"); }
    var input = form.querySelector('input[name="' + field + '"]');
    if (input) input.removeAttribute("aria-invalid");
  }
  function markInvalid(field) {
    var w = wrap(field);
    if (w) { w.classList.add("vg-invalid"); }
    var input = form.querySelector('input[name="' + field + '"]');
    if (input) input.setAttribute("aria-invalid", "true");
  }

  function messageFor(missing) {
    if (missing.length >= 2) return I18N.both || "Choose a colour and size first.";
    if (missing[0] === "color") return I18N.color || I18N.both || "Choose a colour first.";
    return I18N.size || I18N.both || "Choose a size first.";
  }

  function openModal(missing) {
    lastMissing = missing.slice();
    missing.forEach(markInvalid);
    if (msgEl) msgEl.textContent = messageFor(missing);
    if (modal) {
      modal.hidden = false;
      requestAnimationFrame(function () { modal.classList.add("is-open"); });
      var cta = modal.querySelector("[data-vg-confirm]");
      if (cta) setTimeout(function () { cta.focus(); }, 40);
    }
    // scroll the first missing selector into view behind the modal
    var first = wrap(missing[0]);
    if (first) first.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove("is-open");
    setTimeout(function () { modal.hidden = true; }, 200);
  }

  function focusMissing() {
    closeModal();
    var field = lastMissing[0];
    var w = wrap(field);
    if (!w) return;
    var toggle = w.querySelector(".dropdown-toggle, .custom-select-btn");
    setTimeout(function () {
      if (toggle) {
        toggle.focus();
        try { window.jQuery && window.jQuery(toggle).dropdown("show"); } catch (e) {}
      }
    }, 220);
  }

  // Capturing submit guard
  form.addEventListener("submit", function (e) {
    var colorInput = form.querySelector('input[name="color"]');
    var sizeInput = form.querySelector('input[name="size"]');
    var missing = [];
    if (colorInput && !colorInput.value.trim()) missing.push("color");
    if (sizeInput && !sizeInput.value.trim()) missing.push("size");
    if (missing.length) {
      e.preventDefault();
      e.stopImmediatePropagation();   // block spinner + analytics on a rejected submit
      openModal(missing);
    }
  }, true);

  // Clear the invalid state as soon as the shopper picks a value
  document.addEventListener("click", function (e) {
    var item = e.target.closest && e.target.closest('.custom-select-dd .dropdown-item[data-value]');
    if (!item) return;
    var input = item.getAttribute("data-target-input") || "";
    if (input.indexOf("color") !== -1) clearInvalid("color");
    if (input.indexOf("size") !== -1) clearInvalid("size");
  });

  // Modal close wiring
  if (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target === modal || (e.target.closest && e.target.closest("[data-vg-close]"))) closeModal();
    });
    var confirm = modal.querySelector("[data-vg-confirm]");
    if (confirm) confirm.addEventListener("click", focusMissing);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) closeModal();
    });
  }
})();
