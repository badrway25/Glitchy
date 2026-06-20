# Glitchy × n8n — Automation & Email Integration

This folder contains the n8n side of the Glitchy e-commerce automation layer. The
Django app is the **source of truth**; n8n is the **primary channel for sending
email** and for ingesting inbound support mail. Every message in both directions
is authenticated with an **HMAC-SHA256 shared secret**.

```
Django  ──(POST event + X-Signature)──▶  n8n webhook  ──▶  Gmail/SMTP send
n8n  ──(POST + X-Signature)──▶  Django  /api/n8n/...  (incoming email, status, order updates)
```

All workflow files live in [`workflows/`](./workflows). Import each one into n8n
(**Settings → Import from File**), connect credentials, set the environment
variables below, then **activate**.

---

## 1. How HMAC signing works (both directions)

A single shared secret, **`N8N_SHARED_SECRET`**, must be identical on the Django
side and inside n8n. It is used to sign and verify every request.

### Outbound: Django → n8n
Django builds a JSON body and signs the **raw request bytes**:

```
X-Signature = HMAC-SHA256(secret = N8N_SHARED_SECRET, message = raw request body)   // hex
```

Django sends these headers:

| Header           | Value                                        |
|------------------|----------------------------------------------|
| `Content-Type`   | `application/json`                           |
| `X-Event-Type`   | the event name, e.g. `order.paid`            |
| `X-Signature`    | hex HMAC-SHA256 of the raw body              |

Request body shape:

```json
{ "event": "order.paid", "language": "en|it|fr", "recipient": "customer@example.com", "data": { ... } }
```

> **Important — compact JSON.** Django serializes the body with
> `json.dumps(..., separators=(",", ":"))`, i.e. **no spaces** between keys/values.
> The signature is computed over those exact bytes. In n8n you must therefore
> verify against the **raw body**, not a re-serialized object (re-serializing in JS
> can reorder keys or add spaces and break the signature). Each workflow's
> **Verify HMAC** Code node reads the raw body captured by the Webhook node
> (`rawBody: true`) and falls back to `JSON.stringify` only if a raw body is not
> available. See note in §6.

The verify code used in every inbound workflow:

```js
const crypto = require('crypto');
const secret = $env.N8N_SHARED_SECRET;
const item = $input.first();
const headers = item.json.headers || {};
const sig = headers['x-signature'] || headers['X-Signature'];
let rawBody = item.binary && item.binary.data
  ? Buffer.from(item.binary.data.data, 'base64').toString('utf8')
  : (typeof item.json.body === 'string' ? item.json.body : JSON.stringify(item.json.body));
const expected = crypto.createHmac('sha256', secret).update(rawBody, 'utf8').digest('hex');
if (!sig || expected !== sig) { throw new Error('invalid signature'); }
```

On mismatch the node throws `invalid signature`, the workflow stops, and n8n
returns a non-2xx (effectively a 401-style rejection). No email is sent.

### Inbound: n8n → Django
The three Django endpoints under `/api/n8n/` are HMAC-protected by the same secret.
When n8n POSTs to Django it must compute the signature over the **exact body string
it sends** and pass it as `X-Signature`:

```js
const bodyString = JSON.stringify(payload);              // this exact string is the HTTP body
const signature = crypto.createHmac('sha256', secret).update(bodyString, 'utf8').digest('hex');
// then send header X-Signature: signature  AND  body: bodyString  (raw, application/json)
```

Django verifies with `hmac.compare_digest` against `request.body`; a mismatch
returns **HTTP 401 `{"ok": false, "error": "invalid_signature"}`**. This is why
the `support-inbox` workflow sends a **raw** body (the pre-serialized
`bodyString`) rather than letting the HTTP node re-serialize a JSON object.

### Setting the shared secret
1. Generate one strong random secret (e.g. `openssl rand -hex 32`).
2. Put it in Django's `.env` as `N8N_SHARED_SECRET=...` and set `N8N_ENABLED=True`.
3. Put the **same** value in n8n as the environment variable `N8N_SHARED_SECRET`
   (see §4). Never paste it into a node body or commit it.

---

## 2. Workflows

Each workflow is a separate importable file. Customer-facing emails are
**multilingual (EN / IT / FR)**, switching on `data`-level `language` (the body's
top-level `language` field), defaulting to `en`.

