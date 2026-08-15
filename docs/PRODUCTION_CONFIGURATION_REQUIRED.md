# Production configuration required — email & notifications (F5)

`SUPPORT_EMAIL`, `DEFAULT_FROM_EMAIL` and `ADMIN_NOTIFY_EMAIL` fall back to
`*.example.com` **placeholders** when the server environment does not set them
(`greatkart/settings.py`). While they are placeholders:

- the store shows **no** support email to customers (legal pages, FAQ and the
  order-complete page fall back to the `/contact/` form);
- the AI assistant is told to **route shoppers to `/contact/`** instead of quoting
  an address (it never invents one);
- `python manage.py check` raises non-blocking warnings
  `glitchy.support.W001` / `W002`.

None of this replaces real configuration — it only prevents a dead address from
leaking. Set the variables below in the server environment (the systemd unit's
`EnvironmentFile`, e.g. `/etc/glitchy/env`) and restart the service. **Do not commit
these values to the repository or the `.env` file in git.**

## Required variables

| Variable | Purpose | Placeholder if unset |
| --- | --- | --- |
| `SUPPORT_EMAIL` | Customer-facing support address (legal pages, FAQ, order-complete, assistant knowledge) | `support@example.com` |
| `ADMIN_NOTIFY_EMAIL` | Recipient of contact-form / internal alert notifications | *(empty → falls back to `SUPPORT_EMAIL`)* |
| `DEFAULT_FROM_EMAIL` | `From:` on outbound transactional mail | `no-reply@example.com` |
| `EMAIL_HOST_USER` | SMTP username; also the fallback source for the three above | *(empty)* |

## SMTP (only if email is sent directly, not via n8n)

| Variable | Default |
| --- | --- |
| `EMAIL_HOST` | `smtp.gmail.com` |
| `EMAIL_HOST_USER` | *(empty)* |
| `EMAIL_HOST_PASSWORD` | *(empty — secret)* |

## n8n / outbox (already used by the notifications app)

| Variable | Purpose |
| --- | --- |
| `N8N_WEBHOOK_BASE_URL` | Base URL for the n8n outbox webhook (primary notification channel) |
| `N8N_HEADER_AUTH_NAME` | Auth header name (default `X-N8N-AUTH`) |
| `N8N_HEADER_AUTH_SECRET` | Auth header value (secret) |
| `N8N_SHARED_SECRET` | Shared secret for inbound n8n callbacks (secret) |

## Verify after configuring

```bash
python manage.py check            # glitchy.support.W001/W002 must be gone
```

Then, in the assistant, ask a payment/refund question: the reply must offer the
`/contact/` escalation and, if `SUPPORT_EMAIL` is now real, may show that address —
never `support@example.com`.
