# Luxury Conversion UX + Store Depth + Customer Portal Functional Depth (Phase 65, 2026)

**Branch:** `feature/luxury-conversion-store-portal-functional-depth` (from
`release/staging-printify-fashion-store` @ `d876b3a`). **No DB migration.** No real
orders/payments; Printify push/sync OFF.

## 1. Initial problem
The store and portal looked premium but lacked *functional* depth and a few visual
inconsistencies remained (subtle order-row buttons, truncated custom-select values, and a
button family that wasn't uniformly sized). The owner wanted real, practical features — not
placeholders — plus more micro-feedback and conversion polish.

## 2. Store conversion + product card + quick view
The store toolbar, product card (gallery carousel, sale/new badges, price block, quick-add,
wishlist) and the quick-view drawer were already strong, so this phase added the missing
**feedback layer** rather than re-architecting: the wishlist heart now fires a **toast**
("Saved to wishlist" / "Removed from wishlist") on every surface — store grid, PDP,
quick-view drawer and merchandising cards (previously silent on the PDP/quick-view). The
store no-results already uses the luxury empty state. Gallery prefetch and the
add-to-cart/variation flow are untouched (no N+1, no broken filters).

## 3. Customer portal — Buy again / Reorder (the headline feature)
A real, **safe** "Buy again" on the order detail: it re-adds the order's items to the
**cart only** — it never creates an order or takes payment. It is `@login_required` +
`@require_POST`, scoped with `get_object_or_404(Order, user=request.user, …)`, and re-uses
the **exact variations** already chosen on the original `OrderProduct` (so nothing is
re-prompted). Unavailable products are **skipped, not faked**. The user's cart is indexed
once before the merge loop, so it's **N+1-free** even for large carts. Covered by tests for
the cart result, "never creates an order", POST-only, login-required and **ownership**
(another user gets 404).

## 4. Micro-feedback / toast system
A lightweight `toast.js` (`window.glToast(msg, tone)`) + a `#toastHost` region. Used for
**copy order number** ("Order number copied") and **wishlist add/remove**. XSS-safe
(`textContent`), auto-dismiss, dismissible, `prefers-reduced-motion` safe, no leak
(elements removed after fade). Server messages still render as inline alerts (no
duplication).

## 5. Activity — model decision
A `CustomerActivityEvent` model was **evaluated and deliberately NOT built** this phase. The
derived dashboard timeline already pulls real timestamps from `Order`, `Address` and
`WishlistItem`; a dedicated event table would **duplicate those timestamps**, require hook
code in 7 call sites (4 address views + 3 wishlist functions), and add a **risky late-phase
migration that would block testing** — with no UX benefit. The derived timeline is kept and
this trade-off is documented. (A real audit/event layer remains a clean option for a future
phase if monitoring — not UX — needs it.) **No migration → deploy needs no `migrate`.**

## 6. Visual polish fixes (owner feedback this phase)
- **Order-row buttons** (Details / Receipt) were rendering as bare text → given an elegant
  treatment: a clean bordered Details + a gold-tinted Receipt, with hover.
- **Custom-select dropdowns** (`pmsel`) truncated their value ("Newest fi…") and their menu
  options ("Highest t…") → the button now sizes to content (130–260px) and the menu sizes to
  its widest option; nothing is clipped.
- **Button family unified**: `.btn-soft` / `.btn-outline` / `.btn-elegant` / `.btn-ghost`
  now share the **same premium size + uppercase treatment** as `.btn-primary` (e.g. "Shop"
  and "View all orders" were 31px vs 38px → both 38px). `.btn-sm` stays proportionally
  small. Verified: no overflow and no wrapped buttons on store / cart / dashboard at
  375/390/1280/1440.

## 7. Empty states
All `.dash-empty` states (orders / billing / dashboard) were elevated in one CSS pass to the
luxury look (gradient gold icon tile, serif heading) — consistent with the Phase 64
`.lux-empty`. Light + dark.

## 8. Accessibility
Icon-only buttons keep aria-labels; toasts are `role=status` in an `aria-live` region;
focus-visible preserved; the custom-select stays keyboard-operable; reduced-motion fully
respected.

## 9. Performance
Reorder indexes the cart once (no N+1). No new queries elsewhere. Toast/motion are tiny
vanilla files. No CLS. Gallery prefetch intact.

## 10. Security / ownership
`order_reorder` cannot create an order or take payment, is POST+login-only, and is
ownership-scoped (404 for other users). Re-added variations are catalog `Variation` objects
(not user data). CSRF on the Buy-again form. No PII in reports or the PII-safe QA
screenshots (synthetic "QA Demo" accounts, deleted afterwards). No PII in localStorage (only
the theme toggle, pre-existing).

## 11. i18n
~9 new strings (Buy again, order/cart feedback, wishlist toasts) in EN/IT/FR, compiled and
verified.

## 12. QA
Local `127.0.0.1`, **375/390/1280/1440**, EN/IT/FR, **light + dark**, **console 0**,
**0 overflow**, reduced-motion verified (no element stuck hidden). 14 PII-safe screenshots
in `docs/qa/phase65/`.

## 13. Limits (honest)
- The store/quick-view received a **feedback + consistency** pass, not a full re-layout
  (toolbar density toggle, infinite scroll, colour swatches in quick-view remain follow-ups).
- "Download all receipts" (bulk) was **not** built — it would need a streaming/zip job; the
  per-order receipt download and the new Buy-again cover the high-value cases. Documented.
- `CustomerActivityEvent` intentionally deferred (see §5).
- Next-best-actions are the existing dashboard alerts (receipts / address / wishlist) —
  real and prioritised, not a separate invented widget.
