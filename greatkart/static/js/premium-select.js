/*
 * Premium select — progressive enhancement for native <select> site-wide.
 *
 * Replaces the OS dropdown rectangle with an elegant rounded popup (icons,
 * hover, selected check, smooth open) while KEEPING the native <select> in the
 * DOM (visually hidden) so form submission and accessibility still work. Every
 * selection syncs the native value and dispatches `change` + `input`, so existing
 * handlers (country switcher auto-submit, shipping estimator) keep functioning.
 *
 * Opt out per element with `data-no-enhance`. Multi-selects are left native.
 */
(function () {
  "use strict";

  var CARET = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<polyline points="6 9 12 15 18 9"></polyline></svg>';
  var CHECK = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" ' +
    'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<polyline points="20 6 9 17 4 12"></polyline></svg>';

  var uid = 0;
  var openMenu = null;

  function closeOpen() {
    if (openMenu) openMenu.close();
  }

  function enhance(select) {
    if (select.multiple || select.dataset.no_enhance !== undefined ||
        select.hasAttribute("data-no-enhance") || select.closest(".pmsel")) {
      return;
    }
    uid += 1;
    var id = "pmsel" + uid;

    var wrap = document.createElement("div");
    wrap.className = "pmsel";

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pmsel-btn";
    btn.id = id + "-btn";
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    if (select.getAttribute("aria-label")) btn.setAttribute("aria-label", select.getAttribute("aria-label"));

    var label = document.createElement("span");
    label.className = "pmsel-label";
    var caret = document.createElement("span");
    caret.className = "pmsel-caret";
    caret.innerHTML = CARET;
    btn.appendChild(label);
    btn.appendChild(caret);

    var menu = document.createElement("ul");
    menu.className = "pmsel-menu";
    menu.id = id + "-menu";
    menu.setAttribute("role", "listbox");
    menu.hidden = true;

    var optEls = [];

    function syncLabel() {
      var o = select.options[select.selectedIndex];
      label.textContent = o ? o.textContent : "";
      label.classList.toggle("is-placeholder", !!(o && o.value === ""));
    }

    function buildOptions() {
      menu.innerHTML = "";
      optEls = [];
      Array.prototype.forEach.call(select.options, function (o, i) {
        var li = document.createElement("li");
        li.className = "pmsel-opt";
        li.setAttribute("role", "option");
        li.id = id + "-opt" + i;
        li.dataset.index = i;
        li.setAttribute("aria-selected", o.selected ? "true" : "false");
        if (o.disabled) li.setAttribute("aria-disabled", "true");
        var chk = document.createElement("span");
        chk.className = "pmsel-check";
        chk.innerHTML = CHECK;
        var txt = document.createElement("span");
        txt.className = "pmsel-opt-text";
        txt.textContent = o.textContent;
        li.appendChild(chk);
        li.appendChild(txt);
        if (!o.disabled) {
          li.addEventListener("click", function () { choose(i); });
        }
        menu.appendChild(li);
        optEls.push(li);
      });
    }

    var active = -1;
    function setActive(i) {
      if (i < 0 || i >= optEls.length) return;
      if (active >= 0 && optEls[active]) optEls[active].classList.remove("is-active");
      active = i;
      optEls[active].classList.add("is-active");
      btn.setAttribute("aria-activedescendant", optEls[active].id);
      optEls[active].scrollIntoView({ block: "nearest" });
    }

    function choose(i) {
      if (i < 0 || i >= select.options.length || select.options[i].disabled) return;
      select.selectedIndex = i;
      optEls.forEach(function (el, idx) { el.setAttribute("aria-selected", idx === i ? "true" : "false"); });
      syncLabel();
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
      close();
      btn.focus();
    }

    function open() {
      if (openMenu && openMenu !== api) openMenu.close();
      menu.hidden = false;
      wrap.classList.add("is-open");
      btn.setAttribute("aria-expanded", "true");
      openMenu = api;
      setActive(select.selectedIndex >= 0 ? select.selectedIndex : 0);
    }
    function close() {
      menu.hidden = true;
      wrap.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
      if (active >= 0 && optEls[active]) optEls[active].classList.remove("is-active");
      active = -1;
      if (openMenu === api) openMenu = null;
    }
    var api = { close: close };

    btn.addEventListener("click", function (e) {
      e.preventDefault();
      if (menu.hidden) open(); else close();
    });

    btn.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (menu.hidden) { open(); return; }
      }
      if (menu.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(Math.min(active + 1, optEls.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(active - 1, 0)); }
      else if (e.key === "Home") { e.preventDefault(); setActive(0); }
      else if (e.key === "End") { e.preventDefault(); setActive(optEls.length - 1); }
      else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(active); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "Tab") { close(); }
      else if (e.key.length === 1) {
        // simple type-ahead
        var ch = e.key.toLowerCase();
        for (var k = 1; k <= optEls.length; k++) {
          var idx = (Math.max(active, 0) + k) % optEls.length;
          if ((select.options[idx].textContent || "").trim().toLowerCase().indexOf(ch) === 0) {
            setActive(idx); break;
          }
        }
      }
    });

    // Build + insert. Keep the native select inside (hidden) for submission.
    buildOptions();
    syncLabel();
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(btn);
    wrap.appendChild(menu);
    wrap.appendChild(select);
    select.classList.add("pmsel-native");
    select.setAttribute("tabindex", "-1");
    select.setAttribute("aria-hidden", "true");

    // Keep label in sync if external code changes the value programmatically.
    select.addEventListener("change", function () {
      if (menu.hidden) syncLabel();
    });
  }

  function init() {
    document.querySelectorAll("select").forEach(enhance);
  }

  // Close any open menu on outside click / Escape / resize.
  document.addEventListener("click", function (e) {
    if (openMenu && !e.target.closest(".pmsel")) closeOpen();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeOpen();
  });
  window.addEventListener("resize", closeOpen);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  // Expose for dynamically-injected selects.
  window.enhanceSelects = init;
})();
