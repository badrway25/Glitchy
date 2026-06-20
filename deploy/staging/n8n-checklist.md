# n8n — Staging Runbook

See also `n8n/EMAIL_SETUP.md` and `n8n/README.md`. **Never print secrets.**

## 1. Import the 11 workflows
n8n → Settings → **Import from File**, one per file in `n8n/workflows/`:
order-confirmation, shipping-update, **order-tracking**, return-request,
return-decision, abandoned-cart, printify-error-alert, support-inbox,
support-autoreply, newsletter-welcome, internal-notifications.

## 2. Credentials (create in n8n UI — values never in JSON)
- **`Glitchy n8n Header Auth`** (type *Header Auth*): header `X-N8N-AUTH`,
  value = Django `N8N_HEADER_AUTH_SECRET`. Attach to **every webhook node**.
- **`Glitchy Gmail`** (Gmail OAuth2 / SMTP): the sending mailbox. Attach to all
  *Send Email* nodes.
- **`Glitchy Support Mailbox`** (IMAP / Gmail Trigger): the support inbox. Attach
  to the `Support Inbox Ingest` trigger.

## 3. Activate
- **Activate now (10):** all webhook workflows (order-confirmation, shipping-update,
  order-tracking, return-request, return-decision, abandoned-cart,
  printify-error-alert, support-autoreply, newsletter-welcome, internal-notifications).
- **Leave INACTIVE (1):** `Support Inbox Ingest` until the IMAP/Gmail credential is set.

## 4. n8n environment
`N8N_SHARED_SECRET` (= Django observability secret), `DJANGO_BASE_URL`
(`https://STAGING_DOMAIN`), `ADMIN_NOTIFY_EMAIL`, `SUPPORT_EMAIL`.

## 5. Tests
**Django → n8n** (from the Django host):
```bash
./env/bin/python manage.py shell -c "from notifications.dispatcher import dispatch_event; \
from notifications import events as ev; \
print(dispatch_event(ev.ORDER_PAID, {'order_number':'TST'}, recipient_email='you@example.com').status)"
# expect: sent   (OutboundEvent http=200; without a valid X-N8N-AUTH n8n returns 403)
```
- Verify `order.tracking_available` is **sent** (not retrying) — path is
  `order-tracking_available` (underscore kept). Admin → *Outbound events*.

**n8n → Django** (already enforced by Django): valid signature → 200, wrong → 401,
duplicate `message_id` → dedup. Send a test email to the support mailbox → the
`Support Inbox Ingest` workflow posts to `/api/n8n/incoming-email/` → check
Admin → *Support messages*.

**Email send / receive:** trigger an order → confirm the recipient inbox; reply to
support → confirm a new SupportMessage.

## 6. Reading errors safely
n8n → *Executions* shows failed runs. Do **not** paste credential values into
tickets. Django side: Admin → *Outbound events* (status, response code, truncated
`last_error` — no secrets). Use `manage.py n8n_retry` to re-send failed events.
