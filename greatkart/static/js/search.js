/* Premium search autocomplete — debounced, keyboard-navigable, analytics-aware. */
(function () {
  "use strict";
  function esc(s){ var d=document.createElement("div"); d.textContent=s==null?"":String(s); return d.innerHTML; }
  function track(name, meta){ if (window.gkTrack) window.gkTrack(name, meta || {}); }

  document.querySelectorAll("[data-autocomplete]").forEach(function (form) {
    var input = form.querySelector('input[name="keyword"]');
    var panel = form.querySelector(".ac-panel");
    var url = form.getAttribute("data-ac-url");
    var viewAllLabel = form.getAttribute("data-ac-viewall") || "View all results";
    var emptyLabel = form.getAttribute("data-ac-empty") || "No matches.";
    if (!input || !panel || !url) return;
    var timer = null, active = -1, items = [], lastQ = "";

    function close(){ panel.classList.remove("is-open"); input.setAttribute("aria-expanded","false"); active = -1; }
    function open(){ panel.classList.add("is-open"); input.setAttribute("aria-expanded","true"); }

    function render(data){
      var q = data.query || "";
      var rows = (data.results || []);
      if (!rows.length){ panel.innerHTML = '<div class="ac-empty">'+esc(emptyLabel)+'</div>'; open(); items=[]; return; }
      var html = rows.map(function (r) {
        var img = r.image ? '<img class="ac-thumb" src="'+esc(r.image)+'" alt="" loading="lazy">' : '<span class="ac-thumb"></span>';
        return '<a class="ac-item" role="option" href="'+esc(r.url)+'" data-ac-select="'+esc(r.name)+'">'+img+
          '<span class="ac-meta"><span class="ac-name">'+esc(r.name)+'</span>'+
          (r.category?'<span class="ac-cat">'+esc(r.category)+'</span>':'')+'</span>'+
          '<span class="ac-price">'+esc(r.price)+'</span></a>';
      }).join("");
      html += '<a class="ac-all" href="/store/search/?keyword='+encodeURIComponent(q)+'">'+esc(viewAllLabel)+' →</a>';
      panel.innerHTML = html; open(); active = -1;
      items = Array.prototype.slice.call(panel.querySelectorAll(".ac-item"));
      items.forEach(function (el) {
        el.addEventListener("click", function () { track("autocomplete_select", { q: q, name: el.getAttribute("data-ac-select") }); });
      });
    }

    function fetchSuggest(q){
      fetch(url + "?q=" + encodeURIComponent(q), { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (input.value.trim() === q) render(d); })
        .catch(function () {});
    }

    var clearBtn = form.querySelector("[data-search-clear]");
    function syncClear(){ if (clearBtn) clearBtn.hidden = !input.value.length; }
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        input.value = ""; lastQ = ""; close(); syncClear(); input.focus();
      });
    }

    input.addEventListener("input", function () {
      var q = input.value.trim();
      syncClear();
      if (timer) clearTimeout(timer);
      if (q.length < 2) { close(); return; }
      timer = setTimeout(function () { if (q !== lastQ) { lastQ = q; fetchSuggest(q); } }, 220);
    });

    input.addEventListener("keydown", function (e) {
      if (!panel.classList.contains("is-open")) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        active += (e.key === "ArrowDown" ? 1 : -1);
        if (active < 0) active = items.length - 1;
        if (active >= items.length) active = 0;
        items.forEach(function (el, i) { el.classList.toggle("is-active", i === active); });
        items[active].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        if (active >= 0 && items[active]) { e.preventDefault(); items[active].click(); window.location = items[active].href; }
      } else if (e.key === "Escape") { close(); }
    });

    document.addEventListener("click", function (e) { if (!form.contains(e.target)) close(); });
    input.addEventListener("focus", function () { if (items.length && input.value.trim().length >= 2) open(); });
  });

  // Mobile search overlay (top sheet)
  var overlay = document.getElementById("mobileSearch");
  if (overlay) {
    var mInput = overlay.querySelector('input[name="keyword"]');
    function openOverlay() {
      overlay.hidden = false;
      document.body.style.overflow = "hidden";
      requestAnimationFrame(function () {
        overlay.classList.add("is-open");
        if (mInput) mInput.focus();
      });
    }
    function closeOverlay() {
      overlay.classList.remove("is-open");
      document.body.style.overflow = "";
      setTimeout(function () { overlay.hidden = true; }, 250);
    }
    document.querySelectorAll("[data-mobile-search-open]").forEach(function (b) {
      b.addEventListener("click", openOverlay);
    });
    overlay.querySelectorAll("[data-mobile-search-close]").forEach(function (b) {
      b.addEventListener("click", closeOverlay);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && overlay.classList.contains("is-open")) closeOverlay();
    });
  }
})();
