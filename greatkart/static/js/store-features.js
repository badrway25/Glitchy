/* Phase 67 — store premium features: safe quick-add (AJAX) + lightweight compare.
   Vanilla, progressive, no PII in localStorage (only product ids). Never creates an
   order or takes payment — quick-add only adds simple products to the cart and opens
   Quick View for products that need a size/colour. */
(function () {
  "use strict";

  function getCookie(name) {
    var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }
  function toast(msg, tone) { if (window.glToast && msg) window.glToast(msg, tone || "info"); }

  function updateCartCount(n) {
    if (n == null) return;
    document.querySelectorAll("[data-cart-count]").forEach(function (el) { el.textContent = n; });
  }

  // ---------------------------------------------------------------- quick add
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-quick-add]");
    if (!btn) return;
    e.preventDefault();
    if (btn.dataset.busy) return;
    var id = btn.getAttribute("data-quick-add");
    btn.dataset.busy = "1";
    btn.classList.add("is-loading");
    btn.setAttribute("aria-busy", "true");
    fetch("/cart/quick-add/" + encodeURIComponent(id) + "/", {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (d) {
        if (d && d.ok) {
          updateCartCount(d.count);
          toast(btn.getAttribute("data-added-label") || "Added to cart", "success");
        } else if (d && d.needs_options) {
          var qv = document.querySelector('[data-quick-view="' + id + '"]');
          if (qv) qv.click();
          else if (btn.getAttribute("data-product-url")) window.location.href = btn.getAttribute("data-product-url");
        } else {
          toast(btn.getAttribute("data-unavailable-label") || "No longer available", "warn");
        }
      })
      .catch(function () {})
      .finally(function () {
        delete btn.dataset.busy;
        btn.classList.remove("is-loading");
        btn.removeAttribute("aria-busy");
      });
  });

  // ----------------------------------------------------------------- compare
  var CMP_KEY = "gl_compare", CMP_MAX = 3;
  function cmpGet() { try { return JSON.parse(localStorage.getItem(CMP_KEY) || "[]"); } catch (e) { return []; } }
  function cmpSet(a) {
    a = a.filter(function (v, i) { return a.indexOf(v) === i; }).slice(0, CMP_MAX);
    try { localStorage.setItem(CMP_KEY, JSON.stringify(a)); } catch (e) {}
    updateCmpUI();
    return a;
  }

  function updateCmpUI() {
    var a = cmpGet();
    document.querySelectorAll("[data-compare-toggle]").forEach(function (b) {
      var on = a.indexOf(b.getAttribute("data-product-id")) >= 0;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    var bar = document.getElementById("cmpBar");
    if (bar) {
      var c = bar.querySelector("[data-compare-count]");
      if (c) c.textContent = a.length;
      bar.hidden = a.length === 0;
    }
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-compare-toggle]");
    if (!t) return;
    e.preventDefault();
    var id = t.getAttribute("data-product-id");
    var a = cmpGet();
    var i = a.indexOf(id);
    if (i >= 0) {
      a.splice(i, 1);
      cmpSet(a);
      toast(t.getAttribute("data-removed-label") || "Removed from compare", "info");
    } else {
      if (a.length >= CMP_MAX) { toast(t.getAttribute("data-full-label") || "You can compare up to 3 items", "warn"); return; }
      a.push(id);
      cmpSet(a);
      toast(t.getAttribute("data-added-label") || "Added to compare", "success");
    }
  });

  function openCompare() {
    var a = cmpGet();
    var drawer = document.getElementById("cmpDrawer");
    if (!drawer) return;
    var body = drawer.querySelector("[data-compare-body]");
    if (!a.length) { return; }
    fetch("/store/compare/?ids=" + encodeURIComponent(a.join(",")), { credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        body.innerHTML = html;
        drawer.classList.add("is-open");
        drawer.setAttribute("aria-hidden", "false");
        document.body.classList.add("cmp-open");
      })
      .catch(function () {});
  }
  function closeCompare() {
    var drawer = document.getElementById("cmpDrawer");
    if (!drawer) return;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("cmp-open");
  }

  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-compare-open]")) { e.preventDefault(); openCompare(); return; }
    if (e.target.closest && e.target.closest("[data-compare-close]")) { closeCompare(); return; }
    if (e.target.closest && e.target.closest("[data-compare-clear]")) { cmpSet([]); closeCompare(); return; }
    var rm = e.target.closest && e.target.closest("[data-compare-remove]");
    if (rm) {
      var id = rm.getAttribute("data-product-id");
      var a = cmpGet(); var i = a.indexOf(id);
      if (i >= 0) { a.splice(i, 1); cmpSet(a); if (a.length) openCompare(); else closeCompare(); }
    }
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeCompare(); });

  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(updateCmpUI);
})();
