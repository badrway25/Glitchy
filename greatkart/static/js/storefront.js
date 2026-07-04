/* First-party storefront analytics beacons + announcement dismiss. Vanilla, tiny. */
(function () {
  "use strict";

  function cookie(name) {
    return (document.cookie.split("; ").find(function (c) { return c.indexOf(name + "=") === 0; }) || "")
      .split("=")[1] || "";
  }

  // Public, fire-and-forget event tracker (no PII).
  window.gkTrack = function (name, meta) {
    try {
      fetch("/storefront/event/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken") },
        body: JSON.stringify({ name: name, path: location.pathname, meta: meta || {} }),
        keepalive: true,
      }).catch(function () {});
    } catch (e) {}
  };

  document.addEventListener("DOMContentLoaded", function () {
    // PDP product_view
    var pdp = document.querySelector("[data-track-product]");
    if (pdp) window.gkTrack("product_view", { id: pdp.getAttribute("data-track-product") });

    // search no-results
    if (document.querySelector("[data-track-no-results]")) {
      window.gkTrack("search_no_results", { q: document.querySelector("[data-track-no-results]").getAttribute("data-track-no-results") });
    }

    // add-to-cart (any add_cart form)
    document.querySelectorAll('form[action*="add_cart"]').forEach(function (f) {
      f.addEventListener("submit", function () { window.gkTrack("add_to_cart", {}); });
    });

    // begin checkout (link/button to checkout)
    document.querySelectorAll('a[href*="checkout"]').forEach(function (a) {
      a.addEventListener("click", function () { window.gkTrack("begin_checkout", {}); });
    });

    // size guide open
    document.querySelectorAll("[data-size-guide-open]").forEach(function (b) {
      b.addEventListener("click", function () { window.gkTrack("size_guide_open", {}); });
    });

    // assistant events (dispatched by assistant.js)
    window.addEventListener("analytics:assistant_open", function () { window.gkTrack("assistant_open", {}); });
    window.addEventListener("analytics:assistant_question", function () { window.gkTrack("assistant_question", {}); });

    // FAQ accordions (PDP 'Good to know' + general FAQ page)
    document.querySelectorAll("[data-faq] .faq-q").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var open = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!open));
        btn.closest(".faq-item").classList.toggle("is-open", !open);
      });
    });

    // FAQ page search filter
    var faqSearch = document.getElementById("faqSearch");
    if (faqSearch) {
      faqSearch.addEventListener("input", function () {
        var q = faqSearch.value.trim().toLowerCase();
        document.querySelectorAll("[data-faq-item]").forEach(function (it) {
          var hit = it.getAttribute("data-faq-text").indexOf(q) !== -1;
          it.style.display = hit ? "" : "none";
        });
        document.querySelectorAll("[data-faq-group]").forEach(function (g) {
          var any = g.querySelectorAll('[data-faq-item]:not([style*="none"])').length;
          g.style.display = any ? "" : "none";
        });
      });
    }

    // announcement dismiss (remember per id)
    var bar = document.getElementById("announceBar");
    if (bar) {
      var id = "announce_dismissed_" + bar.getAttribute("data-id");
      if (localStorage.getItem(id)) { bar.style.display = "none"; }
      var close = bar.querySelector("[data-announce-close]");
      if (close) close.addEventListener("click", function () {
        bar.style.display = "none";
        try { localStorage.setItem(id, "1"); } catch (e) {}
      });
    }
  });
})();

/* Footer newsletter — inline AJAX success (endpoint already returns JSON for XHR).
   Before: full page reload via redirect, losing scroll position. No-JS: same old POST. */
(function () {
  "use strict";
  var form = document.querySelector("[data-newsletter]");
  if (!form || !window.fetch) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = form.querySelector(".news-btn");
    if (btn) btn.disabled = true;
    fetch(form.action, {
      method: "POST", credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      body: new FormData(form)
    }).then(function (r) { return r.json().then(function (d) { return d; }); })
      .then(function (d) {
        if (d && d.ok) {
          if (btn) { btn.textContent = form.getAttribute("data-done-label") || "✓"; }
          var input = form.querySelector(".news-input");
          if (input) { input.value = ""; input.blur(); }
          if (window.glToast) window.glToast(
            d.created ? form.getAttribute("data-ok-msg") : form.getAttribute("data-dup-msg"),
            d.created ? "success" : "info");
        } else {
          if (btn) btn.disabled = false;
          if (window.glToast) window.glToast(form.getAttribute("data-err-msg") || "Invalid email", "warn");
        }
      })
      .catch(function () { if (btn) btn.disabled = false; form.submit(); });
  });
})();
