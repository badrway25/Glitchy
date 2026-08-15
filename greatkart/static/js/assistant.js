/* Contextual AI shopping assistant widget — vanilla JS, no deps.
   Answers come from the server (grounded in site context). Output is inserted as
   textContent only (never innerHTML) to avoid any injection. */
(function () {
  "use strict";
  var root = document.getElementById("aiAssistant");
  if (!root) return;

  var csrf = root.getAttribute("data-csrf") || "";
  var I18N = {};
  try { I18N = JSON.parse(document.getElementById("aiI18n").textContent); } catch (e) {}

  var toggle = document.getElementById("aiToggle");
  var panel = document.getElementById("aiPanel");
  var messages = document.getElementById("aiMessages");
  var quick = document.getElementById("aiQuick");
  var form = document.getElementById("aiForm");
  var input = document.getElementById("aiText");
  var loaded = false, busy = false;
  var dragMoved = false;   // set true by the drag module when a real drag (not a click) happened

  function clampPanel() {
    /* The panel is anchored above the draggable FAB — dragged to the top of the screen it
       used to open OFF-viewport (irrecoverable). Flip it below the FAB when there is no
       room above; if still out, reset the FAB to its default corner. */
    var panel = document.getElementById("aiPanel");
    if (!panel) return;
    panel.classList.remove("ai-panel--below");
    var r = panel.getBoundingClientRect();
    if (r.top < 8) {
      panel.classList.add("ai-panel--below");
      r = panel.getBoundingClientRect();
    }
    if (r.top < 8 || r.bottom > window.innerHeight - 8 && r.height < window.innerHeight - 16) {
      root.style.top = ""; root.style.left = "";
      root.style.right = "18px"; root.style.bottom = "18px";
      try { localStorage.removeItem("gl_ai_fab_pos"); } catch (e) {}
      panel.classList.remove("ai-panel--below");
    }
  }
  function open() {
    panel.hidden = false;
    root.classList.add("is-open");
    window.setTimeout(clampPanel, 20);
    toggle.setAttribute("aria-expanded", "true");
    if (!loaded) { loaded = true; loadSuggestions(); }
    setTimeout(function () { input.focus(); }, 60);
    try { window.dispatchEvent(new CustomEvent("analytics:assistant_open")); } catch (e) {}
  }
  function close() {
    root.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    setTimeout(function () { panel.hidden = true; }, 220);
  }
  toggle.addEventListener("click", function () {
    if (dragMoved) { dragMoved = false; return; }   // a drag just ended — don't toggle the panel
    root.classList.contains("is-open") ? close() : open();
  });
  root.querySelectorAll("[data-ai-close]").forEach(function (b) { b.addEventListener("click", close); });
  (function clampSavedPos() {
    var r = root.getBoundingClientRect();
    if (r.left < -8 || r.top < -8 || r.left > window.innerWidth - 40 || r.top > window.innerHeight - 40) {
      root.style.top = ""; root.style.left = "";
      root.style.right = "18px"; root.style.bottom = "18px";
      try { localStorage.removeItem("gl_ai_fab_pos"); } catch (e) {}
    }
  })();
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && root.classList.contains("is-open")) close(); });

  // External openers (e.g. "Need help choosing?" on the collections page) can open the
  // assistant and optionally pre-fill a prompt — without exposing anything sensitive.
  document.querySelectorAll("[data-assistant-open]").forEach(function (b) {
    b.addEventListener("click", function () {
      if (!root.classList.contains("is-open")) open();
      var prompt = b.getAttribute("data-assistant-prompt");
      if (prompt && input) { input.value = prompt; setTimeout(function () { input.focus(); }, 80); }
    });
  });

  /* ---- Draggable FAB (pointer events, persisted, viewport-clamped) ----
     Moves the ROOT container (#aiAssistant); the panel is anchored to it and follows.
     A movement threshold distinguishes a click (opens chat) from a drag (repositions). */
  (function setupDrag() {
    var DRAG_KEY = "aiFabPos.v1";
    var MARGIN = 10, THRESHOLD = 5;
    var down = false, startX = 0, startY = 0, originLeft = 0, originTop = 0;

    function isMobileSheet() { return window.matchMedia("(max-width:575.98px)").matches; }

    function clamp(left, top) {
      var w = root.offsetWidth, h = root.offsetHeight;
      left = Math.max(MARGIN, Math.min(left, window.innerWidth - w - MARGIN));
      top = Math.max(MARGIN, Math.min(top, window.innerHeight - h - MARGIN));
      return { left: left, top: top };
    }
    function applyPos(left, top) {
      var p = clamp(left, top);
      root.classList.add("has-custom-pos");
      root.style.left = p.left + "px";
      root.style.top = p.top + "px";
      return p;
    }
    function clearPos() {
      root.classList.remove("has-custom-pos");
      root.style.left = ""; root.style.top = "";
    }
    function restorePos() {
      if (isMobileSheet()) { clearPos(); return; }
      try {
        var p = JSON.parse(localStorage.getItem(DRAG_KEY));
        if (p && typeof p.left === "number" && typeof p.top === "number") applyPos(p.left, p.top);
      } catch (e) {}
    }

    toggle.addEventListener("pointerdown", function (e) {
      if ((e.button !== undefined && e.button !== 0) || isMobileSheet()) return;
      down = true; dragMoved = false;
      var r = root.getBoundingClientRect();
      originLeft = r.left; originTop = r.top;
      startX = e.clientX; startY = e.clientY;
      try { toggle.setPointerCapture(e.pointerId); } catch (_) {}
    });
    toggle.addEventListener("pointermove", function (e) {
      if (!down) return;
      var dx = e.clientX - startX, dy = e.clientY - startY;
      if (!dragMoved && Math.hypot(dx, dy) < THRESHOLD) return;
      dragMoved = true; root.classList.add("is-dragging");
      if (root.classList.contains("is-open")) close();   // collapse panel while repositioning
      applyPos(originLeft + dx, originTop + dy);
    });
    function endDrag(e) {
      if (!down) return; down = false;
      try { toggle.releasePointerCapture(e.pointerId); } catch (_) {}
      root.classList.remove("is-dragging");
      if (dragMoved) {
        var r = root.getBoundingClientRect();
        try { localStorage.setItem(DRAG_KEY, JSON.stringify({ left: r.left, top: r.top })); } catch (_) {}
      }
    }
    toggle.addEventListener("pointerup", endDrag);
    toggle.addEventListener("pointercancel", endDrag);

    // Double-click resets to the default corner position.
    toggle.addEventListener("dblclick", function () {
      clearPos();
      try { localStorage.removeItem(DRAG_KEY); } catch (_) {}
    });

    // Keep on-screen across viewport resizes / breakpoint changes.
    var rt;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        if (isMobileSheet()) { clearPos(); return; }
        if (root.classList.contains("has-custom-pos")) {
          var r = root.getBoundingClientRect();
          applyPos(r.left, r.top);
        }
      }, 120);
    });

    restorePos();
  })();


  function productCards(list) {
    /* Premium product cards — DOM building with textContent only (no injection). */
    var wrap = document.createElement("div");
    wrap.className = "ai-cards";
    list.slice(0, 3).forEach(function (p) {
      var a = document.createElement("a");
      a.className = "ai-card";
      a.href = p.url || "#";
      if (p.image) {
        var img = document.createElement("img");
        img.src = p.image; img.alt = p.name || ""; img.loading = "lazy";
        a.appendChild(img);
      }
      var body = document.createElement("div");
      body.className = "ai-card-body";
      var t = document.createElement("div");
      t.className = "ai-card-name"; t.textContent = p.name || "";
      var pr = document.createElement("div");
      pr.className = "ai-card-price";
      pr.textContent = (typeof p.price === "number") ? ("€ " + p.price.toFixed(2)) : "";
      body.appendChild(t); body.appendChild(pr);
      a.appendChild(body);
      wrap.appendChild(a);
    });
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
  }

  function bubble(role, text) {
    var el = document.createElement("div");
    el.className = "ai-msg ai-msg-" + role;
    var b = document.createElement("div");
    b.className = "ai-bubble";
    b.textContent = text;            // textContent = safe (no HTML)
    el.appendChild(b);
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }

  function loadSuggestions() {
    fetch("/assistant/suggestions/", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.greeting) bubble("assistant", d.greeting);
        var sub = document.getElementById("aiStatusSub");
        if (sub) sub.textContent = d.ai_ready ? sub.getAttribute("data-online")
                                              : sub.getAttribute("data-limited");
        if (d.questions && d.questions.length) {
          quick.hidden = false;
          d.questions.forEach(function (q) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "ai-chip";
            chip.textContent = q.text;
            chip.addEventListener("click", function () { quick.hidden = true; ask(q.text); });
            quick.appendChild(chip);
          });
        }
      })
      .catch(function () {});
  }

  function ask(text) {
    if (busy || !text.trim()) return;
    busy = true;
    quick.hidden = true;
    bubble("user", text);
    input.value = "";
    var thinking = bubble("assistant", I18N.thinking || "…");
    thinking.classList.add("is-thinking");
    try { window.dispatchEvent(new CustomEvent("analytics:assistant_question")); } catch (e) {}

    fetch("/assistant/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "Accept": "application/json" },
      body: JSON.stringify({ message: text })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        thinking.remove();
        var el = bubble("assistant", d.answer || (I18N.error || "Error"));
        if (d.products && d.products.length) productCards(d.products);
        if (d.message_id) addFeedback(el, d.message_id);
        if (d.can_contact_support) addSupport(d.contact_url);
      })
      .catch(function () {
        thinking.remove();
        bubble("assistant", I18N.error || "Something went wrong.");
      })
      .finally(function () { busy = false; });
  }

  function addFeedback(afterEl, messageId) {
    var row = document.createElement("div");
    row.className = "ai-fb";
    var label = document.createElement("span");
    label.className = "ai-fb-label";
    label.textContent = I18N.helpful || "Helpful?";
    row.appendChild(label);
    [["1", I18N.yes || "Yes"], ["0", I18N.no || "No"]].forEach(function (pair) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ai-fb-btn";
      btn.textContent = pair[1];
      btn.addEventListener("click", function () {
        fetch("/assistant/feedback/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({ message_id: messageId, helpful: pair[0] === "1" })
        }).catch(function () {});
        label.textContent = I18N.thanks || "Thanks!";
        row.querySelectorAll(".ai-fb-btn").forEach(function (b) { b.remove(); });
      });
      row.appendChild(btn);
    });
    afterEl.appendChild(row);
  }

  function addSupport(contactUrl) {
    if (messages.querySelector(".ai-support")) return;
    var box = document.createElement("div");
    box.className = "ai-support ai-msg ai-msg-assistant";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ai-support-btn btn btn-soft";
    btn.textContent = I18N.contactSupport || "Contact support";
    btn.addEventListener("click", function () { supportFlow(box); });
    box.appendChild(btn);
    /* Second route: the full contact page with the category pre-selected. The
       server decides the category — the shopper's words never travel in the URL. */
    if (contactUrl) {
      var link = document.createElement("a");
      link.className = "ai-support-link";
      link.href = contactUrl;
      link.textContent = I18N.contactPage || "Contact page";
      box.appendChild(link);
    }
    messages.appendChild(box);
    messages.scrollTop = messages.scrollHeight;
  }

  function supportFlow(box) {
    box.textContent = "";
    var p = document.createElement("div");
    p.className = "ai-bubble";
    p.textContent = I18N.emailPrompt || "Leave your email:";
    var f = document.createElement("form");
    f.className = "ai-support-form";
    var em = document.createElement("input");
    em.type = "email"; em.required = true; em.placeholder = "you@example.com"; em.className = "ai-support-email";
    var sb = document.createElement("button");
    sb.type = "submit"; sb.className = "btn btn-primary ai-support-send"; sb.textContent = I18N.send || "Send";
    f.appendChild(em); f.appendChild(sb);
    box.appendChild(p); box.appendChild(f);
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var lastUser = "";
      var us = messages.querySelectorAll(".ai-msg-user .ai-bubble");
      if (us.length) lastUser = us[us.length - 1].textContent;
      fetch("/assistant/support/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ email: em.value, message: lastUser || "Assistant support request" })
      }).then(function (r) { return r.json(); }).then(function () {
        box.textContent = "";
        var ok = document.createElement("div"); ok.className = "ai-bubble";
        ok.textContent = I18N.supportSent || "Sent."; box.appendChild(ok);
      }).catch(function () {});
    });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); ask(input.value); });
})();