| # | File | Trigger | Webhook path(s) / source | Django endpoint(s) called | What it does |
|---|------|---------|--------------------------|---------------------------|--------------|
| 1 | `order-confirmation.json` | Webhook | `order-paid`, `order-created` | – (sends email only) | Verifies HMAC, builds a multilingual HTML order-confirmation email (items table, totals, address, ETA), sends via Gmail, responds 200. |
| 2 | `shipping-update.json` | Webhook | `order-shipped`, `order-tracking-available` | – | Verifies HMAC, builds a shipping/tracking email with the `tracking_url` button and `tracking_number`, responds 200. |
| 3 | `return-request.json` | Webhook | `return-requested` | – | Verifies HMAC, sends a customer acknowledgement **and** a second internal-ops email to `ADMIN_NOTIFY_EMAIL`, responds 200. |
| 4 | `return-decision.json` | Webhook | `return-approved` (+ `return-rejected`, `refund-completed`) | – | Verifies HMAC, builds the email by branching on `event` (approved / rejected / refund), responds 200. |
| 5 | `abandoned-cart.json` | Webhook | `cart-abandoned` | – | Verifies HMAC, **IF** marketing consent → sends a recovery email with the `cart_url`; otherwise responds 200 `{sent:false, reason:"no_consent"}`. |
| 6 | `printify-error-alert.json` | Webhook | `printify-error` | – | Verifies HMAC, sends an internal alert email (order + error detail) to ops, responds 200. |
| 7 | `support-inbox.json` | Gmail Trigger | support mailbox (poll) | **`POST /api/n8n/incoming-email/`** | Reads new support email, normalises sender/subject/body/message_id/thread_id, computes `X-Signature`, POSTs to Django with `auto_reply:true`. |
| 8 | `support-autoreply.json` | Webhook | `support-autoreply` | – | Verifies HMAC, sends a multilingual "we received your request…" auto-reply, responds 200. |
| 9 | `newsletter-welcome.json` | Webhook | `newsletter-subscribed` | – | Verifies HMAC, optional add-to-list placeholder node, sends a multilingual welcome email, responds 200. |
| 10 | `internal-notifications.json` | Webhook | `internal-alert` (+ `margin-negative`) | – | Verifies HMAC, sends an internal notification email to ops (special-cases negative margin), responds 200. |

> **Other inbound endpoints.** Django also exposes
> `POST /api/n8n/email-status/` (delivery status; `event_id` optional/future) and
> `POST /api/n8n/order-event/` (push tracking/printify status back). They are not
> on the critical path of the 10 workflows above; wire them in as needed:
> - **email-status** — add an HTTP Request node after each `Send Email` node that
>   POSTs `{ event_id, status:"sent" }` (sign the body like §1 inbound). It is a
>   safe no-op when Django did not send an `event_id`.
> - **order-event** — call from `support-inbox` (or a dedicated workflow) when you
>   parse a carrier/tracking update out of the Printify mailbox:
>   `{ order_number, tracking_number?, tracking_url?, carrier?, printify_status? }`.

---

## 3. Django event → webhook path → workflow file

n8n webhook paths are the Django event name with **dots replaced by hyphens**, and
Django POSTs to `${N8N_WEBHOOK_BASE_URL}/<path>`.

| Django event              | Webhook path                 | Workflow file                  |
|---------------------------|------------------------------|--------------------------------|
| `order.created`           | `order-created`              | `order-confirmation.json`      |
| `order.paid`              | `order-paid`                 | `order-confirmation.json`      |
| `order.in_production`     | `order-in_production`*       | (reuse `order-confirmation` style or add a workflow) |
| `order.shipped`           | `order-shipped`              | `shipping-update.json`         |
| `order.tracking_available`| `order-tracking-available`   | `shipping-update.json`         |
| `return.requested`        | `return-requested`           | `return-request.json`          |
| `return.approved`         | `return-approved`            | `return-decision.json`         |
| `return.rejected`         | `return-rejected`            | `return-decision.json`         |
| `refund.completed`        | `refund-completed`           | `return-decision.json`         |
| `cart.abandoned`          | `cart-abandoned`             | `abandoned-cart.json`          |
| `newsletter.subscribed`   | `newsletter-subscribed`      | `newsletter-welcome.json`      |
| `support.autoreply`       | `support-autoreply`          | `support-autoreply.json`       |
| `printify.error`          | `printify-error`             | `printify-error-alert.json`    |
| `margin.negative`         | `margin-negative`            | `internal-notifications.json`  |
| `internal.alert`          | `internal-alert`             | `internal-notifications.json`  |
| _(inbound mail)_          | n/a (Gmail Trigger)          | `support-inbox.json`           |

