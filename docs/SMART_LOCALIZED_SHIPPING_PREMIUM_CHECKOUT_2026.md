# Smart Localized Shipping + Premium Checkout Validation (2026)

**Branch:** `feat/smart-localized-shipping-premium-checkout-validation` (from
`release/staging-printify-fashion-store @ c9253be`). Migrations: `orders/0008` (phone→20 chars,
fits E.164) + `shipping/0001` (CheckoutApiConfig). New package: `phonenumbers==9.0.34`.
No deploy, no real payment/order, no mutative API call.

## 1. Audit
The infrastructure was largely in place: `shipping/geo.py` (session → CF-IPCountry header →
cached → optional IP lookup → default, GDPR-safe, no browser geolocation), the settings rate
table (door-to-door days, unified funnel-wide in the previous phase), a footer country switcher
and `set_country` endpoint. Real gaps: the PDP line presented the **default country as fact**
("Ships to Italy…") even when nothing was detected; `place_order` **discarded every typed field**
on a validation error (P10); `phone` was an unvalidated CharField(15); no anti-bot at all; no
address autocomplete/validation; no admin config for Google APIs.

## 2. Country determination (privacy-safe priority)
`shipping.geo.detect_country_info()` (new) returns the code **and the source**:
manual (user choice, wins) → CDN country header → session-cached auto-detection → optional IP
lookup (off by default) → default (**an assumption, flagged as such**). No precise browser
geolocation, no consent-less external calls.

## 3. Honest "Ships to …" (PDP + quick view)
`shipping/localization.py::localize_shipping(request, subtotal, quantity)` → structured dict
(country_code/name, known, supported, cost/eta labels, source, is_fallback, line_label). Rules:
- known + curated + rated → `Ships to France · €6.90 · 4–8 business days` (real table figures —
  the SAME the checkout charges);
- known but outside the curated name list → neutral copy (the worldwide default rate still
  applies at checkout);
- **source == default (nothing detected) → "Shipping calculated at checkout based on
  destination"** — never presents the assumption as fact;
- free threshold reflected only when actually crossed (`Free shipping`).
The PDP line is now the `_ships_to.html` partial + a discreet premium "Change ▾" country listbox
(JS-revealed; no nested form — the partial lives inside #pdpForm; no-JS keeps the honest static
line). Quick view uses the same localizer. **Browser-verified:** neutral → pick France → real
figures → persists in session.

## 4. AJAX endpoint
Extended `POST /shipping/set-country/`: strict 2-alpha validation (400 otherwise), stores the
manual choice in session, AJAX response now includes the full `localized` summary. Read-only,
no secrets, no payment.

## 5. Checkout — field preservation (fixes prior-phase P10)
Invalid `place_order` now **stashes every typed field + per-field errors in the session**
(`_stash_checkout`) before the PRG redirect; the checkout view (`_checkout_extras`) restores the
values into the inputs and renders inline `field-error` messages. **Browser-verified:** invalid
phone → back on checkout with Marco/Via Roma 1/Milano intact + "This phone number looks too
short or too long." inline.

## 6. International phone validation
- Server (authoritative): `OrderForm.clean` with **phonenumbers** — charset check, prefix+number
  combination (already-international input wins), `is_possible`/`is_valid`, stored normalized
  **E.164** (`+393331234567`); Order.phone widened to 20 chars (migration 0008).
- UI: premium prefix dropdown with **real SVG flags** (local inline SVGs — Windows renders flag
  emoji as plain letters, hence no emoji), dial + country name in the open list, flag+dial in the
  trigger; native `<select>` remains as the no-JS fallback and the posted source of truth;
  prefix auto-selects from the visitor's shipping country.

## 7. Anti-bot (checkout)
`_checkout_guard`: invisible **honeypot** (`website`, off-screen), **minimum form time** (signed
server timestamp, ≥3s, forgery-proof via django.signing), **rate limit** (8 submits / 10 min per
hashed session/IP — no PII stored). Generic error message on trip (no oracle). No CAPTCCHA
dependency; CSRF unchanged. Tests prove: honeypot blocks, too-fast blocks, no Order is created.

