# Stripe — Staging Runbook (TEST mode)

Use **test** keys in staging. Never print keys/secrets.

## 1. Webhook endpoint
Stripe Dashboard (test mode) → Developers → Webhooks → **Add endpoint**:
- URL: `https://STAGING_DOMAIN/orders/stripe/webhook/`
- Events:
  - `payment_intent.succeeded`
  - `payment_intent.payment_failed`
  - `checkout.session.completed`
  - `charge.refunded`
- Copy the endpoint's **Signing secret** → `.env` `STRIPE_WEBHOOK_SECRET`
  (must match exactly). Restart the app.

## 2. Keys
`.env`: `STRIPE_PUBLIC_KEY=pk_test_...`, `STRIPE_SECRET_KEY=sk_test_...`,
`STRIPE_CURRENCY=eur`. **Do not use live keys in staging.**

## 3. Local forwarding (optional dev)
```bash
stripe listen --forward-to 127.0.0.1:8001/orders/stripe/webhook/
stripe trigger payment_intent.succeeded
```
> `stripe trigger` events carry no order metadata, so they won't finalize a real
> order — they only prove the signature path returns 200.

## 4. End-to-end test (real finalization)
1. Place a guest test order in the UI → note the order number.
2. Pay with test card `4242 4242 4242 4242`, any future expiry / CVC.
3. Verify in Admin → *Orders*: `is_ordered=True`, Payment created, costs +
   net margin populated, `printify_status=push_disabled`.
4. Verify Admin → *Outbound events*: `order.paid` → **sent (200)** to n8n.

## 5. Verify behaviours
- **Invalid signature → 400** (the webhook rejects unsigned/forged payloads).
- **Idempotency**: re-deliver the same event (Dashboard → "Resend") → no second
  OrderProduct; order stays finalized once.
- **Refund**: issue a partial/full refund in Stripe (or send `charge.refunded`) →
  Admin → Order `refunded_amount` updates; margin-after-refund recomputes.
- **payment_failed → 200**, order NOT finalized.

The signing secret is read from `.env` and is **never** logged.
