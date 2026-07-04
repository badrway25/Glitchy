/* Unified Google checkout autocomplete — ONE reusable prediction controller, FOUR fields.
 *
 *   city     → real localities restricted to the selected country ((cities) collection)
 *   state    → provinces/regions ((regions) collection, filtered to administrative areas)
 *   postal   → real postal codes ((regions) collection, filtered to postal_code)
 *   street   → addresses biased by everything above (existing behaviour, now context-richer)
 *
 * HONEST CAP RULE: the postal code is auto-filled ONLY when Google returns a postal_code
 * component on the selected place (single-CAP towns; a full street selection). Multi-CAP
 * cities (Milano, Roma…) get the professional hint "complete it with the street" — a CAP is
 * never guessed.
 *
 * Contract unchanged: google_place_id / address_verified / address_validation_source hidden
 * fields (server re-validates; strict never trusts them alone). Editing any location field
 * resets the street verification. No key here (the loader carries the public browser key),
 * no input ever logged, fail-open to plain manual entry.
 */
(function () {
  "use strict";

  var svc = null, details = null, session = null, wired = false;
  var placeIdEl, verifiedEl, sourceEl, okBadge, warnBadge, statusEl;
  var controllers = {};

  function $(sel) { return document.querySelector(sel); }
  function t(key, fallback) {
    var host = $("#checkoutForm");
    return (host && host.getAttribute(key)) || fallback;
  }
  function comp(components, type, short) {
    var c = (components || []).find(function (x) { return x.types.indexOf(type) > -1; });
    return c ? (short ? c.short_name : c.long_name) : "";
  }
  function countryCode() {
    var c = $("#countryInput");
    return c && c.value ? c.value.toLowerCase() : "";
  }
  function token() {
    if (!session && window.google && google.maps.places.AutocompleteSessionToken) {
      session = new google.maps.places.AutocompleteSessionToken();
    }
    return session;
  }

  // ---- street verification state (shared) -------------------------------------------------
  function mode() { return (statusEl && statusEl.getAttribute("data-mode")) || "disabled"; }
  function setVerified(on, source) {
    if (!verifiedEl) return;
    verifiedEl.value = on ? "true" : "";
    sourceEl.value = on ? (source || "google_places") : "";
    if (okBadge) okBadge.hidden = !on;
    if (warnBadge) warnBadge.hidden = on || mode() === "disabled";
  }
  function resetVerification() {
    if (!placeIdEl) return;
    if (!verifiedEl.value && !placeIdEl.value) return;
    placeIdEl.value = "";
    setVerified(false);
  }

  // ---- generic prediction field controller ------------------------------------------------
  function PredictionField(cfg) {
    var self = { programmatic: false };
    var input = cfg.input, list = cfg.list, hint = cfg.hint;
    var items = [], active = -1, debounceT = null;

    function setHint(msg) {
      if (!hint) return;
      if (msg) { hint.textContent = msg; hint.hidden = false; } else { hint.hidden = true; }
    }
    self.setHint = setHint;
    function close() {
      list.hidden = true; list.innerHTML = ""; items = []; active = -1;
      input.setAttribute("aria-expanded", "false");
    }
    function highlight(idx) {
      items.forEach(function (it, i) { it.el.classList.toggle("is-active", i === idx); });
      active = idx;
    }
    function render(preds) {
      list.innerHTML = ""; items = []; active = -1;
      preds.forEach(function (p) {
        var li = document.createElement("li");
        li.className = "addr-opt"; li.setAttribute("role", "option");
        li.innerHTML = '<span class="addr-opt-ic" aria-hidden="true"><i class="fa ' + cfg.icon + '"></i></span>' +
          '<span class="addr-opt-txt"><span class="addr-opt-main"></span><span class="addr-opt-sec"></span></span>';
        li.querySelector(".addr-opt-main").textContent = cfg.formatMain(p);
        li.querySelector(".addr-opt-sec").textContent = cfg.formatSec(p);
        var entry = { el: li, pred: p };
        li.addEventListener("mousedown", function (e) { e.preventDefault(); choose(items.indexOf(entry)); });
        list.appendChild(li);
        items.push(entry);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
    function choose(idx) {
      var it = items[idx];
      if (!it) return;
      close();
      input.classList.add("is-loading");
      details.getDetails({
        placeId: it.pred.place_id,
        fields: ["address_components", "place_id"],
        sessionToken: token() || undefined,
      }, function (place, status) {
        input.classList.remove("is-loading");
        session = null;
        if (status !== google.maps.places.PlacesServiceStatus.OK || !place) {
          setHint(t("data-addr-none", "No suggestions."));
          return;
        }
        cfg.onSelect(place, it.pred, { setHint: setHint });
      });
    }
    input.addEventListener("input", function () {
      if (self.programmatic) return;
      if (cfg.onEdit) cfg.onEdit();
      var q = input.value.trim();
      window.clearTimeout(debounceT);
      if (!svc) return;
      if (q.length < cfg.minChars) {
        close();
        setHint(q ? t("data-addr-min", "Type at least a few characters…") : "");
        return;
      }
      debounceT = window.setTimeout(function () {
        var req = cfg.buildRequest(q);
        req.sessionToken = token() || undefined;
        svc.getPlacePredictions(req, function (preds, status) {
          if (status !== google.maps.places.PlacesServiceStatus.OK || !preds || !preds.length) {
            close(); setHint(t("data-addr-none", "No suggestions.")); return;
          }
          var ok = preds.filter(cfg.acceptPrediction).slice(0, 6);
          if (!ok.length) { close(); setHint(t("data-addr-none", "No suggestions.")); return; }
          setHint("");
          render(ok);
        });
      }, 250);
    });
    input.addEventListener("keydown", function (e) {
      if (list.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); highlight(Math.min(active + 1, items.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); highlight(Math.max(active - 1, 0)); }
      else if (e.key === "Enter") { if (active > -1) { e.preventDefault(); choose(active); } }
      else if (e.key === "Escape") { close(); }
    });
    input.addEventListener("blur", function () { window.setTimeout(close, 150); });
    self.fill = function (value) {
      if (!value) return;
      self.programmatic = true; input.value = value; self.programmatic = false;
    };
    self.input = input;
    return self;
  }

  // ---- field wiring -------------------------------------------------------------------------
  function structMain(p) { return (p.structured_formatting && p.structured_formatting.main_text) || p.description; }
  function structSec(p) { return (p.structured_formatting && p.structured_formatting.secondary_text) || ""; }
  function restrict(req) {
    var cc = countryCode();
    if (cc) req.componentRestrictions = { country: cc };
    return req;
  }

  // HONEST CAP: only fill from a REAL postal_code component; multi-CAP places → hint.
  function maybeFillPostal(place) {
    var postal = comp(place.address_components, "postal_code");
    if (postal) {
      controllers.postal.fill(postal);
      controllers.postal.setHint("");
      return true;
    }
    controllers.postal.setHint(t("data-addr-cap-street",
      "Postal code not unique here — it completes automatically when you pick the street."));
    return false;
  }

  function wireAll() {
    if (wired) return;
    wired = true;

    // CITY — real localities in the selected country
    controllers.city = PredictionField({
      input: $("#cityInput"), list: $("[data-city-suggest]"), hint: $("[data-city-hint]"),
      icon: "fa-city", minChars: 2,
      buildRequest: function (q) { return restrict({ input: q, types: ["(cities)"] }); },
      acceptPrediction: function () { return true; },
      formatMain: structMain, formatSec: structSec,
      onEdit: resetVerification,
      onSelect: function (place, pred) {
        var ac = place.address_components;
        controllers.city.fill(comp(ac, "locality") || comp(ac, "postal_town") || structMain(pred));
        var state = comp(ac, "administrative_area_level_2", true) || comp(ac, "administrative_area_level_1", true);
        if (state) controllers.state.fill(state);
        var cc = comp(ac, "country", true);
        var cSel = $("#countryInput");
        if (cSel && cc && cSel.value !== cc) { cSel.value = cc; cSel.dispatchEvent(new Event("change", { bubbles: true })); }
        resetVerification();                 // context changed → street must be re-picked
        maybeFillPostal(place);
      },
    });

    // STATE / PROVINCE / REGION — administrative areas in the selected country
    controllers.state = PredictionField({
      input: $("#stateInput"), list: $("[data-state-suggest]"), hint: $("[data-state-hint]"),
      icon: "fa-map", minChars: 2,
      buildRequest: function (q) { return restrict({ input: q, types: ["(regions)"] }); },
      acceptPrediction: function (p) {
        return p.types.some(function (ty) {
          return ty === "administrative_area_level_1" || ty === "administrative_area_level_2" ||
                 ty === "administrative_area_level_3" || ty === "locality";
        });
      },
      formatMain: structMain, formatSec: structSec,
      onEdit: resetVerification,
      onSelect: function (place, pred) {
        var ac = place.address_components;
        controllers.state.fill(
          comp(ac, "administrative_area_level_2", true) ||
          comp(ac, "administrative_area_level_1", true) || structMain(pred));
        resetVerification();
      },
    });

    // POSTAL CODE — real postal codes, biased by the city already entered
    controllers.postal = PredictionField({
      input: $("#postalCodeInput"), list: $("[data-postal-suggest]"), hint: $("[data-postal-hint]"),
      icon: "fa-envelope", minChars: 2,
      buildRequest: function (q) {
        var city = $("#cityInput").value.trim();
        return restrict({ input: city ? q + " " + city : q, types: ["(regions)"] });
      },
      acceptPrediction: function (p) { return p.types.indexOf("postal_code") > -1; },
      formatMain: structMain, formatSec: structSec,
      onEdit: resetVerification,
      onSelect: function (place, pred) {
        var ac = place.address_components;
        controllers.postal.fill(comp(ac, "postal_code") || structMain(pred));
        var city = comp(ac, "locality") || comp(ac, "postal_town");
        if (city && !$("#cityInput").value.trim()) controllers.city.fill(city);
        var state = comp(ac, "administrative_area_level_2", true) || comp(ac, "administrative_area_level_1", true);
        if (state && !$("#stateInput").value.trim()) controllers.state.fill(state);
        resetVerification();
      },
    });

    // STREET — full-context predictions + the verification contract
    controllers.street = PredictionField({
      input: $("#addressLine1"), list: $("[data-addr-suggest]"), hint: $("[data-addr-hint]"),
      icon: "fa-map-marker-alt", minChars: 3,
      buildRequest: function (q) {
        var city = $("#cityInput").value.trim(), pc = $("#postalCodeInput").value.trim();
        var bias = [pc, city].filter(Boolean).join(" ");
        return restrict({ input: bias ? q + ", " + bias : q, types: ["address"] });
      },
      acceptPrediction: function () { return true; },
      formatMain: structMain, formatSec: structSec,
      onEdit: resetVerification,
      onSelect: function (place, pred, api) {
        var ac = place.address_components;
        var route = comp(ac, "route"), num = comp(ac, "street_number");
        controllers.street.fill((route + " " + num).trim() || pred.description);
        var city = comp(ac, "locality") || comp(ac, "postal_town") || comp(ac, "administrative_area_level_3");
        if (city) controllers.city.fill(city);
        var state = comp(ac, "administrative_area_level_2", true) || comp(ac, "administrative_area_level_1", true);
        if (state) controllers.state.fill(state);
        var postal = comp(ac, "postal_code");
        if (postal) { controllers.postal.fill(postal); controllers.postal.setHint(""); }
        var cc = comp(ac, "country", true);
        var cSel = $("#countryInput");
        if (cSel && cc) {
          var was = cSel.value;
          cSel.value = cc;
          if (was !== cc) cSel.dispatchEvent(new Event("change", { bubbles: true }));
        }
        placeIdEl.value = place.place_id || pred.place_id;
        var complete = !!(route && city && postal && cc);
        setVerified(complete, "google_places");
        if (!complete) api.setHint(t("data-addr-partial", "Suggestion applied — complete the missing fields."));
      },
    });

    // country change invalidates the street verification (context changed)
    var cSel = $("#countryInput");
    if (cSel) cSel.addEventListener("change", function () { resetVerification(); });

    setVerified(false);
  }

  function grabShared() {
    placeIdEl = $("[data-addr-placeid]");
    verifiedEl = $("[data-addr-verified]");
    sourceEl = $("[data-addr-source]");
    okBadge = $("[data-addr-badge-ok]");
    warnBadge = $("[data-addr-badge-warn]");
    statusEl = $("[data-addr-status]");
    return !!($("#addressLine1") && $("[data-addr-suggest]") && placeIdEl);
  }

  window.__glxAddrInit = function () {
    if (!grabShared()) return;
    try {
      svc = new google.maps.places.AutocompleteService();
      details = new google.maps.places.PlacesService(document.createElement("div"));
    } catch (e) { svc = null; }
    wireAll();
  };
  window.gm_authFailure = function () {
    if (!grabShared()) return;
    svc = null;
    var h = $("[data-addr-hint]");
    if (h) { h.textContent = t("data-addr-noapi", "Google Places is not available — enter the address manually."); h.hidden = false; }
  };
  if (document.readyState !== "loading") { if (grabShared() && !window.google) wireAll(); }
  else document.addEventListener("DOMContentLoaded", function () { if (grabShared() && !window.google) wireAll(); });
})();
