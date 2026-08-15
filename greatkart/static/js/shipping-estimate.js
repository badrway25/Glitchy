/*
 * Pre-order shipping estimator.
 *
 * Posts the chosen destination to /cart/shipping-estimate/, renders the returned
 * cost + delivery options, and lets the customer switch method (updating the
 * estimated total). All money/time strings come back already localized from the
 * server; this script only injects them and computes the display-only total.
 * It never sends or trusts a price, and never places an order.
 */
(function () {
  "use strict";

  function getCookie(name) {
    var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }

  function money(symbol, value) {
    return symbol + " " + (Math.round(value * 100) / 100).toFixed(2);
  }

  function initEstimator(root) {
    var endpoint = root.getAttribute("data-endpoint");
    var symbol = root.getAttribute("data-currency") || "€";
    var subtotal = parseFloat(root.getAttribute("data-subtotal")) || 0;
    var msg = {
      error: root.getAttribute("data-msg-error"),
      network: root.getAttribute("data-msg-network"),
      country: root.getAttribute("data-msg-country"),
      free: root.getAttribute("data-label-free") || "Free",
      fastest: root.getAttribute("data-label-fastest") || "Fastest",
      total: root.getAttribute("data-label-total") || "Estimated total",
      totalFallback: root.getAttribute("data-label-total-fallback") || "Items + shipping",
      expressPhone: root.getAttribute("data-msg-express-phone") || "",
      expressDestination: root.getAttribute("data-msg-express-destination") || "",
      expressItems: root.getAttribute("data-msg-express-items") || ""
    };

    // `panel` is a <div>, not a <form> (the widget can sit inside the checkout
    // billing form, where a nested form would be invalid HTML).
    var panel = root.querySelector("[data-se-form]");
    // Fields may live inside the widget (cart) or in an external form (checkout
    // billing address). External ids take precedence when present.
    var countryFromId = root.getAttribute("data-country-from");
    var zipFromId = root.getAttribute("data-zip-from");
    var countrySel = (countryFromId && document.getElementById(countryFromId)) ||
                     root.querySelector("[data-se-country]");
    var zipInput = (zipFromId && document.getElementById(zipFromId)) ||
                   root.querySelector("[data-se-zip]");
    var submitBtn = root.querySelector("[data-se-submit]");
    var spinner = root.querySelector("[data-se-spinner]");
    var skeleton = root.querySelector("[data-se-skeleton]");
    var resultBox = root.querySelector("[data-se-result]");
    var errorBox = root.querySelector("[data-se-error]");
    var badge = root.querySelector("[data-se-badge]");
    var delivEl = root.querySelector("[data-se-deliv]");
    var optionsEl = root.querySelector("[data-se-options]");
    var subtotalVal = root.querySelector("[data-se-subtotal-val]");
    var shippingVal = root.querySelector("[data-se-shipping-val]");
    var totalVal = root.querySelector("[data-se-total-val]");
    var totalLabelEl = root.querySelector("[data-se-tl-total]");
    var discountRow = root.querySelector("[data-se-discount-row]");
    var discountVal = root.querySelector("[data-se-discount-val]");
    var taxRow = root.querySelector("[data-se-tax-row]");
    var taxVal = root.querySelector("[data-se-tax-val]");
    var mixedEl = root.querySelector("[data-se-mixed]");
    var disclaimerEl = root.querySelector("[data-se-disclaimer]");

    if (!panel || !submitBtn || !endpoint) return;

    var current = null;  // last result payload
    var selectedMethod = "";

    function setBusy(busy) {
      submitBtn.disabled = busy;
      if (spinner) spinner.hidden = !busy;
      if (skeleton) skeleton.hidden = !busy;
      root.classList.toggle("is-loading", busy);
    }

    function showError(text) {
      if (resultBox) resultBox.hidden = true;
      if (errorBox) { errorBox.hidden = false; errorBox.textContent = text || msg.error; }
    }

    function selectMethod(method, userInitiated) {
      if (!current || !current.options) return;
      var opt = null;
      current.options.forEach(function (o) {
        var sel = o.method === method;
        o.selected = sel;
        if (sel) opt = o;
      });
      if (!opt) opt = current.options[0];
      // Keep the header delivery label in sync with the chosen method.
      if (delivEl && opt.delivery_label) delivEl.textContent = opt.delivery_label;
      // Update option chip states
      optionsEl.querySelectorAll("[data-se-opt]").forEach(function (el) {
        var on = el.getAttribute("data-se-opt") === opt.method;
        el.classList.toggle("is-selected", on);
        var radio = el.querySelector("input[type=radio]");
        if (radio) radio.checked = on;
        el.setAttribute("aria-checked", on ? "true" : "false");
      });
      // Update totals (display only). Prefer the authoritative server summary so the
      // widget's estimated total is the SAME grand total (tax included) the Order
      // summary shows — never two different "total" figures on one screen.
      paintWidgetTotals(opt);
      selectedMethod = opt.method;
      var hidden = document.getElementById("shippingMethodInput");
      if (hidden) hidden.value = opt.method;
      /* A method change re-prices the order server-side: ask for the authoritative
         summary rather than doing arithmetic in the browser. */
      if (current && current.summary) paintSummary(current.summary);
      /* A user-picked method must be re-priced server-side (Express costs more):
         re-estimate instead of doing arithmetic in the browser. */
      if (userInitiated) estimate();
      root.dispatchEvent(new CustomEvent("shipping:method", {
        bubbles: true, detail: { method: opt.method, cost: cost, free: !!opt.free, result: current }
      }));
    }

    /* Widget totals = Order summary totals. The server payload (checkout_quote) is
       authoritative and already includes tax and any discount, so the widget's
       "Estimated total" equals the summary's grand total. Only if the summary is
       somehow absent do we fall back to items+shipping — and then the total line is
       relabelled so it can never be misread as the final amount. */
    function paintWidgetTotals(opt) {
      var s = current && current.summary;
      if (s) {
        if (subtotalVal) subtotalVal.textContent = s.items_subtotal_display;
        if (shippingVal) shippingVal.textContent = s.shipping_display;
        var hasDiscount = parseFloat(s.discount || 0) > 0;
        if (discountRow) discountRow.hidden = !hasDiscount;
        if (hasDiscount && discountVal) discountVal.textContent = "− " + s.discount_display;
        var hasTax = parseFloat(s.tax || 0) > 0;
        if (taxRow) taxRow.hidden = !hasTax;
        if (hasTax && taxVal) taxVal.textContent = s.tax_display;
        if (totalVal) totalVal.textContent = s.grand_total_display;
        if (totalLabelEl) totalLabelEl.textContent = msg.total;
        return;
      }
      // Fallback (summary missing): items + shipping only, honestly relabelled.
      var cost = opt.free ? 0 : (parseFloat(opt.cost) || 0);
      if (subtotalVal) subtotalVal.textContent = money(symbol, subtotal);
      if (shippingVal) shippingVal.textContent = opt.free ? msg.free : money(symbol, cost);
      if (discountRow) discountRow.hidden = true;
      if (taxRow) taxRow.hidden = true;
      if (totalVal) totalVal.textContent = money(symbol, subtotal + cost);
      if (totalLabelEl) totalLabelEl.textContent = msg.totalFallback;
    }

    /* Express is eligibility-based: say why it is unavailable rather than
       silently hiding it, but never promise it where Printify cannot deliver. */
    function paintExpressNote(summary) {
      var note = root.querySelector("[data-se-express-note]");
      if (!note) return;
      var blockers = (summary && summary.express_blockers) || [];
      var reason = "";
      if (blockers.indexOf("phone_required") !== -1) {
        reason = msg.expressPhone;
      } else if (blockers.indexOf("destination_not_supported") !== -1 ||
                 blockers.indexOf("po_box") !== -1) {
        reason = msg.expressDestination;
      } else if (blockers.indexOf("items_not_eligible") !== -1) {
        reason = msg.expressItems;
      }
      note.textContent = reason || "";
      note.hidden = !reason;
    }

    /* ---- Order summary repaint — one payload, one set of numbers ------------ */
    function fieldValue(id) {
      var el = document.getElementById(id);
      return (el && el.value || "").trim();
    }

    function paintSummary(s) {
      if (!s) return;
      var box = document.querySelector("[data-summary-lines]");
      if (!box) return;
      var set = function (sel, value) {
        var el = box.querySelector(sel);
        if (el && value !== undefined && value !== null) el.textContent = value;
      };
      set("[data-sum-subtotal]", s.items_subtotal_display);
      set("[data-sum-shipping]", s.shipping_display);
      set("[data-sum-tax]", s.tax_display);
      set("[data-sum-grand]", s.grand_total_display);
      set("[data-sum-method]", s.delivery_label || "");
      var discountRow = box.querySelector("[data-sum-discount-row]");
      if (discountRow) {
        var hasDiscount = parseFloat(s.discount || 0) > 0;
        discountRow.hidden = !hasDiscount;
        if (hasDiscount) set("[data-sum-discount]", s.discount_display);
      }
      var flag = box.querySelector("[data-sum-updated]");
      if (flag) {
        flag.hidden = false;
        window.clearTimeout(flag._t);
        flag._t = window.setTimeout(function () { flag.hidden = true; }, 2600);
      }
    }

    function renderOptions(options) {
      optionsEl.innerHTML = "";
      options.forEach(function (o) {
        var label = document.createElement("label");
        label.className = "se-option" + (o.selected ? " is-selected" : "");
        label.setAttribute("data-se-opt", o.method);
        label.setAttribute("role", "radio");
        label.setAttribute("aria-checked", o.selected ? "true" : "false");
        label.setAttribute("tabindex", "0");

        var radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "se_method";
        radio.value = o.method;
        radio.checked = !!o.selected;
        radio.className = "se-option-radio";

        var main = document.createElement("span");
        main.className = "se-option-main";
        var nm = document.createElement("span");
        nm.className = "se-option-name";
        nm.textContent = o.label;
        var eta = document.createElement("span");
        eta.className = "se-option-eta";
        eta.textContent = o.delivery_label || "";
        main.appendChild(nm);
        main.appendChild(eta);

        if (o.fastest) {
          var fast = document.createElement("span");
          fast.className = "se-badge-fast";
          fast.textContent = msg.fastest || "Fastest";
          main.appendChild(fast);
        }

        var price = document.createElement("span");
        price.className = "se-option-price";
        price.textContent = o.free ? msg.free : o.cost_display;

        label.appendChild(radio);
        label.appendChild(main);
        label.appendChild(price);
        optionsEl.appendChild(label);

        label.addEventListener("click", function () { selectMethod(o.method, true); });
        label.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectMethod(o.method, true); }
        });
      });
    }

    function render(data) {
      current = data;
      if (!data || data.available === false) {
        showError((data && data.disclaimer) || msg.error);
        return;
      }
      if (errorBox) errorBox.hidden = true;
      if (resultBox) resultBox.hidden = false;

      if (badge) {
        badge.textContent = data.source_label || "";
        badge.className = "se-badge se-badge--" + (data.source || "");
      }
      if (delivEl) delivEl.textContent = data.delivery_label || "";
      if (mixedEl) mixedEl.hidden = !data.mixed_sources;
      if (disclaimerEl) disclaimerEl.textContent = data.disclaimer || "";

      if (data.summary) paintSummary(data.summary);
      paintExpressNote(data.summary);
      var opts = data.options && data.options.length ? data.options : [];
      renderOptions(opts);
      var sel = opts.filter(function (o) { return o.selected; })[0] || opts[0];
      if (sel) selectMethod(sel.method);
    }

    function estimate() {
      var country = (countrySel && countrySel.value || "").trim();
      if (!country) { showError(msg.country); return; }
      setBusy(true);
      if (errorBox) errorBox.hidden = true;

      var body = new URLSearchParams();
      body.set("country", country);
      body.set("postal_code", (zipInput && zipInput.value || "").trim());
      /* The server prices AND persists the choice; sending the whole destination
         lets it apply the Express eligibility rules (state, PO box, phone). */
      body.set("shipping_method", selectedMethod || "");
      body.set("region", fieldValue("stateInput"));
      body.set("city", fieldValue("cityInput"));
      body.set("address1", fieldValue("addressLine1Input"));
      body.set("address2", fieldValue("addressLine2Input"));
      body.set("phone", fieldValue("phoneInput"));
      var tokenInput = panel.querySelector("[name=csrfmiddlewaretoken]");
      var token = (tokenInput && tokenInput.value) || getCookie("csrftoken");
      if (tokenInput) body.set("csrfmiddlewaretoken", tokenInput.value);

      fetch(endpoint, {
        method: "POST",
        headers: { "X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest" },
        body: body,
        credentials: "same-origin"
      }).then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, status: r.status, data: j }; });
      }).then(function (res) {
        setBusy(false);
        render(res.data);
      }).catch(function () {
        setBusy(false);
        showError(msg.network);
      });
    }

    submitBtn.addEventListener("click", function (e) { e.preventDefault(); estimate(); });
    // Allow Enter from the postal field to trigger an estimate (no form to submit).
    if (zipInput) zipInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); estimate(); }
    });
    // Re-estimate when the destination changes after a first estimate (keeps it live).
    if (countrySel) countrySel.addEventListener("change", function () {
      if (current) estimate();
    });
    if (zipInput) zipInput.addEventListener("change", function () {
      if (current) estimate();
    });
  }

  function init() {
    document.querySelectorAll("[data-ship-estimator]").forEach(initEstimator);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
