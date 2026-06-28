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
      free: root.getAttribute("data-label-free") || "Free"
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
    var mixedEl = root.querySelector("[data-se-mixed]");
    var disclaimerEl = root.querySelector("[data-se-disclaimer]");

    if (!panel || !submitBtn || !endpoint) return;

    var current = null; // last result payload

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

    function selectMethod(method) {
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
      // Update totals (display only)
      var cost = opt.free ? 0 : (parseFloat(opt.cost) || 0);
      if (subtotalVal) subtotalVal.textContent = money(symbol, subtotal);
      if (shippingVal) shippingVal.textContent = opt.free ? msg.free : money(symbol, cost);
      if (totalVal) totalVal.textContent = money(symbol, subtotal + cost);
      // Let the checkout page sync its own summary if it wants to.
      root.dispatchEvent(new CustomEvent("shipping:method", {
        bubbles: true, detail: { method: opt.method, cost: cost, free: !!opt.free, result: current }
      }));
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

        var price = document.createElement("span");
        price.className = "se-option-price";
        price.textContent = o.free ? msg.free : o.cost_display;

        label.appendChild(radio);
        label.appendChild(main);
        label.appendChild(price);
        optionsEl.appendChild(label);

        label.addEventListener("click", function () { selectMethod(o.method); });
        label.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectMethod(o.method); }
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
