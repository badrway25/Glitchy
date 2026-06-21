/* Wishlist heart toggle — works on product cards and the PDP. Vanilla, CSRF-safe. */
(function () {
  "use strict";
  function cookie(n){ return (document.cookie.split("; ").find(c=>c.indexOf(n+"=")===0)||"").split("=")[1]||""; }

  function setCount(c){
    document.querySelectorAll("[data-wishlist-count]").forEach(function(el){
      el.textContent = c; el.style.display = c>0 ? "" : "none";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-wishlist-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        if (btn.dataset.busy) return; btn.dataset.busy = "1";
        var pid = btn.getAttribute("data-product-id");
        fetch("/wishlist/toggle/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken") },
          body: JSON.stringify({ product_id: pid })
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (typeof d.in_wishlist === "boolean") {
              btn.classList.toggle("is-active", d.in_wishlist);
              btn.setAttribute("aria-pressed", String(d.in_wishlist));
              var lbl = btn.getAttribute(d.in_wishlist ? "data-label-on" : "data-label-off");
              if (lbl) { var t = btn.querySelector("[data-wishlist-label]"); if (t) t.textContent = lbl; }
              setCount(d.count);
            }
          })
          .catch(function(){})
          .finally(function(){ delete btn.dataset.busy; });
      });
    });
  });
})();
