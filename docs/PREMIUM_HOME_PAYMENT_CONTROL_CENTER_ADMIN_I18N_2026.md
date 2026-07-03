# Premium Home Cards + Secure Payment Credentials Admin + Admin i18n (Phase 76, 2026)

**Branch:** `feature/premium-home-payment-control-center-admin-i18n` (from
`release/staging-printify-fashion-store` @ `cdb90bf`). **New app `payments` + migration
`0001`.** No deploy. No real payment created/captured/refunded. Secrets encrypted, write-only.

Grounded in a 6-reader audit of the real payment stack (Stripe + PayPal both integrated).

## 1. Home trust cards — uneven → premium
`.lux-feature` cards ("Premium fabrics / Made on demand / Honest pricing / Designed to last")
had no min-height, line-height or clamp, so they stretched unevenly. **Fix:** the card is now a
full-height flex column (`display:flex;flex-direction:column;min-height:100%`) inside the
existing `d-flex` column, so the four cards equalise per row at every breakpoint; descriptions
get explicit `line-height` and, when JS is on, a 2-line clamp. A discreet **"Read more"** trigger
appears **only when the text actually overflows** and opens a native `<dialog>` detail modal
(free focus-trap + ESC + backdrop-click, `home-features.js`, reduced-motion safe). No JS → full
text stays visible (accessible, SEO-safe). Verified in the browser: desktop cards equal-height;
mobile 390 shows the read-more + the elegant modal.

## 2. Secure Payment Control Center (mirrors Printify)
New `payments` app. `PaymentProviderConfig` (one row per provider: Stripe / PayPal):
- **Server secrets Fernet-encrypted at rest** (`PAYMENT_CONFIG_KEY`, separate from
  `PRINTIFY_CONFIG_KEY`): Stripe `secret_key` + `webhook_secret`, PayPal `secret`. Stored as
  ciphertext + fingerprint + last-4; **write-only** in the admin (`PasswordInput render_value=
  False`); never rendered — only a masked `•••• 9999 · fp:…` is shown. Decrypted server-side
  only. Fail-closed: entering a secret with no `PAYMENT_CONFIG_KEY` is refused.
- **Public keys in plaintext** (already browser-exposed): `stripe_publishable_key`,
  `paypal_client_id`, `paypal_api_base`.
- **Safe defaults:** every provider ships `is_enabled=False`, `environment=test`,
  `allow_checkout=False`, `allow_live_mode=False`. Live keys are never served unless the live
  gate is explicitly on. Secrets + the dangerous switches are **superadmin-only**
  (`get_form`/`get_fieldsets`/`get_readonly_fields`); a non-superadmin can't see or set them and
  gets 403 on Test connection (test-asserted).
- **Admin** = a Printify-style change form: provider / keys / payment operations / safety gates /
  connection status, with a masked secret-status panel + a **Test connection** button.

## 3. Read-only connection tests
`payments/services.py`: **strictly read-only**. Stripe = `Account.retrieve` + `Balance.retrieve`
(reports account id masked, currency, charges_enabled); PayPal = OAuth2 client-credentials token
+ scope read. It detects invalid key, test/live mismatch, missing permissions, rate-limit and
network errors, records a safe summary, and **never** creates a PaymentIntent / Checkout Session
/ Order, never captures, never refunds (test-asserted with a mock). Each test writes a
`PaymentEvent` audit row.

## 4. Checkout credential resolver (backward-compatible)
`payments/config.py` resolves credentials **DB-preferred, ENV-fallback, safety-gated**. Wired
into `orders/views.py` (Stripe intent/confirm/return/webhook set the key per request) and
`orders/paypal.py` (client id / secret / api base + availability). Behaviour is **identical to
today** until an owner enables a config in the admin — with no config it returns the same env
keys as before (test-asserted). Live keys require `allow_live_mode`.