## 8. Address autocomplete (Google Places) — optional, fallback-first
Loaded **only** when the admin enabled it AND set a browser key: classic Places Autocomplete on
Address line 1, filling city/postal/state/country; the Google suggestion dropdown is restyled to
match the design system (`.pac-container`). The **browser key is public by design**
(referrer-restricted — stored plaintext like a publishable key). Not configured → nothing loads,
manual entry unchanged. Script failure → form untouched (autocomplete is an enhancement, never a
dependency).

## 9. Server-side address validation — warning-only
`shipping/address_validation.py`:
- **local rules always**: per-country postal-code shapes (warning), obviously-incomplete street;
  plus form-level normalization (whitespace, control chars, lengths) in OrderForm;
- **Google Address Validation** only when enabled + server key set: read-only, 4s timeout,
  **fail-open** (network error → proceed), `hasUnconfirmedComponents` → premium warning banner
  with a "My address is correct — continue" checkbox (`address_confirmed`) — **never blocks** a
  confirmed address; no full address ever logged.

## 10. Admin — Checkout API settings (Google)
`shipping.CheckoutApiConfig` (singleton, migration shipping/0001), admin mirroring the Payment
Control Center: master + per-feature switches (default **OFF**), plaintext browser key (public),
**encrypted write-only server key** (reuses `payments.secrets` / `PAYMENT_CONFIG_KEY` — documented),
masked `•••• 2222 · fp:…`, superadmin-only secrets/switches, POST-only read-only **Test
connection** (validates a fixed dummy address — never a customer's), safe status panel.
Verified: key never in HTML, masked shown, staff denied.

## 11. Funnel coherence
PDP, quick view, cart/checkout estimator and the order snapshot all read the same rate table
(prev phase) — the new localizer formats from `fallback_quote` directly, so figures can never
diverge. Guard test from the previous phase still enforces estimator==table.

## 12. i18n
All new strings translated it/fr (Ships to / calculated at checkout / phone errors / address
warning / confirm label / picker labels). A de-fuzzy pass fixed a broader gotcha: entries flagged
`#, fuzzy, python-format` (combined flags) were excluded from `.mo` — 71 it + 82 fr previously
translated entries are now active.

## 13. Tests (19 new, all green)
Localization (neutral default / manual wins / header detection / uncurated fallback / free
threshold / endpoint validation), phone (E.164 normalization, international kept, too-short,
letters), anti-bot (honeypot, min-time, no Order side effects), preservation (session stash +
re-rendered values), API config (encrypted+masked, never in HTML, staff denied, test-connection
mocked read-only, Google validation warning-only + fail-open, local postal shapes, no Google
script when unconfigured).

## 14. QA (browser, console 0, overflow 0 at 390/1440)
PDP neutral + France + persistence; picker open; checkout prefix dropdown with SVG flags (menu
verified: 14 flags); invalid submit → fields preserved + inline error; admin config masked;
mobile 390 checkout. Screenshots in `docs/qa/smart_localized_shipping_premium_checkout/`.

## 15. Deploy notes
- `pip install -r requirements.txt` (adds **phonenumbers**).
- **`migrate`** (orders/0008 + shipping/0001).
- `collectstatic` + `compilemessages -l it -l fr` + restart.
- Optional: in admin → *Checkout API settings* → add the referrer-restricted browser key (+
  enable autocomplete) and/or the IP-restricted server key (+ enable validation) → Test
  connection. Checkout keeps working untouched without any of it.

## 16. Limits (honest)
- Google integrations are OFF by default and verified with mocks — a live smoke with real
  restricted keys is a deploy-time step.
- The address-warning confirm flow re-renders via redirect (PRG) — a JS inline confirm would be
  a further polish.
- Dial-prefix list covers the 14 curated shipping countries (matches where we ship).
- No CAPTCHA provider integration (honeypot+time+rate limit chosen); can be added later behind
  the same admin config pattern.
