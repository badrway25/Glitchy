/* Premium fashion rebrand — lightweight, dependency-free enhancements.
   Reveal-on-scroll (IntersectionObserver), native lazy images, add-to-cart
   button feedback. Respects prefers-reduced-motion. ~1.5KB. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  // Enable reveal styling only when JS runs (content stays visible without JS).
  document.documentElement.classList.add("js-anim");

  ready(function () {
    /* 1. Reveal-on-scroll: auto-tag common content blocks, then observe. */
    var sel = ".home-section, .lux-feature, .lux-strip, .pdp-card, .reviews-card, " +
              ".summary-card, .dash-card, .p-card, .product-card, .edit-card";
    var nodes = Array.prototype.slice.call(document.querySelectorAll(sel));
    nodes.forEach(function (n) {
      if (!n.hasAttribute("data-reveal")) n.setAttribute("data-reveal", "");
    });
    function revealAll() { nodes.forEach(function (n) { n.classList.add("is-visible"); }); }

    if (reduce || !("IntersectionObserver" in window)) {
      revealAll();
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
            io.unobserve(e.target);
          }
        });
      }, { threshold: 0.06, rootMargin: "0px 0px -40px 0px" });
      nodes.forEach(function (n) { io.observe(n); });
      // Safety net: never leave content hidden (slow scroll / capture / odd cases).
      window.addEventListener("load", function () { setTimeout(revealAll, 1600); });
    }

    /* 2. Native lazy-loading for product imagery (no layout work, just a hint). */
    document.querySelectorAll(".p-media img, .product-card img, .media-skeleton img")
      .forEach(function (img) {
        if (!img.hasAttribute("loading")) img.setAttribute("loading", "lazy");
        if (!img.hasAttribute("decoding")) img.setAttribute("decoding", "async");
      });

    /* 3. Add-to-cart: subtle pressed/loading feedback (form posts then navigates). */
    document.querySelectorAll('form[action*="add_cart"]').forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector('button[type="submit"]');
        if (btn && !btn.disabled) {
          btn.dataset._label = btn.innerHTML;
          btn.innerHTML = '<i class="fas fa-circle-notch fa-spin mr-2"></i> ' +
            (btn.textContent.trim() || document.body.getAttribute("data-adding-label") || "Adding…");
          btn.style.opacity = ".85";
        }
      });
    });
  });
})();

/* Deep upgrade: mobile drawers (filters + nav), accessible + body-scroll lock. */
(function () {
  "use strict";
  function ready(fn){ if(document.readyState!=="loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  function makeDrawer(panel, openers, opts){
    if(!panel) return;
    var backdrop = document.createElement("div");
    backdrop.className = opts.backdropClass;
    document.body.appendChild(backdrop);
    var lastFocus = null, isOpen = false;
    panel.setAttribute("role","dialog");
    panel.setAttribute("aria-modal","true");
    function setExpanded(v){ openers.forEach(function(o){ if(o) o.setAttribute("aria-expanded", v ? "true" : "false"); }); }
    function open(){
      lastFocus = document.activeElement;
      isOpen = true;
      panel.classList.add(opts.openClass);
      backdrop.classList.add("is-open");
      document.body.style.overflow="hidden";
      setExpanded(true);
      var f = panel.querySelector("a,button,input,select"); if(f) f.focus();
    }
    function close(){
      if(!isOpen) return;
      isOpen = false;
      panel.classList.remove(opts.openClass);
      backdrop.classList.remove("is-open");
      document.body.style.overflow="";
      setExpanded(false);
      if(lastFocus && lastFocus.focus) lastFocus.focus();   // restore focus to the opener
    }
    openers.forEach(function(o){ o && o.addEventListener("click", function(e){ e.preventDefault(); open(); }); });
    backdrop.addEventListener("click", close);
    // Delegated: works for close buttons added AFTER makeDrawer (e.g. the X).
    panel.addEventListener("click", function(e){
      if (e.target.closest && e.target.closest("[data-drawer-close]")) { e.preventDefault(); close(); }
    });
    document.addEventListener("keydown", function(e){ if(e.key==="Escape" && isOpen) close(); });
    // keep Tab inside the open drawer (simple focus trap)
    panel.addEventListener("keydown", function(e){
      if(e.key!=="Tab" || !isOpen) return;
      var items = panel.querySelectorAll("a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex='-1'])");
      if(!items.length) return;
      var first=items[0], last=items[items.length-1];
      if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); }
      else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); }
    });
    return { open: open, close: close };
  }

  ready(function(){
    /* Mobile nav drawer — reuse the existing Bootstrap toggler button. */
    var nav = document.getElementById("navbarMain");
    var toggler = document.querySelector(".navbar-toggler");
    if(nav && toggler){
      // stop Bootstrap collapse from also firing
      toggler.removeAttribute("data-toggle");
      var navDrawer = makeDrawer(nav, [toggler], {backdropClass:"nav-backdrop", openClass:"drawer-open"});
      // add a close button into the drawer
      if(!nav.querySelector(".drawer-close")){
        var c=document.createElement("button"); c.className="drawer-close"; c.setAttribute("aria-label", document.body.getAttribute("data-close-label") || "Close menu");
        c.setAttribute("data-drawer-close",""); c.innerHTML="&times;"; c.style.fontSize="1.8rem";
        nav.insertBefore(c, nav.firstChild);
      }
      // close drawer when a nav link is tapped
      nav.querySelectorAll(".nav-link, .dropdown-item").forEach(function(l){
        l.addEventListener("click", function(){ if(window.innerWidth<992) navDrawer.close(); });
      });
    }

    /* Mobile shop filter drawer */
    var aside = document.querySelector(".shop-aside");
    var openBtn = document.querySelector("[data-open-filters]");
    if(aside && openBtn){
      makeDrawer(aside, [openBtn], {backdropClass:"filter-backdrop", openClass:"is-open"});
    }

    /* Collapsible filter sections (premium) */
    document.querySelectorAll(".filter-section .filter-head[data-collapsible]").forEach(function(h){
      h.addEventListener("click", function(){ h.closest(".filter-section").classList.toggle("is-collapsed"); });
    });
  });
})();
