# n8n Email & Auth Setup Checklist

The workflow JSONs are **ready to receive credentials** — they reference named
credentials but contain **no secret values**. Complete these steps in the n8n UI.

## 1. Authentication (primary enforcement) — Header Auth
Every webhook workflow uses n8n **native Header Auth** (`authentication: headerAuth`).
1. n8n → **Credentials → New → "Header Auth"**.
2. Name it exactly **`Glitchy n8n Header Auth`**.
3. Header **Name** = `X-N8N-AUTH`; **Value** = the same string as Django's
   `N8N_HEADER_AUTH_SECRET`.
4. Open each Glitchy webhook workflow and confirm the webhook node's credential is
   set to this Header Auth credential (it auto-links by name on import).

Result: requests **without** the header (or with a wrong value) are rejected with
**403 by n8n core**, before the workflow runs — this is the production gate.
The `X-Signature` HMAC Django also sends is **observability/defense-in-depth**
(see README), not the primary gate.

## 2. Sending email — Gmail or SMTP
1. n8n → **Credentials → New → "Gmail OAuth2"** (or **SMTP**).
2. Name it **`Glitchy Gmail`** (matches the "Send Email" nodes' placeholder).
3. Authorize the sending mailbox; set the **From** address used by the brand.
4. Attach this credential to the **Send Email (Gmail)** node in these workflows:
   - order-confirmation, shipping-update, **order-tracking**, return-request,
     return-decision, refund (return-decision), abandoned-cart, newsletter-welcome,
     support-autoreply, printify-error-alert, internal-notifications.

## 3. Receiving support email — IMAP / Gmail trigger
1. n8n → **Credentials → New → "IMAP"** (or **Gmail Trigger** OAuth2).
2. Name it **`Glitchy Support Mailbox`** (matches `support-inbox`).
3. Point it at the support inbox (e.g. `support@yourbrand.com`).
4. Open **`Glitchy - Support Inbox Ingest`** → attach the credential to the trigger;
   confirm the HTTP Request node posts to `${DJANGO_BASE_URL}/api/n8n/incoming-email/`
   with the `X-N8N-AUTH` header (or HMAC) so Django accepts it.

## 4. Environment variables (n8n side)
Set where n8n reads env (Docker `environment:`, host env, or `.env`):
- `N8N_SHARED_SECRET` — same as Django (HMAC observability).
- `DJANGO_BASE_URL` — e.g. `https://shop.example.com`.
- `ADMIN_NOTIFY_EMAIL`, `SUPPORT_EMAIL` — used by internal/support workflows.

## 5. Activate
Activate all 11 Glitchy workflows. Each webhook path is then live at
`${N8N_WEBHOOK_BASE_URL}/<event-with-dots-as-hyphens>` (underscores kept), e.g.
`order-paid`, `order-tracking_available`, `return-requested`.

## 6. Test
- **Send**: from Django, dispatch an event (or place a test order) → the matching
  workflow runs and sends the email. Verify in the recipient inbox.
- **Receive**: send an email to the support mailbox → `Support Inbox Ingest`
  fires → Django stores a `SupportMessage` (admin → Support messages).
- **Rendering**: Django renders the same payload for the SMTP fallback — already
  verified for EN/IT/FR with no unresolved placeholders.

## SMTP fallback (Django) stays SECONDARY
`EMAIL_SMTP_FALLBACK=True` lets Django send transactional email **only** when an
n8n dispatch fails or n8n is disabled. n8n remains the primary channel.
