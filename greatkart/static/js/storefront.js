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
