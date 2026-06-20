(function () {
  // Prevent double init if script is included twice
  if (window.__greatkartThemeInit) return;
  window.__greatkartThemeInit = true;

  const root = document.documentElement;

  // Small helper (works even if script is loaded in <head> without defer)
  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  /* =========================
     THEME TOGGLE (light/dark)
     ========================= */
  const THEME_KEY = "theme";

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
  }

  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "dark" || saved === "light") applyTheme(saved);

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-theme-toggle]");
    if (!btn) return;

    const current = root.getAttribute("data-theme") || "light";
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem(THEME_KEY, next);
  });

  /* =========================
     NAV: fixed + shadow on scroll + CSS var height
     ========================= */
  onReady(() => {
    const nav = document.querySelector(".section-header .navbar");
    if (!nav) return;

    document.body.classList.add("has-fixed-navbar");

    const setNavHeight = () => {
      const h = nav.getBoundingClientRect().height || 72;
      root.style.setProperty("--nav-h", h + "px");
    };

    const onScroll = () => {
      if (window.scrollY > 6) nav.classList.add("is-scrolled");
      else nav.classList.remove("is-scrolled");
    };

    setNavHeight();
    onScroll();

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", setNavHeight);
  });

  /* =========================
     DROPDOWN hover delay (desktop only)
     ========================= */
  onReady(() => {
    const DESKTOP_MIN = 992;
    const OPEN_DELAY = 120;
    const CLOSE_DELAY = 180;

    const isDesktop = () => window.innerWidth >= DESKTOP_MIN;

    document.querySelectorAll(".navbar .dropdown").forEach((dd) => {
      const toggle = dd.querySelector('[data-toggle="dropdown"]');
      const menu = dd.querySelector(".dropdown-menu");
      if (!toggle || !menu) return;

      let openTimer = null;
      let closeTimer = null;

      // Toggle Bootstrap 4 dropdown state via classes (the jQuery
      // .dropdown('show'/'hide') methods only exist in Bootstrap 5).
      const open = () => {
        if (!isDesktop()) return;
        dd.classList.add("show");
        menu.classList.add("show");
        toggle.setAttribute("aria-expanded", "true");
      };

      const close = () => {
        if (!isDesktop()) return;
        dd.classList.remove("show");
        menu.classList.remove("show");
        toggle.setAttribute("aria-expanded", "false");
      };

      dd.addEventListener("mouseenter", () => {
        if (!isDesktop()) return;
        clearTimeout(closeTimer);
        openTimer = setTimeout(open, OPEN_DELAY);
      });

      dd.addEventListener("mouseleave", () => {
        if (!isDesktop()) return;
        clearTimeout(openTimer);
        closeTimer = setTimeout(close, CLOSE_DELAY);
      });
    });
  });

  /* =========================
     SKELETON images -> loaded
     ========================= */
  onReady(() => {
    document.querySelectorAll("img[data-skeleton]").forEach((img) => {
      const wrap = img.closest(".media-skeleton");
      if (!wrap) return;

      const done = () => wrap.classList.add("is-loaded");

      // IMPORTANT: if the image is already cached, complete=true and load won't fire
      if (img.complete && img.naturalWidth > 0) {
        done();
        return;
      }

      img.addEventListener("load", done, { once: true });
      img.addEventListener("error", done, { once: true });
    });
  });

  /* =========================
     CUSTOM SELECT dropdown -> hidden input (PDP)
     ========================= */
  document.addEventListener("click", (e) => {
    const item = e.target.closest(".custom-select-dd .dropdown-item[data-value]");
    if (!item) return;

    e.preventDefault();
    e.stopPropagation();

    const inputId = item.getAttribute("data-target-input");
    const labelId = item.getAttribute("data-target-label");
    const value = item.getAttribute("data-value");
    const text = item.textContent.trim();

    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);

    if (input) input.value = value;
    if (label) label.textContent = text;

    // highlight selected item inside this dropdown
    const menu = item.closest(".dropdown-menu");
    if (menu) {
      menu.querySelectorAll(".dropdown-item.is-active").forEach((el) => el.classList.remove("is-active"));
      item.classList.add("is-active");
    }

    // close dropdown (Bootstrap) after DOM updates (prevents tiny jump)
    const dd = item.closest(".dropdown");
    const toggle = dd ? dd.querySelector('[data-toggle="dropdown"]') : null;

    if (toggle && window.jQuery) {
      requestAnimationFrame(() => {
        window.jQuery(toggle).dropdown("hide");
        toggle.blur();
      });
    }
  });

  /* =========================
     ADDRESS dropdown autofill (checkout)
     ========================= */
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".dropdown-item[data-addr]");
    if (!btn) return;

    e.preventDefault();

    let data = {};
    try {
      data = JSON.parse(btn.getAttribute("data-addr") || "{}");
    } catch (err) {
      return;
    }

    const pcEl = document.getElementById("postalCodeInput");
    if (pcEl) pcEl.value = data.postal_code || "";
    const cEl = document.getElementById("countryInput");
    if (cEl) cEl.value = (data.country || "").toUpperCase();


    const map = {
      first_name: "first_name",
      last_name: "last_name",
      email: "email",
      phone: "phone",
      address_line_1: "address_line_1",
      address_line_2: "address_line_2",
      city: "city",
      state: "state",
      postal_code: "postal_code",
      country: "country",
    };

    Object.keys(map).forEach((k) => {
      const el = document.querySelector(`[name="${map[k]}"]`);
      if (el && data[k] !== undefined) el.value = data[k];
    });

    const label = document.getElementById("addrLabel");
    if (label) label.textContent = btn.textContent.trim().replace("✅", "").trim();

    const dd = btn.closest(".dropdown");
    const toggle = dd ? dd.querySelector('[data-toggle="dropdown"]') : null;
    if (toggle && window.jQuery) {
      requestAnimationFrame(() => {
        window.jQuery(toggle).dropdown("hide");
        toggle.blur();
      });
    }
  });

  /* =========================
     STORE: Filters + Sort (NO inline scripts needed)
     ========================= */
  onReady(() => {
    const grid = document.getElementById("productGrid");
    if (!grid) return; // not store page

    const items = Array.from(document.querySelectorAll(".product-item"));

    const inStockOnly = document.getElementById("inStockOnly");
    const stockChip = document.getElementById("stockChip");

    const range = document.getElementById("priceRange");
    const priceMin = document.getElementById("priceMin");
    const priceMax = document.getElementById("priceMax");
    const priceMinText = document.getElementById("priceMinText");
    const priceMaxText = document.getElementById("priceMaxText");

    const applyBtn = document.getElementById("applyFilters");
    const clearBtn = document.getElementById("clearFilters");

    // If missing pieces, do nothing
    if (!items.length || !priceMin || !priceMax || !applyBtn || !clearBtn) return;

    // Collect prices from current page
    const prices = items
      .map((el) => parseFloat(el.getAttribute("data-price") || "0"))
      .filter((n) => Number.isFinite(n));

    const maxPrice = prices.length ? Math.max(...prices) : 0;
    const minPrice = prices.length ? Math.min(...prices) : 0;

    // Init UI
    if (range) {
      range.min = "0";
      range.max = String(maxPrice);
      range.value = String(maxPrice);
    }

    priceMin.value = String(minPrice);
    priceMax.value = String(maxPrice);

    function getMinMax() {
      const minV = Math.max(0, parseFloat(priceMin.value || "0"));
      const maxV = Math.max(minV, parseFloat(priceMax.value || "0"));
      return { minV, maxV };
    }

    function syncLabels() {
      const { minV, maxV } = getMinMax();
      if (priceMinText) priceMinText.textContent = String(Math.round(minV));
      if (priceMaxText) priceMaxText.textContent = String(Math.round(maxV));
      if (stockChip) stockChip.textContent = inStockOnly && inStockOnly.checked ? "In stock" : "All";
    }

    function showEl(el) {
      // reset display to original (bootstrap col + d-flex)
      el.style.removeProperty("display");
    }

    function hideEl(el) {
      // In case some CSS forces display via !important, set with important
      el.style.setProperty("display", "none", "important");
    }

    function apply() {
      const { minV, maxV } = getMinMax();
      const onlyStock = !!(inStockOnly && inStockOnly.checked);

      items.forEach((el) => {
        const p = parseFloat(el.getAttribute("data-price") || "0");
        const inStock = el.getAttribute("data-instock") === "1";

        const okPrice = p >= minV && p <= maxV;
        const okStock = !onlyStock || inStock;

        if (okPrice && okStock) showEl(el);
        else hideEl(el);
      });

      syncLabels();
    }

    // Slider = quick max
    if (range) {
      range.addEventListener("input", () => {
        priceMax.value = range.value;
        syncLabels();
      });
    }

    // Inputs
    priceMin.addEventListener("input", syncLabels);
    priceMax.addEventListener("input", syncLabels);
    if (inStockOnly) inStockOnly.addEventListener("change", syncLabels);

    // Buttons
    applyBtn.addEventListener("click", apply);
    clearBtn.addEventListener("click", () => {
      if (inStockOnly) inStockOnly.checked = true;
      priceMin.value = String(minPrice);
      priceMax.value = String(maxPrice);
      if (range) range.value = String(maxPrice);

      items.forEach(showEl);
      syncLabels();
    });

    // Initial labels (no filtering)
    syncLabels();

    /* ===== SORT DROPDOWN ===== */
    const form = document.getElementById("sortForm");
    const input = document.getElementById("sortInput");
    const label = document.getElementById("sortLabel");

    if (form && input && label) {
      document.querySelectorAll(".dropdown-item[data-sort]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const value = btn.getAttribute("data-sort") || "";
          input.value = value;

          const s = btn.querySelector("span");
          label.textContent = s ? s.textContent.trim() : btn.textContent.trim();

          const dd = btn.closest(".dropdown");
          const toggle = dd ? dd.querySelector('[data-toggle="dropdown"]') : null;
          if (toggle) toggle.blur();

          form.submit();
        });
      });
    }
  });

  /* =========================
     PDP thumbs (optional)
     ========================= */
  onReady(() => {
    const main = document.getElementById("pdpMainImg");
    const thumbs = document.querySelectorAll(".pdp-thumb");
    if (!main || !thumbs.length) return;

    thumbs.forEach((btn) => {
      btn.addEventListener("click", () => {
        const url = btn.getAttribute("data-img");
        if (!url) return;

        main.src = url;

        thumbs.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        const lb = document.querySelector("#pdpLightbox img");
        if (lb) lb.src = url;
      });
    });
  });
})();
