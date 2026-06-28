/*
 * Product Quick View — opens a premium drawer (bottom sheet on mobile) that
 * fetches a lightweight product fragment so shoppers can pick a variant and add
 * to cart without leaving the store grid. No order is created here; add-to-cart
 * submits the normal form. Accessible: focus trap-ish, Esc/outside close, ARIA.
 */
(function () {
  "use strict";

  var root = null, body = null, lastTrigger = null;

  function build() {
    if (root) return;
    root = document.createElement("div");
    root.className = "qv-backdrop";
    root.hidden = true;
    root.innerHTML =
      '<div class="qv-drawer" role="dialog" aria-modal="true" aria-label="Quick view" tabindex="-1">' +
      '<button class="qv-close" type="button" data-qv-close aria-label="Close">' +
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
      '</button>' +
      '<div class="qv-content" data-qv-content><div class="qv-skeleton"><div class="qv-sk-media"></div>' +
      '<div class="qv-sk-line"></div><div class="qv-sk-line short"></div><div class="qv-sk-line"></div></div></div>' +
      '</div>';
    document.body.appendChild(root);
    body = root.querySelector("[data-qv-content]");

    root.addEventListener("click", function (e) {
      if (e.target === root || (e.target.closest && e.target.closest("[data-qv-close]"))) close();
    });
  }

  function open() {
    build();
    root.hidden = false;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(function () { root.classList.add("is-open"); });
  }

  function close() {
    if (!root) return;
    root.classList.remove("is-open");
    document.body.style.overflow = "";
    setTimeout(function () {
      root.hidden = true;
      body.innerHTML = "";
    }, 220);
    if (lastTrigger && lastTrigger.focus) lastTrigger.focus();
  }

  function showSkeleton() {
    body.innerHTML = '<div class="qv-skeleton"><div class="qv-sk-media"></div>' +
      '<div class="qv-sk-line"></div><div class="qv-sk-line short"></div><div class="qv-sk-line"></div></div>';
  }

  function wireForm() {
    var form = body.querySelector("[data-qv-form]");
    if (!form) return;
    form.addEventListener("submit", function (e) {
      var selects = form.querySelectorAll("select[required]");
      var missing = false;
      selects.forEach(function (s) { if (!s.value) missing = true; });
      if (missing) {
        e.preventDefault();
        var err = form.querySelector("[data-qv-err]");
        if (err) { err.textContent = form.getAttribute("data-msg") || "Please choose your options."; err.hidden = false; }
      }
    });
  }

  function load(productId, trigger) {
    lastTrigger = trigger || null;
    open();
    showSkeleton();
    fetch("/store/quick-view/" + encodeURIComponent(productId) + "/",
          { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("bad"); return r.text(); })
      .then(function (html) {
        body.innerHTML = html;
        if (window.enhanceSelects) window.enhanceSelects();   // premium dropdowns
        wireForm();
        var drawer = root.querySelector(".qv-drawer");
        if (drawer) drawer.focus();
      })
      .catch(function () {
        var msg = (document.body && document.body.getAttribute("data-qv-error")) ||
          "Could not load this product. Please try again.";
        body.innerHTML = '<div class="qv-error">' + msg + "</div>";
      });
  }

  document.addEventListener("click", function (e) {
    var trig = e.target.closest && e.target.closest("[data-quick-view]");
    if (!trig) return;
    e.preventDefault();
    var id = trig.getAttribute("data-quick-view");
    if (id) load(id, trig);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && root && !root.hidden) close();
  });
})();
