# Webhooks & Events — readiness reference

How the server-authoritative payment/fulfilment/email paths work and where they are tested
with mocks (no real keys, no real network). Activation steps live in
`INTEGRATIONS_ACTIVATION_RUNBOOK.md`.

## Stripe webhook  (`/orders/stripe/webhook/`)
- **Signature is mandatory**: `stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)`. Invalid signature → HTTP 400. No secret is ever logged.
- **Server-authoritative amount**: order totals come from `order.order_total`, never the client.
- **Idempotent**: `finalize_from_intent` no-ops if the order is already finalized; refunds SET the cumulative amount.
- **Events handled**:
  | Event | Action |
  |-------|--------|
  | `payment_intent.succeeded` / `checkout.session.completed` | finalize the order (by `metadata.order_number`) |
  | `payment_intent.payment_failed` | log for ops, do **not** finalize |
  | `charge.refunded` | `apply_stripe_refund` (cumulative SET) |
- **Tests** (`orders/test_integration_readiness.py`): bad signature → 400; succeeded → finalize called once; refunded → refund applied; failed → not finalized.
- **Activation**: register the public endpoint in the Stripe dashboard, copy its signing secret to `STRIPE_WEBHOOK_SECRET`, test in `sk_test` mode before switching to `sk_live`.

## PayPal  (`/orders/payments/`)
- **Fail-closed**: disabled unless `PAYPAL_ENABLED` AND client id AND secret. A forged `status="COMPLETED"` returns 503 and never finalizes. When enabled, the capture is verified server-side (amount + currency + COMPLETED).
- **Tests** (`orders/test_paypal_security.py`): forged POST → 503/402, order not finalized.

## Printify push  (`push_order_to_printify`)
- Gated by `PRINTIFY_PUSH_ENABLED` (default **False** → status `push_disabled`, no real order).
- **Idempotent**: returns the existing `printify_order_id` instead of creating a duplicate.
- **Tests** (`orders/test_integration_readiness.py`): disabled → no `create_order` call; already-pushed → no duplicate.
- **Activation** (only when authorised to send real orders): set token/shop, sync products, then `PRINTIFY_PUSH_ENABLED=True`. Rollback: set it back to False.

## Printify shipping  (`quote_for_cart`)
- Uses the Printify rate hook only when `SHIPPING_USE_PRINTIFY=True`; **degrades to the fallback rate table** on `None`, exception or timeout. Quote carries a `source` field (`printify` / `fallback` / `free`).
- **Tests** (`shipping/test_printify_readiness.py`): disabled → fallback; available → `source=printify`; raises/None → fallback (never errors).

## Email / n8n events
- `notify_order_event` / `notify_return_event` → `dispatch_event` → n8n (signed) → **SMTP fallback** if n8n is off/failed (after retries). Templates render EN/IT/FR.
- Events: `order.paid`, `order.in_production`, `order.shipped`, `order.tracking_available`, `return.requested/approved/rejected`, `refund.completed`, `support.*`, growth events.
- **Tests** (`notifications/test_email_readiness.py`): n8n off → SMTP delivers; n8n success → sent; n8n failure (retries exhausted) → SMTP recovery; single failure with retries left → RETRYING; event always persisted.