\* `order.in_production` is not bundled as its own file; it follows the same
contract. Either add a webhook path `order-in_production` to
`order-confirmation.json` or duplicate that workflow and change the copy. Note the
underscore: Django only replaces **dots**, so `in_production` keeps its underscore.

---

## 4. Environment variables & credentials to configure

### n8n environment variables
Set these where n8n reads env (Docker `environment:`, `.env`, or host env). They
are referenced in nodes as `{{$env.NAME}}` / `$env.NAME`.

| Variable               | Purpose                                                                 |
|------------------------|-------------------------------------------------------------------------|
| `N8N_SHARED_SECRET`    | **Must equal Django's `N8N_SHARED_SECRET`.** Signs/verifies all traffic. |
| `DJANGO_BASE_URL`      | Base URL of the Django app, e.g. `http://127.0.0.1:8000` (no trailing slash). Used by `support-inbox` to call `/api/n8n/incoming-email/`. |
| `ADMIN_NOTIFY_EMAIL`   | Ops inbox for internal alerts (return ops, printify errors, margin, internal). |
| `SUPPORT_EMAIL`        | The public support address (used as `to_email` fallback when ingesting mail). |
| `SITE_BASE_URL`        | Storefront URL used for the "Start shopping" button in the welcome email. |

### `N8N_WEBHOOK_BASE_URL` alignment (Django side)
On the Django side, `N8N_WEBHOOK_BASE_URL` must point at this n8n instance's
webhook base, e.g. `http://localhost:5678/webhook`. The full URL Django calls is
`${N8N_WEBHOOK_BASE_URL}/<path>` (e.g. `.../webhook/order-paid`). In n8n, **test**
executions use the `/webhook-test/...` URL and **active** workflows use
`/webhook/...` — so the path in each Webhook node (e.g. `order-paid`) must match
the last segment Django sends. Activate the workflows so the production
`/webhook/...` URL is live.

### Credentials to create in n8n (Credentials → New)
| Credential | Used by | Notes |
|------------|---------|-------|
| **Gmail OAuth2** (or SMTP) — "Glitchy Gmail" | workflows 1–6, 9, 10 | The sending account for all customer + ops email. Each Gmail node currently references `gmailOAuth2` id `REPLACE_WITH_GMAIL_CREDENTIAL_ID`; re-select your real credential after import. To use SMTP instead, swap the `n8n-nodes-base.gmail` nodes for `n8n-nodes-base.emailSend` and attach an SMTP credential. |
| **Gmail OAuth2 / IMAP** — "Glitchy Support Mailbox" | `support-inbox.json` (trigger) and `support-autoreply.json` (send) | The mailbox that receives customer support email. `support-inbox` uses a **Gmail Trigger**; to use IMAP instead, replace it with an **Email Trigger (IMAP)** node and attach IMAP credentials. id placeholder: `REPLACE_WITH_SUPPORT_MAILBOX_CREDENTIAL_ID`. |

> The `id` values in the JSON (`REPLACE_WITH_...`) are placeholders. After import,
> open each Gmail / trigger node and pick your real credential from the dropdown —
> n8n re-links by selection.

---

## 5. Import instructions (step by step)

1. Start n8n and sign in.
2. For **each** file in `workflows/`:
   - Top-right menu (**⋮**) → **Import from File** *(older builds: Workflows →
     Import from File)*.
   - Select the `.json` file (e.g. `order-confirmation.json`).
   - The workflow opens on the canvas.
3. Open every **Gmail** / **Gmail Trigger** node and select your real credential
   (the placeholder credential ids will show as "not found" until you pick one).
4. Confirm the env vars in §4 are set and visible (`$env.N8N_SHARED_SECRET` etc.).
5. For webhook workflows: note the **Production URL** shown on the Webhook node and
   confirm its last path segment matches what Django sends (it should, out of the
   box).
6. **Save**, then toggle **Active** (top-right). Only active workflows expose the
   production `/webhook/...` URL.
7. Repeat for all 10 files. For `support-inbox.json`, also confirm the Gmail
   Trigger poll interval and that the mailbox credential is the support inbox.

### Quick test
Send a signed test request from a shell (replace secret/host):

