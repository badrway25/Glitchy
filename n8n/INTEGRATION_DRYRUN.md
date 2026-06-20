# Integration Go-Live Dry Run — Results

Branch: `integration/n8n-stripe-printify-dry-run`. Local only, no deploy, no push.
No real Printify orders created (`PRINTIFY_PUSH_ENABLED=False`). No secrets printed.

## Environment
- Django dev server: `http://127.0.0.1:8799` (free port).
- n8n: real instance `n8n 1.108.0` on `http://localhost:5678` (was installed locally).
- Stripe CLI 1.31.0 available; webhook tested with **real `whsec_` signatures**.

## n8n
- 10 Glitchy workflows **imported into the real n8n** (`n8n import:workflow`).
  Fixed a blocker: workflows were missing the `active` field (NOT NULL in n8n 1.108).
- 9 webhook workflows **activated**; `/webhook/<path>` live.
- **Django → real n8n: 12/13 events delivered** (HTTP 200). `order.tracking_available`
  returned 404 (that path's webhook node not separately registered) and Django
  correctly marked it `retrying`.
- **Limitation (documented):** n8n's in-workflow HMAC *enforcement* via a Code node
  is unreliable on n8n 1.108 because the Code node cannot reproduce Django's exact
  raw body bytes. The verify node is therefore **best-effort/observability**
  (`_signature_valid` flag) and does not block delivery. **Enforce signatures in
  production with n8n native Header Auth or a network control.** The Django side
  signs every call correctly (proven via a controlled receiver: `sig_valid=true`).
- Email-send nodes need Gmail/SMTP credentials (not provisioned in the dry run);
  nodes set `onError=continueRegularOutput` so missing creds don't break delivery.

## Django → n8n (HMAC, outbound)
All 13 event types dispatched; OutboundEvent status tracked; HMAC `X-Signature`
sent on every call; retry/failure handling verified (`retrying` on 404). No
secrets in logs.

## n8n → Django (inbound, HMAC-protected)
| Check | Result |
|---|---|
| `/api/n8n/incoming-email/` valid signature | **200** |
| wrong signature | **401** |
| duplicate `message_id` dedup | count **1** |
| order auto-link from subject | linked ✅ |
| email without known customer | unassociated ✅ |
| `/api/n8n/support-message/` alias | **200** |
| `/api/n8n/email-status/` updates OutboundEvent | status→`sent` ✅ |
| `/api/n8n/order-event/` tracking update | tracking/carrier set ✅ |

## Stripe webhook (real `whsec_` signatures)
| Event | Result |
|---|---|
| invalid signature | **400** |
| `payment_intent.succeeded` | order **finalized** (Payment + OrderProduct) |
| duplicate delivery | **idempotent** (still 1 OrderProduct) |
| `charge.refunded` | `refunded_amount` updated (cumulative, idempotent) |
| `payment_intent.payment_failed` | **200**, no finalize |
| `order.paid` side-effect | OutboundEvent **sent → real n8n (200)** |

## Complete order test (guest, real Printify product)
Guest UI checkout of "Sweet Dreams shirt" (Dark Heather / M) → order `2026062097`
(€21.22) → finalized by a real signed Stripe webhook:
- production cost **€15.02**, shipping **€4.90**, payment fee **€0.57**,
  **net margin €0.41**.
- `order.paid` → real n8n (sent/200).
- `printify_status = push_disabled` → **no real Printify order created**.

## Returns (14-day) + margin after refund
Fresh order eligible (14 days left); oldest order not eligible. Request → approve →
refund flow; `order.refunded_amount` updated; **net margin after refund computed**;
`return.requested / return.approved / refund.completed` all **sent → real n8n (200)**.

## Email templates
21 renders (7 events × EN/IT/FR): **0 integrity issues** (no unrendered tags,
translated subjects, text fallback present).

## Tests / checks
`manage.py check` clean · `makemigrations --check` no changes · **48 tests pass** ·
`compilemessages` OK.

## QA visual
Home EN/IT/FR (desktop+mobile 390px), product detail (More), cart, guest checkout,
payment, order-complete, account dashboard EN/IT, addresses, returns, admin
Orders KPI / Returns / Notifications-n8n / Printify SyncLog. **0 HTTP 500, 0 console
errors, 0 mobile overflow** across 19 smoke surfaces.

## What's left for production
1. Rotate secrets (Phase-2 list) and set `DJANGO_DEBUG=False` + HTTPS hardening.
2. n8n: connect Gmail/SMTP + IMAP credentials, register `order-tracking-available`
   webhook, add native Header Auth for signature enforcement, activate all flows.
3. Stripe: register the public webhook endpoint + signing secret in the Dashboard.
4. Set `PRINTIFY_PUSH_ENABLED=True` only when ready to send real Printify orders.
