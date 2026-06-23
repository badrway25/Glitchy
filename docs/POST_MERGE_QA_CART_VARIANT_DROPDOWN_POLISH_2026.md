# Post-Merge QA — Cart / Variant Dropdown / Nav Polish + Made-on-Demand Copy Fix

**Date:** 2026-06 · **Target branch:** `release/staging-printify-fashion-store`
**Merged source:** `fix/cart-variant-dropdown-sidebar-filter-polish`
**Merge type:** fast-forward (no merge commit, no conflicts) · **Final HEAD:** `4281fc3`

## Scope merged

### Phase 45 — cart / variant dropdown / sidebar / filter polish
- Premium **cart item removal modal** (replaces `window.confirm`; EN/IT/FR; Cancel/Remove; Esc/backdrop close).
- **Empty cart** without the bordered inner card (no card-in-card).
- **`.cart-card` transparent** (no white bg / border / shadow) — only the item mini-cards carry surface.
- **`.qty-control` without border** (clean stepper).
- **Colour/size dropdowns** rebuilt as a vanilla component styled like the `.sortx` sort control
  (single rotating chevron, soft-shadow menu, no Bootstrap `data-toggle` → no double-open).
- **Navbar/sidebar fully visible** at 1024 / 1280 / 1440 (root cause: Bootstrap
  `.navbar-collapse{flex-grow:1}` was squashing the search and pushing cart/wishlist/account
  off-screen; forced content-width + flex-start so the search keeps a generous width).
- **Store filter "yellow hover" removed** (native control `accent-color` switched from gold to
  brand espresso; chip hover border neutralized; sections never get a hover background).

### Phase 46 — made-on-demand copy/layout fix (pre-merge)
- **Root cause:** the French `.po` had **31 corrupted msgstr entries** where each translation was
  concatenated 13–14× across continuation lines (gettext joins continuation lines), producing a
  giant repeated string that broke the "Fabriqués à la demande" section layout and mixed
  singular/plural. Caused by a buggy earlier translation-fill script. IT/EN were unaffected.
- **Fix:** de-duplicated every corrupted FR entry to a single clean sentence (period-repeat
  detection + first-sentence extraction). Longest FR `msgstr` 1316 → 373 chars.
- **Final copy (consistent singular/plural per block):**
  - EN: "Made on demand" / "Printed only when you order — less waste, always fresh."
  - IT: "Realizzato su richiesta" / "Stampato solo quando ordini — meno sprechi, sempre nuovo."
  - FR (home, plural — matches "Fabriqués à la demande"): "Imprimés uniquement à la commande —
    moins de gaspillage, toujours neufs."
  - FR (PDP pod-card, singular subject "Chaque pièce"): "Chaque pièce est imprimée uniquement à
    la commande — moins de gaspillage, toujours neuve."

## Tests (post-merge, on `release/staging-printify-fashion-store`)
- `manage.py check` → 0 issues
- `manage.py makemigrations --check --dry-run` → no changes
- `manage.py test` → **356 passed**
- `compilemessages -l it -l fr` → clean
- `collectstatic --noinput` → ok
- `scripts/staging_check.sh` → **0 failures**

## QA live (post-merge)
- URL `http://127.0.0.1:8799/` · viewports 375/390/1280/1440 · languages EN/IT/FR · light + dark.
- **console 0 · HTTP 500: 0 · overflow 0** (5 pages × 4 viewports × 3 languages × 2 themes).
- Made-on-demand section renders a single sentence in FR/EN/IT, proportionate, no overflow.
- Cart remove modal, transparent cart surfaces, sortx-style variant dropdowns, navbar fully
  visible, filters without yellow hover — all verified.

## Security
- `.env` not tracked · AI key not in git · Printify token not in git · no secrets printed.
- `PRINTIFY_PUSH_ENABLED=False` · `SHIPPING_USE_PRINTIFY=False` · no real order · no real payment.

## What remains manual (out of scope here)
- Staging host provisioning + real credentials.
- OpenAI / Printify key rotation (the documented final pre-go-live step).
- Stale Printify variant counts (re-sync) and live shipping (`SHIPPING_USE_PRINTIFY` stays off).
