# PayPal Completed Payment Reconciliation & Frontend Timeout Fix (2026)

**Branch:** `fix/glitchy-paypal-completed-timeout-reconciliation` (from
`release/staging-printify-fashion-store @ 544ae47`). **No migration.** Sandbox only, tests
mocked, no double payments possible. Webhook still excluded.

## 1. Root cause — "completed in DB, timeout in the browser"
The capture endpoint did too much INSIDE the request: PayPal OAuth (1 roundtrip) + capture
(1 roundtrip) + `finalize_order_payment`, which synchronously ran **`push_order_to_printify`
(external API) and the n8n/SMTP notifications** — on a slow SMTP that is the reported
~1 minute. The frontend aborted at 45s and showed "do NOT pay again" while the backend went on
to complete the payment. Fixes, in layers:
- **Slow external side-effects moved to a background thread** (`_post_finalize_side_effects`:
  Printify push + notifications, each already fail-guarded). The DB core (OrderProduct, stock,
  cart clear, coupon) stays synchronous and fast. Same benefit for the Stripe webhook path.
- **PayPal OAuth token cache** (module-level, expiry-aware) — halves the latency of every
  create/capture.
- **Reconciliation**: even if a timeout ever happens again, the frontend now checks the truth
  before scaring anyone (see §3).

## 2. Deterministic capture contract
`POST /orders/paypal/capture/` now always answers
`{ok, status, order_id, payment_id, redirect_url}`:
- `completed` — captured, verified (amount+currency from the capture response), finalized;
- `already_completed` — **idempotency first**: a paid order answers success immediately with
  ZERO PayPal calls (test-asserted). `ORDER_ALREADY_CAPTURED` from PayPal reconciles from the
  DB the same way;
- `pending` (ok:true) — polite hold message;
- `{ok:false, status:"error", code, message}` — INSTRUMENT_DECLINED carries `retry:true`.
No second capture is possible on any path.

## 3. Post-timeout reconciliation
New `POST /orders/paypal/status/` — DB-only, idempotent, never captures, owner-scoped
(user or guest session): `completed` + redirect_url / `processing` / `unknown`. The JS now
funnels **every** failure path (timeout, network error, unexpected response) through
`ppReconcileThenError()`: "Checking your payment status…" → completed → **"We found your
completed PayPal payment. Redirecting…"** → thank-you page. The "do not pay again" message
survives only for genuinely unknown states. QA-verified end-to-end with a simulated late
capture (status → completed → real Order-complete page).

## 4. Stripe isolation
`stripe/create-intent` fired on page load even for PayPal users (Card tab active by default) —
the console 503 during PayPal payments. Now the payments view passes `stripe_ready`
(resolver-based) and the JS **never calls the intent endpoint when Stripe isn't configured**
(QA: 0 intent requests on load) — the Card panel shows "Card payments are not configured yet.
Choose PayPal or contact us." instead. PayPal is fully independent of Stripe's state.

## 5. Blank window & PayPal-hosted console noise
The previous phase's `application_context` + single-funding fix removes the persistent blank
window; what can remain is the SDK's **momentary bridge window** while `createOrder` resolves —
now shorter thanks to the token cache (one PayPal roundtrip). Not fully removable: it is SDK
behaviour. CSP `unsafe-eval` warnings and the `<svg> height="auto"` React error originate from
`paypalobjects.com/checkoutweb` (PayPal-hosted): no Django CSP exists, no Glitchy SVG uses
`height="auto"` (QA-asserted) — documented, not patchable on our side, no `unsafe-eval` added.

## 6. Tests (7 new; 36 in the PayPal file) + QA
Idempotent capture success (zero PayPal calls on paid orders), status endpoint
completed/processing/unknown + owner scoping, ALREADY_CAPTURED reconciliation, contract keys on
every branch, Stripe isolation + reconciliation wiring template guards. Full suite green.
QA (sandbox, SDK blocked): 0 intent calls with Stripe unconfigured + elegant card message,
status→completed→real thank-you page, idempotent capture via browser, 4 screenshots.

## 7. Deploy notes
No migration. `git pull` → `compilemessages -l it -l fr` → `collectstatic` → restart. Sandbox
smoke: approve in PayPal → "Confirming your payment…" → thank-you **in a few seconds**; if
anything is slow, the reconciliation still lands the customer on the thank-you page. The
console 503 disappears (no Stripe call until configured).
