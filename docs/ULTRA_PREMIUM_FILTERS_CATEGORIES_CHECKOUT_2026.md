# Ultra-premium filters / categories / checkout CRO (2026)

**Branch:** `feature/ultra-premium-filters-categories-checkout-cro` (from
`feature/wow-ecommerce-polish-smart-features` @ `a3bed8b`).
Focused premium polish where users interact (filters, checkout, cards, buttons) +
quick-view accessibility. **No new DB migration.** No real orders/payments;
Stripe TEST; Printify push OFF; `SHIPPING_USE_PRINTIFY` off at rest.

---

## 1. Defects fixed (incl. live owner feedback)

| Defect | Fix |
|--------|-----|
| Mobile store cards wrapped the price ("€" and number on separate lines) | `.price{white-space:nowrap}` + `.product-meta{flex-wrap}` on mobile |
| "New" badge sat **under the wishlist heart** (top-right) on mobile | Store card corner badges now stack **top-left** in a column, clear of the heart |
| "Sort: recommended" button was white before hover (low feedback) | **Inverted**: dark by default → light/white on hover |
| Soft buttons ("Reviews", others) were **white-on-white** | Stronger visible border at rest + **dark invert on hover** (light & dark themes) |
| `placeholder.png` 404 (broken images for imageless products) + console error | Generated a brand placeholder (PIL); console now **0 errors** |
| `--border-strong` shorthand misused as a color (checkout steps) | Replaced with explicit colors + dark overrides |

## 2. Checkout — world-class CRO

Added a premium **step indicator** (Bag ✓ → Details & review → Payment) with a
gold progress line and done/current states; a **Secure** badge on the billing
card; **sticky order summary** on desktop. The shipping estimator stays a `<div>`
(no nested form, no accidental order submit — Phase 52 fix, still covered). Stripe
**TEST** only; **no real order/payment**. EN/IT/FR.

## 3. Quick View — full accessibility (focus trap)

Resolves the Phase 54 TODO: the Quick View drawer now **traps Tab / Shift+Tab**
within the dialog, restores focus to the trigger on close, closes on Esc /
outside click, and is `role="dialog" aria-modal="true"`. Mobile bottom-sheet
preserved.

## 4. Filters / categories / search (already strong — verified + polished)

Honest note: the storefront **already had** (earlier phases) active filter chips,
"Clear all", a mobile filter drawer, result count, sort dropdown, breadcrumb, and
search/category meta chips. This phase verified them working, fixed the badge
overlap, and kept the no-yellow-hover guarantee (Phase 49). The technical
"Printify" category stays invisible and `/store/category/printify/` is **404**.

## 5. Buttons / design tokens

Sort and all `.btn-soft` buttons now invert on hover (premium, consistent) and
are readable on white surfaces. `prefers-reduced-motion` respected. No gold
hover, no heavy shadows, gold used only as a controlled accent.

## 6. Tests

`store/test_ultra_premium.py` (13): checkout steps render + i18n + no-nested-form;
filter drawer/trigger/sort present; active chips on filtering; no chips without
filters; no-gold-hover regression; Printify category 404; quick-view focus-trap
JS + ARIA dialog; CSS checkout-steps + dark + **no `--border-strong` used as a
color**; sticky summary. Full suite: `check` ✅ · `makemigrations --check` (none)
✅ · **`test` 463 OK** ✅ · `compilemessages it/fr` ✅ · `collectstatic` ✅ ·
`staging_check` 0 ✅ · `integration_status` = 2 rotation gates (expected).

## 7. QA live

`127.0.0.1:8799`, viewports 375/390 + 1280/1440, EN/IT/FR, light + dark. Console
**0 errors** (placeholder 404 fixed), **0 overflow**, no hover-yellow, no
customer-facing Printify category, no internal cost/ID leak, no real
order/payment. Screenshots in `docs/qa/phase55/`.

## 8. Accessibility

Quick View focus trap + restore + Esc/outside + ARIA dialog; checkout steps use
`aria-current="step"`; filter drawer `role=dialog aria-modal`; premium dropdowns
keyboard + ARIA; HTML5 `required` validation on checkout fields; reduced-motion.

## 9. Performance / query

No new queries (CSS/UI + a small placeholder asset). Quick view endpoint
unchanged (1 product + review avg). No new dependencies.

## 10. Security

No secrets/PII; no internal Printify ids/costs customer-facing; CSRF intact;
`PRINTIFY_PUSH_ENABLED=False`, `SHIPPING_USE_PRINTIFY` off at rest; no real
orders/payments; QA data fictitious and cleaned up; placeholder is a generated
neutral asset.

## 11. What works · partial · missing

**Works:** checkout step indicator + sticky summary; quick-view focus trap;
inverted sort/soft buttons; badge top-left; single-line prices; placeholder
images; active chips + mobile filter drawer (pre-existing, verified).

**Partial:** categories/collections got light polish (hero/landing redesign not
done this phase); forms got HTML5 + server validation (no floating-label
redesign); cart got light polish (no new in-cart "complete your look").

**Missing for production:** real staging host + `migrate` (Phase 51 `0003`); key
rotation; provider-specific size charts; category landing redesign; live shipping
QA on a public URL; broader real catalog.
