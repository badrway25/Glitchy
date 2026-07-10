# Add-to-Cart Modal + Variant Thumbnail Propagation (2026)

**Branch:** `fix/glitchy-add-to-cart-modal-variant-thumbnail-flow` (from `release/staging-printify-fashion-store @ 6f9638e`). **Three additive migrations**: `carts/0004` (`CartItem.selected_image` FK), `orders/0010` (`OrderProduct.selected_image` FK), `store/0016` (`ProductColorImageMapRun` — see the admin mapping doc). No new dependencies.

## 1. Root cause — variant text changed, image didn't

Every line-thumbnail surface rendered the **live product hero** and nothing else: `cart.html` and `checkout.html`/`payments.html` used `cart_item.product.images.url` (the single `Product.images` ImageField), `order_complete.html` showed no line image at all, and `accounts/order_detail.html` used the live `cover_image()` (which silently changes when the catalogue changes). `CartItem`/`OrderProduct` had **no image field**, so the colour picked on the PDP was never captured — the variant pills came from the `variations` M2M while the image stayed the default. The colour→image knowledge existed (`ProductColorImage`, previous phase) but no order-side surface consulted it.

## 2. Variant thumbnail resolver — `store/variant_thumbnail.py`

One backend authority for every line image. Priority: **line snapshot** (`selected_image`, validated to still belong to the line's product — a foreign/poisoned FK is ignored) → **ProductColorImage** for the normalized colour (primary image, else first listed image that still exists, always product-scoped) → **product fallback** (main image, else first gallery `display_url()`) → `''` (template placeholder). Colour normalization lowercases and maps IT/FR synonyms (Nero/Noir→black, Bianco/Blanc→white, …) so localized variation values still reach the English mapping rows. Convenience methods: `CartItem.line_image_url()/line_color_value()` and `OrderProduct.line_image_url()/line_color_value()`.

## 3. Snapshot propagation

- **Add to cart** (`carts/views.py`): after the merge/create logic, `_ensure_line_snapshot` resolves and stores the colour-matched `ProductImage` on the cart line — set once at first add (quantity bumps via the cart “+” stepper never churn it). Backend-resolved only: nothing image-related is trusted from the client.
- **Finalize** (`orders/services.py::finalize_order_payment`): the snapshot is copied from the cart line to the `OrderProduct` (or resolved on the spot if missing) *before* the cart rows are deleted — webhook-safe, guest-safe. Historical orders keep the purchased colour even if the catalogue/mapping changes later (`on_delete=SET_NULL` + resolver fallback if the image itself disappears).

## 4. Enriched add-to-cart JSON

The AJAX `add_cart` success response now carries the modal payload (the pinned `quick_add` contracts are untouched):

```json
{"ok": true, "count": 2, "name": "…",
 "line": {"product_name": "…", "quantity": 1, "price": "16", "color": "Black",
          "size": "M", "image_url": "…", "thumb_url": "…", "variant_matched": true},
 "cart_url": "/cart/"}
```

`variant_matched` is true only when a colour-matched snapshot exists, so the modal's “Image reflects your selected colour” note never lies on fallbacks.

## 5. Premium add-to-cart modal

- Markup: `#atcModal` in `product_detail.html`, **outside** `#pdpForm` (no nested-form risk); `role="dialog"`, `aria-modal`, labelled title/subtitle; thumb + colour/size pills + quantity/price + note; **Continue shopping** (closes) and **View cart** (`/cart/`, href updated from `cart_url`).
- Wiring: `store-features.js` dispatches a **cancelable `glitchy:cart-added`** CustomEvent with the JSON; `add-cart-modal.js` claims it (`preventDefault`) and opens. Pages without the modal (store-grid quick add) keep the toast — zero duplicated confirmations, no double overlay (re-adds refresh the open modal).
- A11y/UX: focus trap (Tab/Shift-Tab), focus lands on *View cart*, Esc/overlay/× close (own-visibility checked — never cross-closes other overlays), focus restored to the trigger, body scroll locked, z-index 2000 (variant-guard tier), 160–200 ms discrete animation with `prefers-reduced-motion` fallback, dark/light via tokens, ≤576 px bottom-sheet with full-width buttons and safe-area padding.
- **No-JS unchanged**: the classic POST → Django message → redirect-to-cart flow never reaches any of this. Fetch failure still falls back to a native submit.

## 6. Surfaces updated

Cart, checkout summary, payments review, order complete (line thumbs added + fixed the pre-existing unguarded `{{ p.images.url }}` 500 on cover-less recommended products), account order detail (snapshot-aware instead of live cover), admin order inline (thumbnail column). Alt text everywhere: `product name — Colour`. **Mini cart does not exist** in this theme (declared); **emails and the PDF invoice use no product images** by design (declared, untouched).

## 7. Tests (+69 this phase, full suite green)

`store/test_variant_thumbnail.py` (24: resolver priorities, synonyms, foreign-snapshot rejection, fallbacks), `carts/test_variant_snapshot.py` (14: snapshot capture Black/White, JSON contract, merge keeps snapshot, no-JS redirect, finalize copy incl. guest/webhook path, surface rendering cart/checkout/order-complete), `store/test_add_cart_modal.py` (7: markup/a11y/i18n/JS literals/outside-form/CSS hidden rule) + mapping admin/runner tests (see the other doc). Full suite: `env/Scripts/python.exe manage.py test` → **1004 tests OK** (was 935 at branch start).

## 8. QA (real browser)

`docs/qa/glitchy_add_to_cart_modal_variant_thumbnail/` — modal with dark-heather thumb (dark mode), white modal, cart with both colour thumbs, checkout thumbs, mobile 390 bottom-sheet, fallback (unmapped colour → default image, note hidden). Verified live: colour-correct thumbs on cart/checkout, Esc/Continue close, re-add doesn't duplicate overlays, rapid-switch race safe, console clean, no horizontal overflow at 390/768/1440.

## 9. Deploy notes

`git pull` → `migrate` (carts 0004, orders 0010, store 0016) → `compilemessages -l it -l fr` → `collectstatic --noinput` → restart. Existing cart lines have no snapshot: they resolve via the colour mapping at render time and self-heal on the next add; historical orders fall back to the colour mapping / product image (no backfill required, optional).
