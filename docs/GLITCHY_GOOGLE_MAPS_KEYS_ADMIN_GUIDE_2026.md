# Google Maps Keys — Admin Guide & Diagnostics Fix (2026)

**Branch:** `fix/glitchy-google-maps-keys-admin-diagnostics` (from
`release/staging-printify-fashion-store @ 4ad5577`). **No migration.** Admin UX/diagnostics only.

## The reported bug — "Connection failed — Key rejected (403)"
**Root cause:** the admin's only "Test connection" ran a **server-side** Address Validation call.
A **browser key restricted by HTTP referrers always returns 403 when called from a server**
(there is no referrer) — so pasting the browser key into the server-key slot, or expecting that
button to test the browser key, produced a false negative with a terse message. The two keys
were also presented in one combined fieldset, inviting exactly that confusion.

## The two keys (never interchangeable)
| | **Browser key** (`Maps browser key`) | **Server key** (encrypted slot) |
|---|---|---|
| Visibility | Public by design (in the page HTML) | Secret — encrypted at rest, masked |
| Restriction | **HTTP referrers**: `https://glitchy.graphics/*`, `https://www.glitchy.graphics/*` (+ http variants if needed) | **IP addresses**: the server's public IP |
| APIs | Maps JavaScript API + Places API | Address Validation API (+ Places API if Place Details) |
| Used by | Checkout street autocomplete (client JS) | Server-side address verification (strict mode) |
| Test | **In the browser** (new admin button) | Server-side dummy-address call |
| Requires | Billing enabled | Billing + `PAYMENT_CONFIG_KEY` on the server |

## Fixes
1. **Client-side browser-key test** (option A): "Test browser key in this browser" loads Maps JS
   with the saved key in the ADMIN's browser (the referrer check needs a real page) and runs one
   live prediction — green "Browser key works…" or the actual Google failure with a checklist.
   The key is never logged; nothing saved.
2. **Browser key is never tested server-side** (test-asserted: no `requests` call happens when
   only a browser key exists).
3. **Server-key diagnostics**: 403 now explains the real causes (API not enabled / billing off /
   wrong application type / server IP missing from the key / a browser key pasted in the server
   slot); 400 = malformed key; 429 = quota; missing/changed `PAYMENT_CONFIG_KEY` = precise
   message (decrypt is fail-soft, now checked explicitly before calling Google).
4. **Anti-confusion guard**: saving a server key identical to the browser key is rejected with
   "This is your BROWSER key — the server key must be a DIFFERENT key…".
5. **Two premium admin sections** with full checklists (referrers, APIs, billing, restrictions)
   replacing the combined fieldset.

## Server setup reminders
- `PAYMENT_CONFIG_KEY` must exist on the server to save/decrypt the server key (generate once:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`,
  put in `/etc/glitchy/env`, **never rotate once secrets are stored**, never print it).
- After changing keys in the Google console allow a few minutes for propagation.

## Tests (8 new)
Browser key never called server-side; 403 diagnostics mention billing/referrer/IP/enabled and
never echo the key; 400/429 mapped; missing `PAYMENT_CONFIG_KEY` precise message with zero
Google calls; same-key guard; admin page shows both sections + exact referrers + client-test
markup; server key never leaks in HTML (the public browser key legitimately appears in its own
input). Full suite green.

## Deploy notes
No migration. `git pull` → `compilemessages -l it -l fr` → `collectstatic` → restart. Then in
admin follow the two checklists; verify the browser key with the in-browser button (or simply
open checkout and type a street), and the server key with the server-side test.
