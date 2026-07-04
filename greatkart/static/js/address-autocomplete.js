/* Professional street autocomplete — custom prediction list over Google Places.
 *
 * Why custom (AutocompleteService + PlacesService) instead of the stock widget: full design
 * control (premium list, keyboard nav, i18n states) and real context filtering — predictions are
 * hard-restricted to the selected country and biased by the city/postal the shopper already
 * entered (destination fields come BEFORE the street in the form).
 *
 * Contract with the backend (server re-validates; these are hints, not trust):
 *   google_place_id / address_verified / address_validation_source hidden fields.
 * Any manual edit of the street or of a destination field resets the verification.
 * No Google key in this file; the loader script tag (template) carries the public
 * referrer-restricted browser key. Fail-open: without Google the form is plain manual entry.
 */
(function () {
  "use strict";

  var input, list, hint, placeIdEl, verifiedEl, sourceEl, okBadge, warnBadge, statusEl;
  var wired = false;
  var svc = null, details = null, session = null;
  var debounceT = null, items = [], active = -1, programmatic = false;

  function $(sel) { return document.querySelector(sel); }
  function t(key, fallback) {
    var host = $("#checkoutForm");
    return (host && host.getAttribute(key)) || fallback;
  }

  function grab() {
    input = $("#addressLine1");
    list = $("[data-addr-suggest]");
    hint = $("[data-addr-hint]");
    placeIdEl = $("[data-addr-placeid]");
    verifiedEl = $("[data-addr-verified]");
    sourceEl = $("[data-addr-source]");
    okBadge = $("[data-addr-badge-ok]");
    warnBadge = $("[data-addr-badge-warn]");
    statusEl = $("[data-addr-status]");
    return !!(input && list && placeIdEl);
  }

  function mode() { return (statusEl && statusEl.getAttribute("data-mode")) || "disabled"; }

  function setHint(msg) {
    if (!hint) return;
    if (msg) { hint.textContent = msg; hint.hidden = false; } else { hint.hidden = true; }
  }
  function closeList() {
    list.hidden = true; list.innerHTML = ""; items = []; active = -1;
    input.setAttribute("aria-expanded", "false");
  }
  function setVerified(on, source) {
    verifiedEl.value = on ? "true" : "";
    sourceEl.value = on ? (source || "google_places") : "";
    if (okBadge) okBadge.hidden = !on;
    if (warnBadge) warnBadge.hidden = on || mode() === "disabled";
  }
  function resetVerification() {
    if (!verifiedEl.value && !placeIdEl.value) return;
    placeIdEl.value = ""; setVerified(false);
  }

  // ---- context (country/state/city/postal live BEFORE the street) ----------------------
  function ctx() {
    var c = $("#countryInput"), city = $("#cityInput"), pc = $("#postalCodeInput");
    return {
      country: c && c.value ? c.value.toLowerCase() : "",
      city: city ? city.value.trim() : "",
      postal: pc ? pc.value.trim() : "",
    };
  }

  // ---- predictions ----------------------------------------------------------------------
  function predict(q) {
    var c = ctx();
    var req = { input: q, types: ["address"] };
    // bias with what the shopper already told us (kept out of the visible main text)
    var bias = [c.postal, c.city].filter(Boolean).join(" ");
    if (bias) req.input = q + ", " + bias;
    if (c.country) req.componentRestrictions = { country: c.country };
    if (session) req.sessionToken = session;
    svc.getPlacePredictions(req, function (preds, status) {
      if (status !== google.maps.places.PlacesServiceStatus.OK || !preds || !preds.length) {
        closeList();
        setHint(t("data-addr-none", "No suggestions — you can keep typing the full address."));
        return;
      }
      setHint("");
      render(preds.slice(0, 6));
    });
  }

  function render(preds) {
    list.innerHTML = ""; items = []; active = -1;
    preds.forEach(function (p, idx) {
      var li = document.createElement("li");
      li.className = "addr-opt"; li.setAttribute("role", "option"); li.id = "addrOpt" + idx;
      var main = (p.structured_formatting && p.structured_formatting.main_text) || p.description;
      var sec = (p.structured_formatting && p.structured_formatting.secondary_text) || "";
      li.innerHTML = '<span class="addr-opt-ic" aria-hidden="true"><i class="fa fa-map-marker-alt"></i></span>' +
        '<span class="addr-opt-txt"><span class="addr-opt-main"></span>' +
        '<span class="addr-opt-sec"></span></span>';
      li.querySelector(".addr-opt-main").textContent = main;
      li.querySelector(".addr-opt-sec").textContent = sec;
      li.addEventListener("mousedown", function (e) { e.preventDefault(); choose(idx); });
      list.appendChild(li);
      items.push({ el: li, pred: p });
    });
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function highlight(idx) {
    items.forEach(function (it, i) { it.el.classList.toggle("is-active", i === idx); });
    active = idx;
    input.setAttribute("aria-activedescendant", idx > -1 ? "addrOpt" + idx : "");
  }

  // ---- selection → Place Details → fill the form ----------------------------------------
  function comp(components, type, short) {
    var c = components.find(function (x) { return x.types.indexOf(type) > -1; });
    return c ? (short ? c.short_name : c.long_name) : "";
  }

  function choose(idx) {
    var it = items[idx];
    if (!it) return;
    closeList();
    input.classList.add("is-loading");
    details.getDetails({
      placeId: it.pred.place_id,
      fields: ["address_components", "place_id"],
      sessionToken: session || undefined,
    }, function (place, status) {
      input.classList.remove("is-loading");
      session = null;                       // token consumed
      if (status !== google.maps.places.PlacesServiceStatus.OK || !place || !place.address_components) {
        setHint(t("data-addr-none", "No suggestions — you can keep typing the full address."));
        return;
      }
      var ac = place.address_components;
      var route = comp(ac, "route"), num = comp(ac, "street_number");
      var city = comp(ac, "locality") || comp(ac, "postal_town") || comp(ac, "administrative_area_level_3");
      var state = comp(ac, "administrative_area_level_2", true) || comp(ac, "administrative_area_level_1", true);
      var postal = comp(ac, "postal_code");
      var cc = comp(ac, "country", true);

      programmatic = true;
      input.value = (route + " " + num).trim() || it.pred.description;
      var set = function (sel, v) { var el = $(sel); if (el && v) el.value = v; };
      set("#cityInput", city); set("#stateInput", state); set("#postalCodeInput", postal);
      var cSel = $("#countryInput");
      if (cSel && cc) { cSel.value = cc; cSel.dispatchEvent(new Event("change", { bubbles: true })); }
      programmatic = false;

      placeIdEl.value = place.place_id || it.pred.place_id;
      // "verified" only when the place actually carries the components an order needs
      var complete = !!(route && city && postal && cc);
      setVerified(complete, "google_places");
      if (!complete) setHint(t("data-addr-partial", "Suggestion applied — please complete the missing fields."));
    });
  }

  // ---- wiring -----------------------------------------------------------------------------
  function wire() {
    if (wired) return;                        // Google callback may fire after the no-JS boot
    wired = true;
    input.addEventListener("input", function () {
      if (programmatic) return;
      resetVerification();
      var q = input.value.trim();
      window.clearTimeout(debounceT);
      if (!svc) return;                      // Google not loaded -> plain manual input
      if (q.length < 3) { closeList(); setHint(q ? t("data-addr-min", "Type at least 3 characters…") : ""); return; }
      if (!session && google.maps.places.AutocompleteSessionToken) {
        session = new google.maps.places.AutocompleteSessionToken();
      }
      debounceT = window.setTimeout(function () { predict(q); }, 250);
    });
    input.addEventListener("keydown", function (e) {
      if (list.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); highlight(Math.min(active + 1, items.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); highlight(Math.max(active - 1, 0)); }
      else if (e.key === "Enter") { if (active > -1) { e.preventDefault(); choose(active); } }
      else if (e.key === "Escape") { closeList(); }
    });
    input.addEventListener("blur", function () { window.setTimeout(closeList, 150); });

    // destination edits invalidate a previous verification + refresh restriction context
    document.querySelectorAll("[data-addr-context]").forEach(function (el) {
      el.addEventListener("change", function () { if (!programmatic) resetVerification(); });
      el.addEventListener("input", function () { if (!programmatic) resetVerification(); });
    });

    // initial state: nothing verified on load (server-rendered restore stays manual)
    setVerified(false);
  }

  // Google JS callback (template loader) — also safe to call from tests with a stub.
  window.__glxAddrInit = function () {
    if (!grab()) return;
    try {
      svc = new google.maps.places.AutocompleteService();
      details = new google.maps.places.PlacesService(document.createElement("div"));
    } catch (e) { svc = null; }
    wire();
  };
  // Auth/network failure of the Google script → honest manual fallback.
  window.gm_authFailure = function () {
    if (!grab()) return;
    svc = null;
    setHint(t("data-addr-noapi", "Google Places is not available — enter the address manually."));
  };
  // No-Google page (key not configured): still wire the reset logic for the hidden contract.
  if (document.readyState !== "loading") { if (grab() && !window.google) wire(); }
  else document.addEventListener("DOMContentLoaded", function () { if (grab() && !window.google) wire(); });
})();
