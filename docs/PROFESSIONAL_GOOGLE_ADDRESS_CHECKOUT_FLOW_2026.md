# Professional Google Address Checkout Flow (2026)

**Branch:** `feat/glitchy-professional-google-address-checkout-flow` (from
`release/staging-printify-fashion-store @ 581d7c3`). **Migrations:** `shipping/0002`
(validation_mode) + `orders/0009` (google_place_id / address_verified /
address_manual_confirmed) — additive, deploy needs `migrate`. No deploy, no real
payment/order/mutation; Google always mocked/stubbed in tests and QA.

## 1. Audit findings
Fields were ordered name→email→phone→**street→city→state→postal→country** (country LAST).
The previous Places integration used the stock `places.Autocomplete` widget with **no country
restriction and no context bias**, loaded only when a browser key is configured — with no key
(the usual state so far) nothing could ever appear, and even with a key the suggestions ignored
the destination the shopper had already typed. No `place_id` reached the backend; there was no
verification contract at all (any free text passed).

## 2. Professional field order
Three premium sections: **1 Contact** (name/email/phone with the SVG-flag prefix) →
**2 Delivery destination** (Country, State/Region/Province, City, Postal code — all BEFORE the
street) → **3 Street address** (street+number with suggestions, optional line 2) + a
**verification status** row (verified badge / not-verified hint / manual-mode note). Inline
errors and full field preservation (session stash) kept from the previous phases.

## 3. Real suggestions (custom prediction list)
Replaced the stock widget with **AutocompleteService + PlacesService** (`js/address-autocomplete.js`):
full design control and real context filtering —
- **country**: `componentRestrictions={country}` (hard filter from the Country select);
- **city/postal**: appended to the query as bias (destination fields are before the street by
  design, so the context exists when the shopper types);
- session tokens for correct Places billing; 250ms debounce; ≥3-chars state; "no suggestions"
  state; premium list (location icon, main/secondary line, hover/keyboard nav, Escape);
- selection → Place Details (`address_components`) fills street+number, city, state, postal,
  country, and the hidden contract: `google_place_id`, `address_verified`
  (only when route+city+postal+country are ALL present), `address_validation_source`;
- any manual edit of the street or destination fields **resets the verification** (badge flips
  to "not verified");
- `gm_authFailure` / script failure → honest manual fallback, form untouched.

## 4. Server-side contract (anti-spoof)
`shipping/address_validation.py`:
- `effective_mode(cfg)` → disabled (no/off config) / warning / strict — **strict degrades to
  warning when neither Google surface is usable** (a misconfigured admin can never lock all
  customers out);
- `verify_for_order(cfg, data, place_id)` — STRICT verdict: requires a sane `place_id`
  (**hidden `address_verified` alone is never trusted — test-asserted spoof case**), local
  shape checks, and when the encrypted server key is configured a **fail-CLOSED** Google
  Address Validation pass (non-200/timeout/ambiguous → order blocked with a retryable message).
  Without a server key: documented browser-trust mode (place_id + local checks).
`place_order` wires the modes: strict → verify or block; warning → unverified needs the explicit
"I confirm this address is correct" checkbox; disabled → local checks + confirm flow. The Order
rows record `google_place_id` / `address_verified` / `address_manual_confirmed` (audit trail).

## 5. Admin
`CheckoutApiConfig.validation_mode` (Disabled/Warning/Strict, superadmin-gated, styled Unfold
select) beside the existing switches; browser key (public, referrer-restricted) vs encrypted
server key (write-only, masked, requires `PAYMENT_CONFIG_KEY` — warning card when missing,
never rotate an existing key) unchanged from the previous phase.

## 6. Privacy / GDPR
No precise browser geolocation; no address ever logged (only safe status codes/exception class
names); lat/lng never requested (only `address_components`); Places calls are user-initiated
typing with session tokens; server validation posts only the fields the shopper is submitting
to us anyway, over TLS to Google, read-only.

## 7. Tests (15 new, green) + QA
Matrix: effective-mode (off/degrade/kept), verify_for_order (no place_id, spoofed hidden,
local-shape block, browser-trust pass, mocked Google ambiguous→block, outage→fail-closed,
success→pass), place_order per mode (strict blocks spoof, strict accepts selection, warning
requires checkbox then records the flag, disabled manual OK), template order + contract markup.
Browser QA (Google stubbed client-side, real script blocked — zero external calls): field order,
suggestions for France (restriction 'fr' + bias '75001 Paris' captured from the request),
selection fills all fields + verified badge, manual edit resets, strict submit blocked with
fields preserved, warning submit → confirm checkbox, mobile 390 no overflow, admin mode select +
key warning. 8 screenshots in `docs/qa/professional_google_address_checkout_flow/`.

## 8. Limits (honest)
- Live end-to-end with a REAL Google key is a deploy-time smoke (everything here is
  mocked/stubbed by design — no real API calls allowed).
- Street number is part of the street field (route+number combined — standard IT/FR format);
  a separate civic-number input was deliberately not added.
- In strict + no-server-key, trust rests on the browser-provided place_id (documented); for
  maximum assurance configure the server key so verification is server-side and fail-closed.
- Suggestions require JS; no-JS falls back to manual entry governed by the same server modes.

## 9. Deploy notes
`pip` unchanged. **`migrate` required** (shipping/0002 + orders/0009). `compilemessages -l it
-l fr` (strict `msgfmt -c` verified) + `collectstatic` + restart. Then in admin → Checkout API
settings: browser key + enable autocomplete → suggestions go live; server key + enable
validation → strict becomes fully server-verified; pick the mode (start with Warning, move to
Strict once the keys are confirmed working).
