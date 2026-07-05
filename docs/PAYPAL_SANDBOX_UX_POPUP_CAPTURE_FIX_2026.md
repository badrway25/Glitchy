# PayPal Sandbox UX, Popup & Capture Fix (2026)

**Branch:** `fix/glitchy-paypal-sandbox-ux-popup-capture` (from
`release/staging-printify-fashion-store @ 19c7a9b`). **No migration.** Sandbox only, tests
mocked, no live payments. Webhook still excluded (unchanged rationale).

## Root causes (live sandbox smoke)
1. **~1-minute hang on "Grazie per avere usato PayPal" then "PayPal encountered a problem"** —
   the order was created server-side WITH `payment_source.paypal.experience_context`, which
   pushes PayPal into the payer-action flow, while the JS still ran a **client-side
   `actions.order.capture()`**. That combination is incompatible: the client capture stalls
   against a server-created order and eventually fires the SDK `onError`.
   **Fix (two sides):** the payload now uses **`application_context`** (same preferences —
   SET_PROVIDED_ADDRESS, PAY_NOW, brand, locale — in the SDK-Buttons-compatible shape), and
   capture is now **SERVER-SIDE**: `onApprove` POSTs to the new `/orders/paypal/capture/`,
   which calls `/v2/checkout/orders/{id}/capture`, maps statuses precisely (COMPLETED /
   INSTRUMENT_DECLINED→retry / PENDING→polite hold / other), verifies **amount+currency from
   the capture response itself**, stores the REAL capture id and finalizes idempotently.
2. **Blank white window next to the real PayPal window** — same `payment_source` conflict
   (payer-action flow opening its own context) plus the multi-funding render. Gone with
   `application_context` + a **render-once guard** (`__ppRendered`) + single funding source.
   No `window.open` anywhere (SDK owns the popup; test-asserted).
3. **Three stacked black buttons** — `layout:'vertical'` + `color:'black'` rendered the whole
   funding stack (PayPal / Pay Later / card). Now: **one gold pill button**
   (`fundingSource: paypal.FUNDING.PAYPAL`, `color:'gold'`, `shape:'pill'`, height 48) and the
   SDK query hard-disables `paylater,card,credit,venmo`.
4. **Console `503`** — that request is the **Stripe create-intent** on a live server where the
   Stripe keys are not yet configured in the admin: it is the *intentional elegant 503* from the
   previous phase ("Card payments are not configured yet…"), not a PayPal failure. It
   disappears as soon as the Stripe sandbox keys are saved in the Payment Control Center.
5. **CSP `unsafe-eval` warnings + `<svg> height="auto"` React error** — audited: this project
   sets **no CSP header in Django** and **no template/JS of ours uses `height="auto"`**
   (QA-asserted on the rendered page). Both messages originate from **PayPal's own hosted
   frames/scripts** (their React UI, their telemetry) logging into the page console — sandbox
   noise we cannot fix and do not need to: the flow works without adding `unsafe-eval`, so
   **no CSP loosening was done**. If a reverse-proxy CSP is ever added on the server, whitelist
   `*.paypal.com *.paypalobjects.com` in `script-src`, `connect-src`, `frame-src`, `img-src`
   for the payment page.

## What is / isn't controllable in the PayPal window
Controllable: which buttons render (single gold pill), brand name, locale, the address and
itemized totals shown inside (our payload), our panel around the buttons, loading/error states.
NOT controllable: the popup window's own size/layout/inner styling and its console output —
it is PayPal-hosted UI.

## Frontend UX
`.pp-status` line drives honest states: "Connecting to PayPal…" (createOrder), "Confirming
your payment…" (capture, with a 45s AbortController timeout → "do NOT pay again — contact us"
message), "Payment confirmed — redirecting…". In-flight guard prevents double createOrder;
INSTRUMENT_DECLINED shows PayPal's documented retry path message. No infinite spinner.

## Tests (9 new; 22 total in the PayPal file)
Server capture: success finalizes with the REAL capture id (Payment 33.42, order marked),
amount mismatch → 409 without finalizing, INSTRUMENT_DECLINED → 402 retry, PENDING → polite
402, network → elegant 502, bad/missing id rejected, token never in responses. Template guards:
single gold funding source pinned, disable-funding list, **no `actions.order.capture`**, no
`window.open`, render-once guard, one container, loading/timeout strings present. Full suite
green.

## QA (local, PayPal blocked → fallback paths)
SDK script ×1, container ×1, elegant fallback when the SDK is absent, loading/error state
visuals, our pages contain zero `height="auto"` SVGs, mobile 390 clean. Screenshots in
`docs/qa/paypal_sandbox_ux_popup_capture/`. **The real gold button + single-window popup +
capture-success screenshots require the live sandbox** (owner credentials) — first item of the
post-deploy smoke; the configuration is test-asserted meanwhile.

## Deploy notes
No migration. `git pull` → `compilemessages -l it -l fr` → `collectstatic` → restart. Sandbox
smoke: PayPal tab → ONE gold button → one PayPal window with Glitchy totals/address → approve
→ "Confirming your payment…" → redirect to order-complete within seconds. Also save the Stripe
sandbox keys in admin to silence the console 503 on the card tab.
