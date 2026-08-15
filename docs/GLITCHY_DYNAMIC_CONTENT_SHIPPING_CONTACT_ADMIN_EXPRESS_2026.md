# Dynamic Home Media, Checkout Shipping Sync, Contact Centre, Admin Users & Printify Express (2026)

**Branch:** `feat/glitchy-dynamic-content-shipping-contact-admin-express` (from `release/staging-printify-fashion-store @ 9b79094`). **Six additive migrations** — `store/0017`, `orders/0011`, `storefront/0002`, `accounts/0005`, `notifications/0004` (+ the store field pair in 0017). No new dependencies (Pillow was already present).

---

## 1. Dynamic homepage visuals

**Problem.** Every homepage image was a hardcoded `{% static %}` path under `images/home/pexels/`; changing one meant a deploy.

**Model.** `storefront.SiteVisualAsset` — one row per named slot (`slot` unique), `image`, optional `mobile_image`, `alt_text`, `focal_point_x/y`, cached `width/height`, `is_active`, audit fields. Slots are declared in `storefront/visuals.py::SLOTS`: `home_hero`, `home_edit_1..3`, `home_editorial`, each carrying its fallback static asset, recommended size, aspect ratio, minimums and default alt text.

**Fallback contract.** `visual_for(slot)` returns the admin's upload only when a row exists, is active and has a readable file; anything else (no row, inactive, missing file, DB error) returns the **original static asset**, so the shipped design is the permanent floor. The homepage keeps its full responsive `<picture>` markup in the default path and only swaps to a plain `<img>` when an override is active.

**Validation** (`storefront/forms.py`) rejects, with a plain-language reason: files over 5 MB, non-raster/unsupported formats (SVG included), images below the slot's minimum dimensions, and aspect ratios more than 28 % from the slot's. Alt text is required whenever an image is present. Focal point maps to `object-position`, so a crop is re-centred, never stretched.

**Admin.** *Commerce → Site visuals*: changelist with live preview, Custom/Default badge and the recommended size; the change form shows a desktop **and** mobile-390 preview pair, framing controls and a collapsed audit panel. Unchecking `is_active` instantly restores the original artwork — that is the "reset to default".

---

## 2. Checkout shipping ↔ Order summary (root cause and fix)

**Reported symptom.** "Estimate delivery" updated on country change; "Order summary" kept a static value.

**Actual root cause (worse).** Shipping was computed by **two independent engines that never spoke to each other**:

| | Order summary + real order | "Estimate delivery" widget |
|---|---|---|
| engine | `shipping.services.quote_for_cart` (settings rate table) | `printify_integration.shipping_estimator.estimate_for_cart` (Printify profiles/live) |
| destination | `detect_country()` — session/IP/default | the country typed in the form |
| gating | honoured `SHIPPING_USE_PRINTIFY` | its cached-profile tier ignored the flag |

Measured on the dev DB before the fix: IT → summary €4.90 / widget €10.00; US → summary €9.90 / widget €3.99 — a mismatch **even on the same country after a full reload**. On top of that the widget's result and the customer's chosen method were never persisted (the JS dispatched a `shipping:method` event no listener had ever been written for), and `place_order` re-priced with the *summary* engine, so the shopper was charged something they had never been shown.

**Fix — one engine, one number.**
* New `shipping/quote.py::checkout_quote()` returns the complete money picture (subtotal, discount, shipping, tax, grand total, method, options, ETA, express blockers) for one destination + method.
* `orders/totals.py::compute_cart_totals()` now delegates to it and gained `method`/address parameters, so the checkout render, the AJAX endpoint, `place_order` and the payment payloads all read the same function.
* The estimator's cached-profile tier is now gated on `SHIPPING_USE_PRINTIFY`, exactly like the money engine — the two tiers can no longer disagree.
* `/cart/shipping-estimate/` returns a `summary` block; `shipping-estimate.js` repaints `.summary-lines` (new `data-sum-*` hooks) from it and shows an "Order summary updated" flag. A user-picked method re-queries the server rather than doing arithmetic in the browser.
* The chosen method is persisted in the session (`shipping/session.py`) and re-validated server-side at `place_order`, which also stores it on `Order.shipping_method`.

Because `place_order` and the payment intents read the same totals, PayPal's breakdown identity and Stripe's amount stay consistent by construction.

---

## 3. Contact centre + assistant escalation

**Before:** "Contact" was a `mailto:` in the footer — no page, no record, no queue.

**Now:** `/contact/` (localised, also `/it/`, `/fr/`) with a premium hero, six categories (order, payment, delivery, returns, product, other), name/email/optional order number/message, and a privacy consent box. `notifications.ContactRequest` stores every request **before** dispatch, so an n8n/SMTP outage never loses a message — the row stays `pending` and is retryable from the admin.

**Anti-abuse** mirrors the proven checkout guard: hidden honeypot, signed minimum-fill-time token (3 s, 4 h max age), rate limit of 5/hour per session plus a salted-IP counter, consumed only by accepted messages. Bots receive a normal success page and nothing is stored. A double-submit inside 15 minutes is de-duplicated by a `sha256(email|category|message)` fingerprint; a later identical message is treated as a genuine follow-up. Quoted order numbers are auto-linked to the real `Order`.