## 5. PaymentEvent monitor
Lightweight, read-only audit log (`PaymentEvent`) — provider, kind (test/webhook/verify/refund/
finalize), external id (idempotency), ok/status/reason, amount/currency. Written from the Stripe
webhook (incl. signature-reject), PayPal verify, and test connection. No secrets, no card data,
no full PII. Closes the audit's biggest gap (there was no queryable payment trail).

## 6. Admin i18n
The admin was not localizable like the site. **Fix:** wrapped the Unfold sidebar titles + site
title/subtitle, the `admin_ext` environment badge, the Printify status badge, and all the new
payment admin strings in `gettext_lazy` (using the standard `_` alias — a custom alias would not
be harvested by `makemessages`). Added a **Payment control** sidebar section. Harvested into the
`it`/`fr` catalogs and translated the admin-chrome strings; `compilemessages` built the `.mo`.
Verified with `gettext`: under `it`, "Payment control" → "Controllo pagamenti", "Products" →
"Prodotti", "Test connection" → "Prova connessione", etc. The storefront already switches
languages via `/it/`, `/fr/` (verified `<html lang="it">`).

## 7. Deploy notes
- **`migrate`** required (`payments/0001`).
- New env key **`PAYMENT_CONFIG_KEY`** (a Fernet key) — without it, saving a payment secret is
  refused (fail-closed); resolver still falls back to the existing env keys, so checkout keeps
  working. Also `collectstatic` (home-features.js + CSS) and `compilemessages -l it -l fr`.
- No new pip dependency (Stripe SDK + `cryptography` already present).

## 8. Security
No Stripe/PayPal secret, no `PAYMENT_CONFIG_KEY`, no webhook secret ever appears in HTML / JSON /
messages / logs (test-asserted); DB stores ciphertext; forms are write-only + masked;
non-superadmin denied; no real payment/capture/refund; live mode gated. No PII in reports/
screenshots (demo data used fake emails/keys, cleaned up).

## 9. Tests
`payments/tests.py` (11): secret encrypted-not-plaintext, never in change HTML, non-superadmin
can't see/set/test, test-connection read-only (mock — no PaymentIntent/Charge/Refund), safe
defaults OFF, resolver env-fallback + DB-preferred + live-gate, PaymentEvent idempotent,
admin strings translatable to Italian. `store/test_home_cards.py` (3): read-more + dialog markup,
equal-height/clamp CSS, progressive-enhancement JS.

## 10. QA
Browser, console 0: home cards equal-height (desktop) + read-more modal (mobile 390); Payment
Control Center list + Stripe/PayPal change forms (secrets masked, no leak, Test button, safety
gates OFF, sidebar Payment section). 4 secret/PII-safe screenshots in
`docs/qa/premium_home_payment_admin_i18n/`.

## 11. Limits / deferred (honest)
- **Admin live language toggle:** admin strings are translatable + translated + gettext-verified,
  and the storefront switches languages; but the admin is outside `i18n_patterns` and (Django 6
  removed the session-language key) did not switch language in QA via cookie/Accept-Language. The
  wiring of an in-admin language switcher is a follow-up — the translation work itself is done.
- **Arabic / RTL: deferred entirely** — the site has no Arabic language (LANGUAGES = en/it/fr);
  adding AR means a full catalog + `dir=rtl` handling + an RTL stylesheet (a phase of its own).
- **Full admin catalog translation:** the admin *chrome* (sidebar/payment/status) is translated;
  the `admin_ext` dashboard chart labels remain English pending translation (wrapping done for
  the visible chrome; the rest is incremental).
- **Deferred payment ops** (per the audit): PayPal refund/void + PayPal webhook, a full financial
  ledger (Refund/Settlement/Dispute/Balance models), and the `Payment.amount_paid` CharField→
  Decimal migration. The Stripe dashboard already covers reconciliation/disputes/payouts.
- Live Test connection / checkout need real valid keys on the server; QA uses mocks (never a real
  secret).