```bash
SECRET='your-shared-secret'
BODY='{"event":"order.paid","language":"en","recipient":"you@example.com","data":{"order_number":"GLT-1001","first_name":"Sam","currency":"EUR","items":[{"name":"Tee","variant":"M","qty":1,"unit_price":25,"line_total":25}],"items_subtotal":25,"shipping_cost":5,"tax":0.5,"order_total":30.5,"shipping":{"country":"IT","min_days":3,"max_days":6},"address":{"line1":"Via Roma 1","city":"Milan","postal_code":"20100","country":"IT"}}}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -r | cut -d' ' -f1)
curl -sS -X POST http://localhost:5678/webhook/order-paid \
  -H 'Content-Type: application/json' -H "X-Event-Type: order.paid" -H "X-Signature: $SIG" \
  --data "$BODY"
```

A valid signature returns `{"ok":true}` and sends the email; a wrong signature
fails the **Verify HMAC** node and no email is sent.

---

## 6. n8n version note on raw-body access

How a Webhook node exposes the raw body varies by n8n version:

- The webhook nodes here set **`rawBody: true`** and use **Response Mode: Using
  'Respond to Webhook' node**. With `rawBody`, n8n exposes the original bytes
  (commonly under `item.binary.data`), which the Verify HMAC code prefers.
- On some versions the parsed JSON appears under `item.json.body` and the original
  string is not retained. The verify code falls back to `JSON.stringify(item.json.body)`,
  **but** because Django uses compact separators this fallback can mismatch if key
  order differs. For reliable verification, keep `rawBody: true` and verify against
  the raw bytes.
- If your build still cannot surface the raw body, an alternative is to verify in a
  small reverse proxy in front of n8n, or to relax to a constant-time compare after
  canonicalising both sides identically. Prefer raw-body verification.

---

## 7. Security notes

- **Never log secrets.** The shared secret only ever appears as `$env.N8N_SHARED_SECRET`.
  Do not echo it in Code nodes, do not put it in node parameters, do not commit it.
- **Always verify signatures.** Every inbound webhook runs **Verify HMAC** before
  doing anything; on mismatch it throws and stops. Django likewise rejects unsigned
  / wrongly-signed inbound calls with 401.
- **Restrict webhook exposure.** Put n8n behind HTTPS and, ideally, restrict the
  `/webhook/...` paths to the Django server's IP (firewall / reverse-proxy allowlist).
  The HMAC is the auth layer, but network restriction is defence in depth.
- **Outbound to Django over TLS.** In production set `DJANGO_BASE_URL` to `https://`.
- **Least privilege on mailboxes.** The Gmail/IMAP credentials should be a
  dedicated sending/support account, not a personal admin account.
- **Don't trust inbound mail content.** `support-inbox` only forwards normalised
  fields to Django; Django dedupes by `message_id` and links orders/accounts safely.

---

## 8. What's left to configure manually

- [ ] Generate `N8N_SHARED_SECRET` and set it **identically** in Django `.env` and
      n8n env. Set Django `N8N_ENABLED=True`.
- [ ] Set Django `N8N_WEBHOOK_BASE_URL` to this n8n's webhook base
      (e.g. `http://localhost:5678/webhook`).
- [ ] In n8n, set env vars: `DJANGO_BASE_URL`, `ADMIN_NOTIFY_EMAIL`,
      `SUPPORT_EMAIL`, `SITE_BASE_URL` (and `N8N_SHARED_SECRET`).
- [ ] Create the **Gmail (sending)** credential and re-select it on every Gmail
      send node (or swap to SMTP `emailSend` + SMTP credential).
- [ ] Create the **support mailbox** credential (Gmail Trigger or IMAP Email
      Trigger) and attach it in `support-inbox.json` (trigger) and
      `support-autoreply.json` (send).
- [ ] In `abandoned-cart.json`, confirm how marketing consent is signalled. The IF
      node checks `data.marketing_consent === true` (or `data.consent`). If Django
      sends consent under a different key, update the **Verify HMAC** node's
      `_consent` line.
- [ ] (Optional) In `newsletter-welcome.json`, replace the **Add to Mailing List
      (placeholder)** NoOp node with a real Mailchimp / Brevo / SendGrid subscriber
      node using `{{$json.data.email}}`.
- [ ] (Optional) Add `email-status` and `order-event` HTTP Request callbacks where
      you need delivery tracking or to push tracking/printify status back to Django.
- [ ] Decide whether `order.in_production` needs its own copy/workflow.
- [ ] **Save and Activate** all 10 workflows so production webhook URLs go live.
```
