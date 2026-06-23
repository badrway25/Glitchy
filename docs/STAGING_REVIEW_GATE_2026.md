# Staging Review Gate — Glitchy (release/staging-printify-fashion-store)

**Date:** 2026-06 · **Repo:** https://github.com/badrway25/Glitchy.git
**Branch:** `release/staging-printify-fashion-store` · **Deployed commit (remote = local):** `5a29f27`

This is a **staging review/provisioning gate**, not a production deploy. No host was provisioned,
no keys were rotated, no real orders/payments were made.

---

## 1. GitHub / branch strategy
- Remote `origin` = `https://github.com/badrway25/Glitchy.git` ✓
- **Only one remote branch**: `release/staging-printify-fashion-store` (HEAD `5a29f27`, in sync with local).
- **`main` does NOT exist** on the remote.
  - This is **not a blocker** for staging: `release/staging-printify-fashion-store` can serve as the
    default/staging branch.
  - For a PR-based workflow, a base branch (e.g. `main`) must be created first. **Not created** here
    (no authorization to add remote branches).

## 2. Pre-staging local gate — ALL GREEN
| Check | Result |
|---|---|
| `manage.py check` | 0 issues |
| `makemigrations --check --dry-run` | no changes |
| `manage.py test` | **356 passed** |
| `compilemessages -l it -l fr` | clean |
| `collectstatic --noinput` | ok |
| `scripts/staging_check.sh` | **0 failures** |
| `integration_status --staging` | 2 items not ready = the two rotation gates (expected) |

## 3. Staging host discovery — NO HOST AVAILABLE
Environment is a **local Windows dev machine** (MINGW64), not a deploy target:
- `gunicorn`: absent · `nginx`: absent · `systemctl`: absent
- DB engine currently `sqlite3` (a real staging needs managed Postgres)
- `DEBUG=True` locally (must be `False` on a real staging host)
- No staging domain / SSH deploy user / HTTPS configured.

**=> Deploy NOT executed.** A real staging requires a host to be provisioned (handoff below).
The "live" QA below was run against the local server running this exact commit.

## 4. `.env.staging` checklist
- Template `.env.staging.example` exists (3.3 KB), **git-ignored**, **no real values**.
- `.env` and `.env.staging` are **not tracked** (gitignore covers `.env*`).
- Required (fill on the real host, never commit): `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`,
  `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (Postgres), Stripe **test** keys + webhook secret,
  `PAYPAL_ENABLED=False`, `PRINTIFY_API_TOKEN` (staging), `PRINTIFY_PUSH_ENABLED=False`,
  `SHIPPING_USE_PRINTIFY` (may be True on staging to read live rates — never to push orders),
  `OPENAI_API_KEY` (staging), `N8N_WEBHOOK_URL`, `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`.

## 5. Database / static
- DB: **sqlite locally**; real staging must use managed **Postgres** + `migrate` (no migration drift detected).
- Static: `collectstatic` ok; home/legal/SEO pages serve 200.

## 6. Printify — honest data status (read-only audit, `--no-live --compare-site`)
- 2 products carry a `printify_product_id` → **24 fields cached-from-DB**, **4 demo** (stock 9999 + shipping fallback), 0 missing, 0 mismatch (no-live, so no live verification ran).
- `product_audit`: 5 products, avg quality 61% → **2 real Printify** (Sweet Dreams, New Day) + **3 demo/seed** (ATX Jeans, RXN Blue Shirt, Great Tshirt — not synced, 40%).
- **Shipping = fallback** (settings table), because `SHIPPING_USE_PRINTIFY=False`.
- `PRINTIFY_PUSH_ENABLED=False` ✓ · no order created · no product pushed.
- Customer PDP leaks **no** cost / internal Printify ID (verified: 0 occurrences).

## 7. OpenAI translation
- AI key configured locally. **2 cached translation rows** (Sweet Dreams IT + FR), status `done`.
- PDP/AI use the cached translation per active language, fallback to clean English; **never translate
  in-request**. On a host without the key, behaviour falls back to clean English (documented).

## 8. Stripe / PayPal
- Stripe **TEST mode** (public + secret keys are `pk_test`/`sk_test`), currency EUR.
- Webhook: signature-verified path exists; a public staging URL is needed to exercise live test webhooks.
- PayPal: **DISABLED** (fail-closed). No real payment made.

## 9. n8n / SMTP
- Not configured locally → **documented as missing**. Configure on the real staging host (internal test only).

## 10. QA live (local server running `5a29f27`)
- URL `http://127.0.0.1:8799/` · viewports 375/390/1280/1440 · EN/IT/FR · light + dark.
- **console 0 · HTTP 500: 0 · overflow 0** across the full matrix (Phase 46 post-merge run).
- Confirmed: made-on-demand FR single sentence, nav cart visible at 1280, dark-mode text readable,
  cart remove modal, transparent cart surfaces, sortx-style variant dropdowns, filters without yellow hover.
- Legal/SEO: robots.txt, sitemap.xml, privacy, terms, cookies, returns, FAQ, style-quiz → 200.

## 11. Rotation gates (NOT rotated — by design)
- `OPENAI_KEY_ROTATED = False` → **NEEDS_ACTION**
- `PRINTIFY_KEY_ROTATED = False` → **NEEDS_ACTION**
- These are the **last step before go-live** (the OpenAI + Printify keys were exposed in chat and must
  be rotated on the host). Technical staging can be reviewed without treating it as production-ready.

## 12. Security
- `.env` / `.env.staging` not tracked · AI key not in git · Printify token not in git · no secrets printed.
- `PRINTIFY_PUSH_ENABLED=False` · `SHIPPING_USE_PRINTIFY=False` · no real order · no real payment.

## 13. Go-live blockers (remaining, manual)
1. **Provision a staging host** (VPS/PaaS), managed Postgres, gunicorn + nginx + systemd, HTTPS + domain.
2. **Fill `.env.staging`** on the host (Stripe test, Printify staging token, OpenAI staging key, n8n/SMTP) — never commit.
3. **Rotate OpenAI + Printify keys**, then set `OPENAI_KEY_ROTATED=True` / `PRINTIFY_KEY_ROTATED=True`.
4. Run `migrate` + `collectstatic` + `check --deploy` on the host; live QA on the staging URL.
5. (Optional) Create a `main` base branch if a PR workflow is desired.

**Staging review (code/QA): READY.** **Production: NOT ready** until the blockers above are done.
