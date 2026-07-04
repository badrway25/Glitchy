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

/* PDP add-to-cart — AJAX + toast instead of yanking the shopper to /cart.
   Respects variant-guard (defaultPrevented), updates the navbar badge, disables the
   CTA while in flight. No-JS / fetch-failure: falls back to the normal POST redirect. */
(function () {
  "use strict";
  var form = document.getElementById("pdpForm");
  if (!form || !window.fetch) return;
  form.setAttribute("data-no-loader", "");          // fast AJAX — no G-loader flash

  function cartButtons() {
    return document.querySelectorAll('button[form="pdpForm"], #pdpForm button[type="submit"]');
  }
  function setBusy(b) {
    cartButtons().forEach(function (btn) { btn.disabled = b; btn.classList.toggle("is-busy", b); });
  }
  function updateCount(n) {
    document.querySelectorAll("[data-cart-count]").forEach(function (el) {
      el.textContent = n;
      el.classList.remove("badge-pop"); void el.offsetWidth; el.classList.add("badge-pop");
    });
  }

  form.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return;                 // variant-guard already blocked it
    e.preventDefault();
    setBusy(true);
    fetch(form.action, {
      method: "POST", credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      body: new FormData(form)
    }).then(function (r) { return r.json().then(function (d) { return { s: r.status, d: d }; }); })
      .then(function (res) {
        setBusy(false);
        if (res.d && res.d.ok) {
          updateCount(res.d.count);
          if (window.glToast) window.glToast(form.getAttribute("data-added-msg") || "Added to your bag", "success");
        } else if (window.glToast) {
          window.glToast(form.getAttribute("data-options-msg") || "Please choose your options first.", "warn");
        }
      })
      .catch(function () { setBusy(false); form.removeAttribute("data-no-loader"); form.submit(); });
  });
})();

/* "Ships to" country picker (PDP) — AJAX country switch that refreshes the honest shipping
   line in place. Lives inside #pdpForm, so it uses buttons + fetch (no nested form).
   JS-only affordance: without JS the toggle stays hidden and the honest line still renders. */
(function () {
  "use strict";
  var box = document.getElementById("shipsTo");
  if (!box || !window.fetch) return;
  var toggle = box.querySelector("[data-shipsto-toggle]");
  var menu = box.querySelector("[data-shipsto-menu]");
  var line = box.querySelector("[data-shipsto-line]");
  var endpoint = box.getAttribute("data-endpoint");
  if (!toggle || !menu || !endpoint) return;
  toggle.hidden = false;                      // JS available -> reveal the picker

  function csrf() {
    var i = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (i) return i.value;
    var m = document.cookie.match("(^|;)\s*csrftoken\s*=\s*([^;]+)");
    return m ? m.pop() : "";
  }
  function close(){ menu.hidden = true; toggle.setAttribute("aria-expanded","false"); }
  toggle.addEventListener("click", function (e) {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    toggle.setAttribute("aria-expanded", menu.hidden ? "false" : "true");
    if (!menu.hidden) { var a = menu.querySelector(".is-active") || menu.querySelector("button"); if (a) a.focus(); }
  });
  document.addEventListener("click", function (e) { if (!box.contains(e.target)) close(); });
  box.addEventListener("keydown", function (e) { if (e.key === "Escape") { close(); toggle.focus(); } });

  menu.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-country]");
    if (!btn) return;
    close();
    var fd = new FormData();
    fd.set("csrfmiddlewaretoken", csrf());
    fd.set("country", btn.getAttribute("data-country"));
    fd.set("subtotal", box.getAttribute("data-subtotal") || "0");
    line.style.opacity = ".45";
    fetch(endpoint, { method: "POST", credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }, body: fd })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok && d.localized) {
          line.textContent = d.localized.line_label;
          menu.querySelectorAll(".shipsto-opt").forEach(function (o) {
            var on = o.getAttribute("data-country") === d.country;
            o.classList.toggle("is-active", on);
            o.parentElement.setAttribute("aria-selected", on ? "true" : "false");
          });
        }
      })
      .catch(function () { /* silent — the honest static line stays */ })
      .finally(function () { line.style.opacity = ""; });
  });
})();

/* Intl phone prefix — swap the native select for a flag-SVG dropdown (progressive).
   The hidden-native select stays the source of truth (posted as phone_prefix). */
(function () {
  "use strict";
  var wrap = document.querySelector("[data-pfx]");
  var select = document.querySelector("[data-pfx-select]");
  if (!wrap || !select) return;
  var btn = wrap.querySelector("[data-pfx-toggle]");
  var menu = wrap.querySelector("[data-pfx-menu]");
  var flagHost = wrap.querySelector("[data-pfx-flag]");
  var dialHost = wrap.querySelector("[data-pfx-dial]");

  function optFor(code) {
    return menu.querySelector('.pfx-opt[data-code="' + code + '"]');
  }
  function syncFromSelect() {
    var opt = select.options[select.selectedIndex];
    if (!opt) return;
    var rich = optFor(opt.getAttribute("data-code"));
    if (rich) {
      flagHost.innerHTML = rich.querySelector(".pfx-flag").innerHTML;
      dialHost.textContent = rich.querySelector(".pfx-dial").textContent;
    }
  }
  select.hidden = true; select.setAttribute("tabindex", "-1");
  select.classList.add("pfx-native-hidden");
  wrap.hidden = false;
  syncFromSelect();

  function close(){ menu.hidden = true; btn.setAttribute("aria-expanded","false"); }
  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    btn.setAttribute("aria-expanded", menu.hidden ? "false" : "true");
    if (!menu.hidden) { var f = menu.querySelector(".pfx-opt"); if (f) f.focus(); }
  });
  document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
  wrap.addEventListener("keydown", function (e) { if (e.key === "Escape") { close(); btn.focus(); } });
  menu.addEventListener("click", function (e) {
    var o = e.target.closest && e.target.closest(".pfx-opt");
    if (!o) return;
    // update the REAL select (posted value) then mirror the button
    for (var i = 0; i < select.options.length; i++) {
      if (select.options[i].value === o.getAttribute("data-dial") &&
          select.options[i].getAttribute("data-code") === o.getAttribute("data-code")) {
        select.selectedIndex = i; break;
      }
    }
    syncFromSelect(); close(); btn.focus();
  });
})();
