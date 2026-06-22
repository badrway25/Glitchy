/* Growth suite: outfit builder, notify-me, recommendation analytics. Vanilla, CSRF-safe. */
(function () {
  "use strict";
  function cookie(n){ return (document.cookie.split("; ").find(c=>c.indexOf(n+"=")===0)||"").split("=")[1]||""; }
  function track(name, meta){ if (window.gkTrack) window.gkTrack(name, meta || {}); }

  document.addEventListener("DOMContentLoaded", function () {
    // --- recommendation / outfit / collection view beacons ---
    if (document.querySelector("[data-outfit-view]")) track("outfit_view", {});
    document.querySelectorAll("[data-reco-view]").forEach(function () { track("recommendation_view", {}); });
    document.querySelectorAll("[data-reco-click]").forEach(function (a) {
      a.addEventListener("click", function () { track("recommendation_click", { id: a.getAttribute("data-reco-click") }); });
    });

    // --- outfit builder ---
    var builder = document.getElementById("outfitBuilder");
    if (builder) {
      var totalEl = document.getElementById("outfitTotal");
      var sym = (document.querySelector(".ctl-price") || {}).textContent || "";
      sym = (sym.match(/^\s*(\D+)/) || ["", "€"])[1].trim();
      function recompute() {
        var t = 0;
        builder.querySelectorAll('input[type="checkbox"]').forEach(function (c) {
          if (c.checked) t += parseFloat(c.getAttribute("data-outfit-price")) || 0;
        });
        if (totalEl) totalEl.textContent = sym + " " + t;
      }
      builder.addEventListener("change", recompute);
      recompute();

      var addBtn = document.getElementById("outfitAdd");
      if (addBtn) addBtn.addEventListener("click", function () {
        var ids = [];
        builder.querySelectorAll('input[type="checkbox"]').forEach(function (c) {
          if (c.checked) ids.push(c.value);
        });
        if (!ids.length) return;
        addBtn.disabled = true;
        fetch("/outfit/add/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken") },
          body: JSON.stringify({ product_ids: ids })
        }).then(function (r) { return r.json(); }).then(function (d) {
          var lbl = addBtn.querySelector("[data-outfit-add-label]");
          if (d.ok) {
            if (lbl) lbl.textContent = (addBtn.getAttribute("data-added-label") || "Added ✓");
            track("outfit_add_to_cart", { count: String(d.added) });
            setTimeout(function () { window.location = "/cart/"; }, 600);
          } else { addBtn.disabled = false; }
        }).catch(function () { addBtn.disabled = false; });
      });
    }

    // --- notify me (container is a <div>, not a <form>, to avoid nested-form HTML) ---
    document.querySelectorAll("[data-notify-form]").forEach(function (box) {
      var btn = box.querySelector("[data-notify-submit]");
      if (!btn) return;
      btn.addEventListener("click", function () {
        var msg = box.querySelector("[data-notify-msg]");
        var fd = new FormData();
        box.querySelectorAll("input").forEach(function (inp) {
          if (inp.type === "checkbox") { if (inp.checked) fd.append(inp.name, inp.value || "1"); }
          else fd.append(inp.name, inp.value);
        });
        btn.disabled = true;
        fetch(box.getAttribute("data-action"), {
          method: "POST",
          headers: { "X-CSRFToken": cookie("csrftoken") },
          body: fd
        }).then(function (r) { return r.json().then(function (d){ return { ok: r.ok, d: d }; }); })
          .then(function (res) {
            btn.disabled = false;
            if (msg) {
              msg.hidden = false;
              msg.textContent = res.d.message || (res.ok ? "Thanks!" : (box.getAttribute("data-err") || "Please check your details."));
              msg.className = "notify-msg " + (res.ok && res.d.ok ? "is-ok" : "is-err");
            }
            if (res.ok && res.d.ok) { var e = box.querySelector('input[type="email"]'); if (e) e.value = ""; track("notification_signup", {}); }
          }).catch(function () { btn.disabled = false; });
      });
    });
  });
})();