**Assistant escalation.** `assistant/escalation.py` maps a question to a contact category with a small conservative keyword table (unclear → `other`) and builds `/contact/?category=…`. `_finalise()` now returns `contact_url`/`contact_category` whenever `can_contact_support` is true (sensitive refusal, out-of-scope decline and ungrounded fallback), and the widget renders a "Contact page" link next to the existing inline handoff. **Only the category travels in the URL** — never the shopper's words, so no PII or card digits can leak into a query string, referrer or access log. Nothing is ever sent without the customer pressing send.

**Admin.** *Contact requests* with masked emails in the list, status and category badges, filters, "mark as closed" and "retry sending" actions; the customer's text is read-only.

---

## 4. Inviting a second admin (and closing an escalation hole)

**Security defect found during the audit:** `AccountAdmin` exposed `is_admin`/`is_staff`/`is_superadmin` to **any** `is_admin` staffer (this project's `has_perm()` collapses to that single flag), so a staff tester could tick `is_superadmin` on their own record. Fixed on three levels: the fields are removed from the form for non-superadmins, added to `readonly_fields`, and re-read from the database in `save_model` so a forged POST cannot set them. The **last** superadmin can now neither be demoted, deactivated, nor deleted.

**Invite flow.** *Users → Invite admin user* (superadmin only, 403 otherwise): email, name, role (Staff tester / Support agent / Store manager / Superadmin). The account is created **inactive with an unusable password** — we never generate, display, email or log a password. A single-use `StaffInvite` token (72 h) is created; the link is shown once to the superadmin (deliberately NOT sent through the outbox, whose payloads staff can read). The invitee opens `/accounts/staff-invite/<token>/`, sets a password validated by Django's validators, and the account activates. Tokens are single-use and expire; an invalid/used/expired token says exactly that and touches nothing. Superadmin rights require an explicit confirmation checkbox even when the Superadmin role is chosen. `StaffInvite` is an immutable audit trail in the admin.

---

## 5. Printify Express / Priority — research and implementation

**Verified against the official OpenAPI spec** (`developers.printify.com/openapi.json`, parsed) and the help centre:

* Product payloads carry `is_printify_express_eligible` and `is_printify_express_enabled`; **each variant** carries `is_printify_express_eligible`. All three were previously ignored by the sync — now persisted on `Product`/`Variation`.
* `POST /v1/shops/{id}/orders/shipping.json` returns **every** method's cost in one call: `{"standard":…, "priority":…, "express":…, "printify_express": 799, "economy":…}` (integer cents). Absence of a key means the method is not offered for that cart/destination.
* Orders take a `shipping_method` integer (1 standard · 2 priority · 3 express · 4 economy). **Express uses a different endpoint** — `POST /v1/shops/{id}/orders/express.json` with `shipping_method: 3` and `address_to.email` **and** `address_to.phone` required.
* Express **splits** a mixed cart: the response is `data[]` with `attributes.fulfilment_type` = `express` | `ordinary`, each with its own order id.
* Business rules: US mainland only (Alaska/Hawaii excluded), no PO Boxes, eligible products/variants only, USD 7.99 + 2.40 per extra item, 2–3 business days, and it must be chosen at order placement.

**Implementation.** `shipping/express.py` answers "may we offer Express?" with safe blocker codes (`express_disabled`, `destination_not_supported`, `po_box`, `phone_required`, `email_required`, `items_not_eligible`, `empty_cart`), including PO-Box detection across both address lines and US state normalisation (`alaska` → `AK`). `checkout_quote()` hides the Express option whenever any blocker applies **or** Printify did not price it — so Belgium/EU simply never sees it, and Priority appears only when the API actually returned a `priority` cost. Selecting Express re-prices the order server-side; an Express request that no longer qualifies degrades to standard **before** payment. `build_printify_payload` now sets `shipping_method` (it was absent, so Printify silently defaulted everything to standard) and refuses to build an Express payload without email + phone; `push_order_to_printify` routes Express to the express endpoint and records the sibling order id when Printify splits the cart. The widget shows a "Fastest" badge and an honest one-line reason when Express is unavailable — copy is interpolated from config, never hardcoded delivery promises (the shipping-copy guard test forbids those).

**Kill switch:** `SHIPPING_EXPRESS_ENABLED` (default on, but every other rule still applies).

---

## 6. Tests

New: `shipping/test_express.py` (17), `shipping/test_quote.py` (17), `carts/test_checkout_shipping_sync.py` (10), `orders/test_express_submission.py` (9), `storefront/test_site_visuals.py` (22), `accounts/test_staff_invites.py` (25), `notifications/test_contact.py` (24). Updated: the estimator's cached-profile tests now pin the consistent gating. No test sends an email, creates a Printify order or calls OpenAI — clients are mocked and push is disabled.

## 7. Adversarial review — 17 confirmed findings, all fixed

A 65-agent review (5 lenses × 2 independent skeptics per finding, most reproduced with
executed probes) found real defects in this very phase. Every confirmed one is fixed and
pinned by a regression test:

**Money / shipping**
* Printify's cost map carries **both** `express` and `printify_express`, and both route to
  the express endpoint — but the eligibility filter only matched the second, so a shopper
  could get Express fulfilment on a blocked destination while paying the standard rate.
  The gate now uses `shipping.express.is_express()` for both.
* Without a live cost map the estimator labels its single fallback option with *whatever
  method was requested* and prices it from the local table. Premium methods are now dropped
  unless Printify actually priced them — a premium service can never be charged at the
  standard rate.
* An uncurated destination (any country outside the 14-entry list) rendered shipping as
  **Free** and silently dropped the coupon, then charged something else. The legacy rate
  table is used again for those destinations, discount included.
* The checkout render has no address or phone, so it cannot verify Express; the downgrade
  to standard is now persisted to the session, so `place_order` charges exactly what the
  page showed.
* `/cart/shipping-estimate/` ran the estimator twice and could mix a cached estimate's
  provenance with freshly computed money — it now builds the whole payload from one quote.

**Admin security**
* `UserAdmin` exposes `/<id>/password/` regardless of hidden fields — a plain staffer could
  set a superadmin's password and sign in as them. Now superadmin-only (own password still
  allowed).
