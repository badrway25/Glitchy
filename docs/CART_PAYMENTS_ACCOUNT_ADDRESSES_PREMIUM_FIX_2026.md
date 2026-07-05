# Cart, Payments & Account Addresses — Premium Fix (2026)

**Branch:** `fix/glitchy-cart-payments-account-addresses-premium` (from
`release/staging-printify-fashion-store @ 7af4d78`). **Migration:** `payments/0002`
(cherry-picked from the pending F76B — allow_capture/allow_refund gates + paypal_webhook_id) →
**deploy needs `migrate`**. No real payments/orders (Stripe test-mode only in local QA).

## 1. Root cause — "Stripe intent creation failed" (LIVE)
Three stacked problems:
1. **Config**: the live server has no Stripe key in env AND the admin Payment Control Center
   (Phase 76) **rendered no credential fields on the add form** — the exact bug fixed by the
   pending F76B commit `ab6123c` ("provider add form showed no fields for the Stripe/PayPal API
   keys"). The owner literally could not enter keys.
2. **Code**: `stripe_create_intent` swallowed every exception into a generic 500
   ("Stripe intent creation failed") with **zero logging**.
3. **Frontend**: the Card tab is active by default but Stripe mounted **only on click** — the
   page could sit on "Loading…" or surface the error only after re-clicking the tab.

**Fixes**: F76B core cherry-picked (see §3); the intent view now pre-checks the resolver
(`no key → 503` with a translated, elegant message), catches Stripe errors with safe logging
(error class + Stripe code + order number — never the key, never PII) and returns friendly
retryable copy; the payments page mounts Stripe on load for the active tab with the same
elegant catch. **Verified locally end-to-end**: with the dev test key the Payment Element
mounts and the intent succeeds (test mode, no confirm/capture).

## 2. Root cause — PayPal never visible (LIVE)
**Code bug**: the context processor fed the template `PAYPAL_ENABLED` / `PAYPAL_CLIENT_ID`
straight **from env**, ignoring the resolver — a PayPal configured in the admin DB could never
appear. Fixed: the context processor now uses `payments.config.paypal_available()` /
`paypal_client_id()` (admin DB preferred, env fallback, fail-open to the old behaviour).
**Verified**: with env PayPal OFF and an enabled admin config, the PayPal tab renders.

## 3. F76B integration (analyzed, selective — NOT a blind merge)
Cherry-picked: `ab6123c` (credential fields on add+change, payment-admin.js provider-section
toggle, masked per-provider status, migration payments/0002), `af0b9ce` (control-center guidance
polish), `900648d` (tests — minus the two classes belonging to excluded commits).
**Excluded on purpose** (still pending, documented): the admin language switcher (`86cc950`) and
its i18n catalog (`3b013ed`) — they conflict with four later i18n phases; and F76B's docs/QA
commits. Nothing else from F76B remains needed for payments.

## 4. Admin checklist (what the owner must configure)
- **Stripe**: publishable key (plaintext) + secret key (write-only, encrypted) in the Stripe
  provider row → enable + allow checkout; sandbox environment; live only behind the live gate.
- **PayPal**: client ID (plaintext) + secret (encrypted) → enable + allow checkout; sandbox.
- **`PAYMENT_CONFIG_KEY`** must exist on the server to save encrypted secrets (already required
  by the Google server key — same warning card pattern; never rotate once secrets exist).
- Test connection buttons are read-only.

## 5. Cart polish
`Remove` was a heavy red pill (weight 900, red border/bg) → now a quiet ghost action (muted,
borderless, small; danger tint only on hover; visible focus). `.cart-thumb` had a visible
border + shadow (theme.css second definition) → now the checkout-style soft container (no
border, soft background, radius). Mobile 390 verified.

## 6. Account address book — checkout parity
- **Form** (`/accounts/addresses/…`): same Google autocomplete as checkout on street/city/
  province/postal (the shared `address-autocomplete.js` controller is reused as-is — the form
  exposes the same ids/data-attributes via `AddressForm` widget attrs + template suggest
  lists/hints), flag-SVG phone prefix component (global store-features JS), **E.164 server
  validation** via a new shared helper `orders.forms.clean_international_phone` (single source
  for checkout + address book), honest multi-CAP hint, manual fallback without Google.
  The verification contract fields exist client-side but are NOT persisted for the address book
  (no migration needed; enforcement stays a checkout concern).
- **List**: Edit / Set default / Delete refined into quiet ghost pills (delete = subtle danger);
  the existing confirm modal kept.
- **Verified in browser**: flags, 4 suggestion lists, Torino → city+TO fill, mobile 390 clean.

## 7. Tests
5 new payment tests (intent 503-elegant without key, success mocked with integer cents, friendly
502 on Stripe error without leaking internals, PayPal visible from admin config with env off,
PayPal hidden when nothing configured) + F76B's credential-field tests + all targeted suites
(payments/carts/orders/accounts/shipping) and the full suite green.

## 8. Deploy notes
```bash
git pull
python manage.py migrate            # payments/0002
python manage.py compilemessages -l it -l fr
python manage.py collectstatic --noinput
sudo systemctl restart glitchy-gunicorn.service
```
Then in **admin → Payment Control Center**: enter Stripe sandbox keys + PayPal sandbox
credentials (fields now exist), enable + allow checkout. Requires `PAYMENT_CONFIG_KEY` in
`/etc/glitchy/env` (generate once, never rotate — see the Google keys guide). Card + PayPal
then work in sandbox; move to live only behind the live gates after a sandbox smoke.

## 9. Limits
- Live Stripe/PayPal smoke with the owner's sandbox keys is a post-deploy step.
- F76B's admin language switcher + i18n catalog remain pending (documented exclusion).
- The address book intentionally does not enforce verification modes (checkout-only policy).
