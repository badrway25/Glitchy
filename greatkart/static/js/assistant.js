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

  function open() {
    panel.hidden = false;
    root.classList.add("is-open");
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
    root.classList.contains("is-open") ? close() : open();
  });
  root.querySelectorAll("[data-ai-close]").forEach(function (b) { b.addEventListener("click", close); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && root.classList.contains("is-open")) close(); });

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
        if (d.message_id) addFeedback(el, d.message_id);
        if (d.can_contact_support) addSupport();
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

  function addSupport() {
    if (messages.querySelector(".ai-support")) return;
    var box = document.createElement("div");
    box.className = "ai-support ai-msg ai-msg-assistant";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ai-support-btn btn btn-soft";
    btn.textContent = I18N.contactSupport || "Contact support";
    btn.addEventListener("click", function () { supportFlow(box); });
    box.appendChild(btn);
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
