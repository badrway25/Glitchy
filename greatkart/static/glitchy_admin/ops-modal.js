/* Glitchy admin — premium operation loader for Printify actions.
 * Progressive enhancement: the ops forms are synchronous POST -> redirect. Without JS they
 * still work (Django messages). With JS, submitting shows a full-screen overlay with a spinner
 * and stepped progress that persists until the browser navigates on the server redirect.
 * Vanilla JS (no Alpine) to avoid Unfold's Alpine modal namespace. Reduced-motion safe. */
(function () {
  "use strict";
  var STEPS = {
    discover: ["Connecting to Printify", "Discovering shops", "Building report"],
    test: ["Connecting to Printify", "Checking credentials", "Building report"],
    dryrun: ["Connecting to Printify", "Reading products", "Simulating mapping", "Building report"],
    sync: ["Connecting to Printify", "Reading products", "Mapping catalog", "Updating local database", "Building report"],
    use: ["Selecting shop", "Saving"],
    paytest: ["Connecting to the payment provider", "Checking credentials (read-only)", "Building report"],
    default: ["Working with Printify", "Please wait"]
  };
  var TITLES = {
    discover: "Discovering shops…", test: "Testing connection…", dryrun: "Dry-run in progress…",
    sync: "Syncing products…", use: "Selecting shop…", paytest: "Testing connection…", default: "Working…"
  };

  function reduced() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function buildOverlay() {
    var ov = document.getElementById("gl-ops-overlay");
    if (ov) return ov;
    ov = document.createElement("div");
    ov.id = "gl-ops-overlay";
    ov.setAttribute("role", "status");
    ov.setAttribute("aria-live", "polite");
    ov.innerHTML =
      '<div class="gl-ops-card">' +
      '<div class="gl-ops-spinner" aria-hidden="true"></div>' +
      '<p class="gl-ops-title" id="gl-ops-title">Working…</p>' +
      '<p class="gl-ops-step" id="gl-ops-step"></p>' +
      '<ul class="gl-ops-steps" id="gl-ops-steps"></ul>' +
      "</div>";
    document.body.appendChild(ov);
    return ov;
  }

  function opFor(form) {
    var a = (form.getAttribute("action") || "");
    if (form.dataset.glOp) return form.dataset.glOp;
    if (a.indexOf("discover") > -1) return "discover";
    if (a.indexOf("test") > -1) return "test";
    if (a.indexOf("dry-run") > -1) return "dryrun";
    if (a.indexOf("sync-now") > -1) return "sync";
    if (a.indexOf("use-shop") > -1) return "use";
    return "default";
  }

  function run(form) {
    var op = opFor(form);
    var ov = buildOverlay();
    var steps = STEPS[op] || STEPS.default;
    document.getElementById("gl-ops-title").textContent = TITLES[op] || TITLES.default;
    var list = document.getElementById("gl-ops-steps");
    list.innerHTML = "";
    steps.forEach(function (s) {
      var li = document.createElement("li");
      li.textContent = s;
      list.appendChild(li);
    });
    ov.classList.add("gl-on");

    if (reduced()) {
      // no timed animation — mark all steps active statically
      Array.prototype.forEach.call(list.children, function (li) { li.classList.add("gl-active"); });
      document.getElementById("gl-ops-step").textContent = "Please wait…";
      return;
    }
    // pseudo-progress: advance through steps until the server redirect replaces the page
    var i = 0;
    function tick() {
      Array.prototype.forEach.call(list.children, function (li, idx) {
        li.classList.toggle("gl-done", idx < i);
        li.classList.toggle("gl-active", idx === i);
      });
      document.getElementById("gl-ops-step").textContent = steps[Math.min(i, steps.length - 1)] + "…";
      if (i < steps.length - 1) { i++; window.setTimeout(tick, 900); }
    }
    tick();
  }

  function wire() {
    var scopes = document.querySelectorAll(".gl-printify-ops, .gl-payment-ops");
    if (!scopes.length) return;
    Array.prototype.forEach.call(scopes, function (scope) {
      var forms = scope.querySelectorAll("form[method='post'], form[method='POST']");
      Array.prototype.forEach.call(forms, function (form) {
        form.addEventListener("submit", function () {
          // let the form submit normally; just show the loader over the round-trip
          try { run(form); } catch (e) { /* fail open: never block the submit */ }
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
