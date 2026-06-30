/* Wishlist heart toggle — works on product cards and the PDP. Vanilla, CSRF-safe. */
(function () {
  "use strict";
  function cookie(n){ return (document.cookie.split("; ").find(c=>c.indexOf(n+"=")===0)||"").split("=")[1]||""; }

  function setCount(c){
    document.querySelectorAll("[data-wishlist-count]").forEach(function(el){
      el.textContent = c; el.style.display = c>0 ? "" : "none";
    });
  }

  // Event delegation so dynamically-injected hearts (e.g. Quick View drawer) work too.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-wishlist-toggle]");
    if (!btn) return;
    e.preventDefault(); e.stopPropagation();
    if (btn.dataset.busy) return; btn.dataset.busy = "1";
    // a brief "pop" micro-interaction (respects prefers-reduced-motion via CSS)
    btn.classList.remove("wish-pop"); void btn.offsetWidth; btn.classList.add("wish-pop");
    var pid = btn.getAttribute("data-product-id");
    fetch("/wishlist/toggle/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken") },
      body: JSON.stringify({ product_id: pid })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (typeof d.in_wishlist === "boolean") {
          document.querySelectorAll('[data-wishlist-toggle][data-product-id="' + pid + '"]').forEach(function (b) {
            b.classList.toggle("is-active", d.in_wishlist);
            b.setAttribute("aria-pressed", String(d.in_wishlist));
            var lbl = b.getAttribute(d.in_wishlist ? "data-label-on" : "data-label-off");
            if (lbl) { var t = b.querySelector("[data-wishlist-label]"); if (t) t.textContent = lbl; }
          });
          setCount(d.count);
          if (window.glToast) {
            var tmsg = btn.getAttribute(d.in_wishlist ? "data-toast-on" : "data-toast-off");
            if (tmsg) window.glToast(tmsg, "success");
          }
        }
      })
      .catch(function(){})
      .finally(function(){ delete btn.dataset.busy; });
  });
})();