* The invite token is a takeover credential: it is no longer rendered in the StaffInvite
  admin (which is now superadmin-only) and **no longer travels through the outbox**, whose
  payloads any staffer can read. The superadmin copies the link once and shares it.
* Bulk `delete_selected` bypassed the last-superadmin guard; `delete_queryset` now keeps one.
* The lock-out guard restored `is_superadmin`/`is_active` but not `is_staff`, so the last
  superadmin could still be locked out.
* A pending, never-accepted invite permanently blocked re-inviting that email; invites can
  now be revoked, and a dormant pending account is reused.

**Contact centre**
* An expired or missing anti-bot token silently binned a genuine customer's message; only a
  suspiciously fast submit is now treated as a bot, and an aged form asks the customer to
  send again.
* The permanent fingerprint dedupe swallowed follow-ups and blocked retries after a failed
  dispatch — it is now a 15-minute window that ignores failed rows.
* The rate limiter counted rejected submissions, so a few typos locked a customer out for an
  hour; only accepted messages consume budget, and the session-only limit is backed by a
  salted IP counter (never storing the raw IP).

## 8. QA

Browser QA on the local dev server at 1440 (desktop), 768 (tablet) and 390 (mobile), with
screenshots in `docs/qa/glitchy_dynamic_content_shipping_contact_admin_express/`:

| File | What it shows |
| --- | --- |
| `admin-homepage-visuals.png` | Site visuals changelist: every slot, Custom/Default badge, live preview |
| `admin-homepage-visuals-form.png` | Change form: desktop + mobile-390 preview pair, framing controls |
| `homepage-custom-image-preview.png` | Homepage rendering an admin upload in the hero slot |
| `checkout-shipping-summary-sync.png` | Country change: estimate and Order summary showing the same number |
| `contact-page-premium.png` | `/contact/` at desktop width |
| `contact-page-mobile-check.png` | `/contact/` narrow-viewport check |
| `admin-invite-user.png` | Invite form with role descriptions and the superadmin confirmation |
| `admin-invite-user-created.png` | Generated single-use link, token painted out of the frame |

Two honest notes on `admin-invite-user-created.png`: the token was redacted after capture (it is a
credential and must never live in the repository), and the frame still reads *"It was also queued
by email"* because it was taken before the review fix that stopped routing the link through the
outbox. The current build never emails it — `email_sent` is always false and that sentence no
longer renders.

Honest limitation: the automation window could not be resized below the maximized viewport and
iframes are blocked by `X-Frame-Options`, so the 390 px pass was verified in a `window.open`
popup sized 390×844 — measuring `innerWidth 390`, `scrollWidth 390`, no horizontal overflow on
`/`, `/contact/`, `/it/contact/` and `/cart/checkout/` — but a true 390 px screenshot could not be
captured from that popup. The mobile screenshot above is a narrow-window check, not a 390 px frame.

## 9. Internationalisation

Every customer-facing string added by this phase is translated in IT and FR (contact page and its
validation messages, delivery method labels and delivery windows, Express notes and blocker
explanations, the invite-acceptance page). `msgfmt --check-format` passes on both catalogues and
`/it/contact/` and `/fr/contact/` render translated. Admin-facing strings in the Printify, payments
and store control centres remain English, as they were before this phase.

## 10. Deploy notes

`git pull` → `migrate` (store 0017, orders 0011, storefront 0002, accounts 0005, notifications 0004) → `compilemessages -l it -l fr` → `collectstatic --noinput` → restart. Media uploads need `MEDIA_ROOT` writable and served (the site visuals use `/media/site_visuals/`). Optional settings: `SHIPPING_EXPRESS_ENABLED` (default true), `SHIPPING_USE_PRINTIFY` (unchanged default false — with it off, both the summary and the widget use the local rate table, consistently).
