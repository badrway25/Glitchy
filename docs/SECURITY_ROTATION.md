# Secret Rotation & Pre-Deploy Security Checklist

All secrets live in the **untracked** `.env`. `.env.example` holds placeholders
only. Never commit `.env`, never paste secret values into tickets/logs/chat.

## Secrets inventory

| Secret (env var) | Source | Can be generated locally? | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | self | **Yes** | `python -c "import secrets;print(secrets.token_urlsafe(64))"` |
| `N8N_SHARED_SECRET` | self | **Yes** | HMAC observability signature (Django↔n8n) |
| `N8N_HEADER_AUTH_SECRET` | self | **Yes** | Primary n8n Header Auth value (must match the n8n credential) |
| `PRINTIFY_API_TOKEN` | Printify dashboard | No | Printify → Account → Connections |
| `STRIPE_SECRET_KEY` | Stripe dashboard | No | Developers → API keys |
| `STRIPE_PUBLIC_KEY` | Stripe dashboard | No | Publishable (not secret, but env-managed) |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard | No | Developers → Webhooks → signing secret |
| `EMAIL_HOST_PASSWORD` | Gmail/SMTP provider | No | Gmail App Password (not the account password) |
| `PAYPAL_CLIENT_ID` | PayPal dashboard | No | Public client id (env-managed for config) |

> The values originally hard-coded in the pre-Phase-1 source were externalized.
> Treat them as **potentially exposed** and rotate them before go-live.

## Rotation procedure (per secret)
1. Generate/obtain the **new** value from the provider (or locally for the three
   self-managed ones — never print it to a shared console).
2. Update the matching key in `.env` (local) / your secret manager (server).
3. For provider secrets, **revoke the old value** in the provider dashboard.
4. For `N8N_HEADER_AUTH_SECRET`: also update the **"Glitchy n8n Header Auth"**
   credential in n8n to the same new value.
5. For `STRIPE_WEBHOOK_SECRET`: copy it from the Stripe webhook endpoint you
   register; it must match exactly.
6. Restart Django (and n8n) to load the new values. Re-run the smoke tests.

### Locally-generatable secrets — one-liners (do not echo the value into chat)
```bash
# DJANGO_SECRET_KEY / N8N_SHARED_SECRET / N8N_HEADER_AUTH_SECRET
python -c "import secrets; open('/tmp/k','w').write(secrets.token_urlsafe(64))"
# then paste the file contents into .env, then shred /tmp/k
```

## OpenAI assistant key (`AI_API_KEY`) — treat as EXPOSED
The contextual AI assistant uses an OpenAI key in `AI_API_KEY`. During development
this key was shared over a chat channel, so it **must be considered exposed** even
though it is not in git, not in `.env.example`, and never logged by the code.

**Before staging/production you MUST rotate it:**
1. Go to https://platform.openai.com/api-keys → **revoke** the current key.
2. **Create a new** secret key (ideally project-scoped, with a usage limit).
3. Put the new value in `.env` only: `AI_API_KEY=sk-...` (never commit it).
4. Restart the app; verify the assistant answers a shipping question and declines
   an off-topic one.

Operational guardrails already enforced in code:
- Key read from env only; never hardcoded, never logged (only HTTP status is logged).
- `AI_RATE_LIMIT` (per session/hour), `AI_MAX_INPUT_CHARS`, `AI_MAX_TOKENS`,
  `AI_TIMEOUT_SECONDS` cap abuse and cost; off-topic questions are declined WITHOUT
  an API call.
- Set a **hard spending limit** in the OpenAI dashboard as a backstop.
- To disable the assistant entirely without code changes: `AI_ASSISTANT_ENABLED=False`.

## Pre-deploy checklist
- [ ] `.env` is NOT committed (`git ls-files | grep -x .env` → empty).
- [ ] `.env.example` contains placeholders only (no real values).
- [ ] All secrets above rotated; old provider values revoked.
- [ ] `DJANGO_DEBUG=False`.
- [ ] `DJANGO_SECRET_KEY` is a fresh long random value (no `django-insecure-`).
- [ ] `DJANGO_ALLOWED_HOSTS` set to the real domain(s).
- [ ] `CSRF_TRUSTED_ORIGINS` set to the `https://` domain(s).
- [ ] `SITE_BASE_URL` set to the production URL.
- [ ] `python manage.py check --deploy` → only acceptable warnings.
- [ ] HTTPS terminating proxy in front; `SECURE_PROXY_SSL_HEADER` matches it.
- [ ] `DATABASE_URL` points to managed Postgres (not SQLite).
- [ ] `collectstatic` run; static served by the web server/CDN.
- [ ] Stripe webhook endpoint registered + `STRIPE_WEBHOOK_SECRET` matches.
- [ ] n8n Header Auth credential created and attached to webhook nodes.
- [ ] `PRINTIFY_PUSH_ENABLED=True` only when ready to create real Printify orders.
- [ ] Logs do not contain secrets (we log status codes + truncated errors only).

## OpenAI key rotation gate (operational)

`scripts/rotate_secrets_check.sh` now **fails** (blocks staging/prod) while `AI_ASSISTANT_ENABLED=True`
unless `OPENAI_KEY_ROTATED=True`. The dev key was shared in chat and must be treated as exposed.

Procedure (owner only — the key is never committed, never printed):
1. Revoke the current key at https://platform.openai.com/api-keys
2. Create a new **project-scoped** key with a hard monthly spend limit
3. Put it only in `.env` / the secrets manager — never in git
4. Set `OPENAI_KEY_ROTATED=True` in the same environment file
5. Run `bash scripts/rotate_secrets_check.sh` (must show 0 failures)
6. Never commit `.env`

Until step 4–5 pass, **staging is blocked** by design.
