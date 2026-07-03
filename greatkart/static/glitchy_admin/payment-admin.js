/* Payment provider admin — show only the credential section matching the selected provider.
 * Progressive enhancement: no JS -> both Stripe and PayPal sections stay visible (accessible).
 * The fieldsets carry classes gl-prov + gl-prov-stripe / gl-prov-paypal. */
(function () {
  "use strict";
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }
  ready(function () {
    var select = document.querySelector("#id_provider, select[name='provider']");
    var sections = document.querySelectorAll(".gl-prov");
    if (!sections.length) return;
    function currentProvider() {
      if (select && select.value) return select.value;
      // change form: provider is readonly -> read it from the readonly field text
      var ro = document.querySelector(".field-provider .readonly");
      return ro ? ro.textContent.trim().toLowerCase() : "";
    }
    function apply() {
      var p = currentProvider();
      Array.prototype.forEach.call(sections, function (sec) {
        var isStripe = sec.classList.contains("gl-prov-stripe");
        var match = (p.indexOf("stripe") > -1 && isStripe) || (p.indexOf("paypal") > -1 && !isStripe);
        // if we can't tell the provider, show everything (safe fallback)
        sec.style.display = (!p || match) ? "" : "none";
      });
    }
    if (select) select.addEventListener("change", apply);
    apply();
  });
})();
