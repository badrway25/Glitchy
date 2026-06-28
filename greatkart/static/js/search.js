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

    // Recent (localStorage) + popular (server categories) — premium empty state.
    var POP = (form.getAttribute("data-ac-popular") || "").split("|")
      .map(function (s) { return s.trim(); }).filter(Boolean).slice(0, 8);
    var recentLabel = form.getAttribute("data-ac-recent-label") || "Recent searches";
    var popLabel = form.getAttribute("data-ac-popular-label") || "Popular";
    var clearLabel = form.getAttribute("data-ac-clear-label") || "Clear";
    function getRecent(){ try { return JSON.parse(localStorage.getItem("gk_recent_searches") || "[]"); } catch (e) { return []; } }
    function saveRecent(q){
      q = (q || "").trim(); if (q.length < 2) return;
      try {
        var a = getRecent().filter(function (x) { return x.toLowerCase() !== q.toLowerCase(); });
        a.unshift(q); localStorage.setItem("gk_recent_searches", JSON.stringify(a.slice(0, 6)));
      } catch (e) {}
    }
    function chip(term){ return '<a class="ac-chip" href="/store/search/?keyword=' + encodeURIComponent(term) + '">' + esc(term) + '</a>'; }
    function renderEmpty(){
      var rec = getRecent(), html = "";
      if (rec.length) {
        html += '<div class="ac-sec"><div class="ac-sec-head"><span>' + esc(recentLabel) +
          '</span><button type="button" class="ac-clear-recent" data-ac-clear-recent>' + esc(clearLabel) +
          '</button></div><div class="ac-chips">' + rec.map(chip).join("") + '</div></div>';
      }
      if (POP.length) {
        html += '<div class="ac-sec"><div class="ac-sec-head"><span>' + esc(popLabel) +
          '</span></div><div class="ac-chips">' + POP.map(chip).join("") + '</div></div>';
      }
      if (!html) return false;
      panel.innerHTML = html; open(); items = [];
      var cr = panel.querySelector("[data-ac-clear-recent]");
      if (cr) cr.addEventListener("click", function (e) {
        e.preventDefault();
        try { localStorage.removeItem("gk_recent_searches"); } catch (_) {}
        if (!renderEmpty()) close();
      });
      return true;
    }

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
        el.addEventListener("click", function () { saveRecent(q); track("autocomplete_select", { q: q, name: el.getAttribute("data-ac-select") }); });
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
      if (q.length === 0) { if (!renderEmpty()) close(); return; }
      if (q.length < 2) { close(); return; }
      timer = setTimeout(function () { if (q !== lastQ) { lastQ = q; fetchSuggest(q); } }, 220);
    });

    // Persist the term to recent searches when the user searches.
    form.addEventListener("submit", function () { saveRecent(input.value); });

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
    input.addEventListener("focus", function () {
      var q = input.value.trim();
      if (q.length >= 2 && items.length) open();
      else if (q.length === 0) renderEmpty();
    });
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
