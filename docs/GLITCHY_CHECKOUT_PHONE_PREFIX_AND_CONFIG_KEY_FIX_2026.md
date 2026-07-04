# Checkout Phone Prefix + Config Key Fix (2026)

**Branch:** `fix/glitchy-checkout-phone-prefix-and-config-key` (from
`release/staging-printify-fashion-store @ 252f2a5`). **No migration.** CSS/JS/template/admin-UX
only. The i18n placeholder hotfix requested as "FASE 0" was already shipped separately as
**`252f2a5`** (on the release before this branch) — see that commit for the full repair
(placeholder parity restored, 130 msgmerge guesses emptied, strict `msgfmt -c` green).

## Bug 1 — duplicate phone-prefix selector
**Root cause:** `premium-select.js` enhances every native `<select>` site-wide into a `.pmsel`
widget (opt-out: `data-no-enhance`). The new `select[name=phone_prefix]` (kept in the DOM as the
posted source of truth / no-JS fallback for the flag dropdown) lacked the opt-out, so
premium-select wrapped it in a visible flagless `.pmsel-btn` **next to** the flag dropdown —
two prefix selectors.
**Fix (3 layers):**
1. `data-no-enhance` on the select (primary — premium-select now skips it);
2. defensive JS: if a cached older bundle already wrapped it, the flag-dropdown init hides the
   whole `.pmsel` wrapper;
3. defensive CSS `.phone-row [data-pfx]:not([hidden]) ~ .pmsel{display:none}` — scoped to
   "flag dropdown active" so a JS failure still leaves exactly one usable control.
The native select stays visually hidden (`.pfx-native-hidden`) and still posts `phone_prefix`;
E.164 validation unchanged. **Browser-verified:** 0 `.pmsel` in DOM, exactly one visible control
(SVG flags), value posted, mobile 390 no overflow.

## UX refinements (owner feedback, same phase)
- **Prefix width == phone width:** guaranteed 50/50 split (`flex:0 0 calc(50% - .25rem)` on both
  sides; equal heights via `align-items:stretch`). Verified 172px==172px (desktop),
  157px==157px (390px).
- **"Back to cart" on mobile** rendered as a 3-line block → compact one-line pill
  (`white-space:nowrap` + reduced padding at ≤575px). Verified 162×38px, no overflow.

## Bug 2 — Google API key not savable in admin
**Root cause:** the Address Validation **server key** is encrypted at rest via
`payments.secrets`, which requires the **`PAYMENT_CONFIG_KEY`** Fernet key in the server
environment. On a server without it, saving correctly refuses (no plaintext fallback — by
design) but the error surfaced only after submit and read like a crash.
**Fix (UX only, no security change):**
- premium **warning card** on the admin page shown BEFORE typing when the key is missing:
  "Encryption key missing … ask the server administrator to configure PAYMENT_CONFIG_KEY"
  (non-secret settings remain savable; the browser key is public by design);
- clearer validation error ("the key was NOT saved — it is never stored in plain text…");
- tests: without the key nothing is ever stored in plaintext and no message echoes the key;
  with the key the value is encrypted + masked (`•••• 9999 · fp:…`) and never in HTML.

### Server setup (documented dependency)
The Google server key intentionally reuses the payments encryption key (one secretbox per
deployment). To configure it on the server — generate **once**, never print/commit it:
```bash
# on the server, as the deploy user:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
  | sudo tee -a /etc/glitchy/env > /dev/null   # then edit the line into PAYMENT_CONFIG_KEY=<value>
sudo systemctl restart glitchy-gunicorn.service
```
⚠️ **Never rotate an existing `PAYMENT_CONFIG_KEY`**: every already-encrypted secret (Stripe/
PayPal configs, Google server key) becomes undecryptable. If it exists, leave it.

## Tests
`shipping/test_prefix_and_config_key.py` (5): exactly one `phone_prefix` select with the
`data-no-enhance` opt-out; defensive JS/CSS layers present; missing-key form never saves
plaintext + actionable error without echoing the key; admin page shows the warning card
(and hides it when the key is present); with key → encrypted + masked, never in HTML.
Full suite green (see report).

## Deploy notes
Server already at `14052e3` + migrations applied → this branch adds **no migration**. After
push: `git pull`, `compilemessages -l it -l fr` (now passes thanks to 252f2a5),
`collectstatic --noinput`, restart. To enable saving Google server keys: configure
`PAYMENT_CONFIG_KEY` as above (if payments secrets already work on the server, it is already
configured and nothing is needed).
