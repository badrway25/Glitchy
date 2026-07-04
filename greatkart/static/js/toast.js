/* Phase 65 — lightweight toast feedback. window.glToast(message, tone).
   tone: 'success' | 'info' | 'warn'. Vanilla, reduced-motion safe, auto-dismiss,
   no dependency. Reads server messages rendered into #toastHost[data-toast]. */
(function () {
  "use strict";

  var REDUCED = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function host() {
    var h = document.getElementById("toastHost");
    if (!h) {
      h = document.createElement("div");
      h.id = "toastHost";
      h.className = "toast-host";
      h.setAttribute("aria-live", "polite");
      h.setAttribute("aria-atomic", "true");
      document.body.appendChild(h);
    }
    return h;
  }

  var ICONS = { success: "fa-check-circle", info: "fa-info-circle", warn: "fa-exclamation-triangle" };

  function show(message, tone) {
    if (!message) return;
    tone = ICONS[tone] ? tone : "info";
    var h = host();
    var t = document.createElement("div");
    t.className = "toast toast-" + tone;
    t.setAttribute("role", "status");
    t.innerHTML = '<span class="toast-ic"><i class="fa ' + ICONS[tone] + '" aria-hidden="true"></i></span>' +
      '<span class="toast-msg"></span>' +
      '<button type="button" class="toast-x" aria-label="Dismiss"><i class="fa fa-times" aria-hidden="true"></i></button>';
    t.querySelector(".toast-msg").textContent = message;
    h.appendChild(t);

    var dismiss = function () {
      if (t._gone) return;
      t._gone = true;
      t.classList.remove("is-in");
      t.classList.add("is-out");
      window.setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, REDUCED ? 0 : 260);
    };
    t.querySelector(".toast-x").addEventListener("click", dismiss);
    if (REDUCED) { t.classList.add("is-in"); }
    else { requestAnimationFrame(function () { t.classList.add("is-in"); }); }
    window.setTimeout(dismiss, 4200);
  }

  window.glToast = show;

  // Surface any server-rendered messages (data-toast) as toasts.
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }
  ready(function () {
    var seed = document.querySelectorAll("#toastHost [data-toast]");
    Array.prototype.forEach.call(seed, function (el) {
      show(el.getAttribute("data-msg") || el.textContent, el.getAttribute("data-tone") || "info");
      if (el.parentNode) el.parentNode.removeChild(el);
    });
  });
})();
