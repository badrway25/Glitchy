/* Premium add-to-cart confirmation modal (PDP).
 *
 * store-features.js dispatches a cancelable 'glitchy:cart-added' event with the
 * enriched add_cart JSON; this modal claims it (preventDefault) and shows the
 * confirmation with the variant-correct thumbnail. Pages without the modal (or
 * responses without a line payload, e.g. grid quick-add) keep the toast.
 * No-JS never reaches here: the classic POST redirect-to-cart stays untouched.
 *
 * A11y: role=dialog + aria-modal on the card, focus trap, Esc/overlay close
 * (own-visibility checked), focus restored to the trigger on close.
 */
(function () {
  "use strict";

  var onReady = function (fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  };

  onReady(function () {
    var backdrop = document.getElementById("atcModal");
    if (!backdrop) return;
    var modal = backdrop.querySelector(".atc-modal");
    var currency = backdrop.getAttribute("data-currency") || "";
    var lastTrigger = null;

    function isOpen() { return !backdrop.hidden; }

    function focusables() {
      return modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    }

    function open() {
      if (!isOpen()) {
        lastTrigger = document.activeElement;
        backdrop.hidden = false;
        window.requestAnimationFrame(function () { backdrop.classList.add("is-open"); });
        document.body.style.overflow = "hidden";
      }
      var f = focusables();
      if (f.length) f[f.length - 1].focus();   /* land on "View cart" */
    }

    function close() {
      if (!isOpen()) return;
      backdrop.classList.remove("is-open");
      backdrop.hidden = true;
      document.body.style.overflow = "";
      if (lastTrigger && lastTrigger.focus) lastTrigger.focus();
      lastTrigger = null;
    }

    function setText(sel, value) {
      var el = backdrop.querySelector(sel);
      if (el) el.textContent = value;
    }

    function togglePill(wrapSel, valueSel, value) {
      var wrap = backdrop.querySelector(wrapSel);
      if (!wrap) return;
      wrap.hidden = !value;
      if (value) setText(valueSel, value);
    }

    function fill(line) {
      setText("[data-atc-name]", line.product_name || "");
      setText("[data-atc-qty]", String(line.quantity || 1));
      setText("[data-atc-price]", line.price ? (currency + " " + line.price) : "");
      togglePill("[data-atc-color-wrap]", "[data-atc-color]", line.color || "");
      togglePill("[data-atc-size-wrap]", "[data-atc-size]", line.size || "");
      var thumb = backdrop.querySelector("[data-atc-thumb]");
      var note = backdrop.querySelector("[data-atc-imgnote]");
      var hasImage = !!line.image_url;
      if (thumb) {
        thumb.hidden = !hasImage;
        if (hasImage) {
          thumb.src = line.thumb_url || line.image_url;
          thumb.alt = (line.product_name || "") + (line.color ? " — " + line.color : "");
        }
      }
      if (note) note.hidden = !(hasImage && line.color && line.variant_matched);
    }

    document.addEventListener("glitchy:cart-added", function (e) {
      var d = e.detail || {};
      if (!d.line) return;                  /* no payload -> leave the toast on */
      e.preventDefault();                   /* claim the confirmation UI */
      fill(d.line);
      var viewCart = backdrop.querySelector(".atc-viewcart");
      if (viewCart && d.cart_url) viewCart.setAttribute("href", d.cart_url);
      open();                               /* re-open safe: never doubles the overlay */
    });

    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop || (e.target.closest && e.target.closest("[data-atc-close]"))) {
        close();
      }
    });

    document.addEventListener("keydown", function (e) {
      if (!isOpen()) return;                /* never react while closed */
      if (e.key === "Escape") {
        close();
      } else if (e.key === "Tab") {
        var f = focusables();
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }
    });
  });
})();
